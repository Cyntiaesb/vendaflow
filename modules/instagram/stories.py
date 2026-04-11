"""
Instagram Stories — processa respostas e reações às stories da conta.

Stories replies chegam como DMs com contexto especial.
Instagrapi os expõe via direct_threads() com item_type diferente.

Tipos detectados:
- "reel_share"        → pessoa respondeu a um Reel
- "story_share"       → pessoa compartilhou sua story
- "story_mention"     → te marcou numa story
- "felix_share"       → resposta com texto a uma story
- Texto livre em thread nova → DM orgânico (pode ser de story sem contexto)

Fluxo:
1. Identifica threads com origem em story/reel
2. Detecta se é o primeiro contato (lead novo) ou continuação
3. Usa prompt específico para cada tipo — contexto diferente do cold outreach
"""

import json
from datetime import datetime
from typing import Optional
from instagrapi import Client
from modules.database.models import Lead, get_session
from modules.ai.claude_client import ClaudeClient

STORY_REPLY_TYPES = {
    "reel_share", "story_share", "story_mention",
    "felix_share", "media_share",
}


class StoryHandler:
    def __init__(self, bot_username: str, client: Client):
        self.bot_username = bot_username
        self.client = client
        self.db = get_session()
        self.ai = ClaudeClient()

    def process_story_replies(self) -> int:
        """
        Varre as threads recentes procurando respostas a stories.
        Integra com o loop de process_replies() do InstagramBot.
        Retorna quantidade de respostas processadas.
        """
        try:
            threads = self.client.direct_threads(amount=30)
        except Exception as e:
            print(f"[Stories @{self.bot_username}] Erro ao buscar threads: {e}")
            return 0

        processed = 0
        for thread in threads:
            if not thread.messages:
                continue

            last_msg = thread.messages[0]

            # Ignora mensagens enviadas por nós
            if str(last_msg.user_id) == str(self.client.user_id):
                continue

            # Verifica se é resposta a story/reel
            item_type = str(getattr(last_msg, "item_type", "") or "")
            is_story_reply = item_type in STORY_REPLY_TYPES

            if not is_story_reply:
                continue

            sender = thread.users[0] if thread.users else None
            if not sender:
                continue

            # Verifica se já existe como lead
            lead = (
                self.db.query(Lead)
                .filter(Lead.instagram_username == sender.username)
                .first()
            )

            if lead and (lead.call_scheduled or lead.disqualified):
                continue

            # Extrai texto da resposta (pode ser vazio se for só uma reação)
            reply_text = getattr(last_msg, "text", "") or ""
            story_context = self._extract_story_context(last_msg)

            if lead:
                # Lead já existe — continua qualificação
                self._continue_qualification(lead, reply_text, story_context)
            else:
                # Lead novo — cria e inicia qualificação
                lead = self._create_story_lead(sender, reply_text, story_context)
                self._start_story_qualification(lead, reply_text, story_context)

            processed += 1

        return processed

    # ── Helpers ───────────────────────────────────────────────────────

    def _extract_story_context(self, message) -> dict:
        """Extrai informações sobre qual story gerou a interação."""
        context = {"type": "story_reply", "story_text": "", "item_type": ""}
        try:
            context["item_type"] = str(getattr(message, "item_type", ""))
            # Tenta extrair caption da story se disponível
            reel = getattr(message, "reel_share", None) or {}
            if hasattr(reel, "media"):
                caption = getattr(reel.media, "caption_text", "") or ""
                context["story_text"] = caption[:100]
        except Exception:
            pass
        return context

    def _create_story_lead(self, sender, reply_text: str, story_context: dict) -> Lead:
        """Cria um novo lead a partir de uma interação com story."""
        try:
            info = self.client.user_info(sender.pk)
            niche = info.category or "desconhecido"
            full_name = info.full_name or sender.username
            is_business = info.is_business or bool(info.category)
        except Exception:
            niche = "desconhecido"
            full_name = sender.username
            is_business = False

        lead = Lead(
            username=f"story_{sender.pk}",
            full_name=full_name,
            niche=niche,
            instagram_username=sender.username,
            instagram_lookup_tried=True,
            source="instagram_story",
            intent_score="high" if is_business else "medium",
            contacted=True,
            contacted_at=datetime.utcnow(),
            contacted_by=self.bot_username,
            responded=True,
            responded_at=datetime.utcnow(),
        )
        self.db.add(lead)
        self.db.commit()
        return lead

    def _start_story_qualification(
        self, lead: Lead, reply_text: str, story_context: dict
    ) -> None:
        """Primeira resposta para quem interagiu com a story."""
        response = self.ai.generate_story_reply_response({
            "full_name": lead.full_name,
            "niche": lead.niche,
            "reply_text": reply_text,
            "story_type": story_context.get("item_type", ""),
            "story_text": story_context.get("story_text", ""),
        })

        try:
            user_id = self.client.user_id_from_username(lead.instagram_username)
            self.client.direct_send(response, [user_id])
            history = [
                {"role": "context", "content": f"Interagiu com story. Tipo: {story_context.get('item_type')}. Texto: '{reply_text}'"},
                {"role": "assistant", "content": response, "channel": "instagram_story"},
            ]
            lead.conversation = json.dumps(history)
            self.db.commit()
            print(f"[Stories] ✅ Resposta enviada para @{lead.instagram_username}")
        except Exception as e:
            print(f"[Stories] ❌ Erro ao responder @{lead.instagram_username}: {e}")

    def _continue_qualification(
        self, lead: Lead, reply_text: str, story_context: dict
    ) -> None:
        """Continua a qualificação de um lead que já existe."""
        if not reply_text:
            return

        history = json.loads(lead.conversation or "[]")
        result = self.ai.handle_reply(history, reply_text)

        if result["action"] == "disqualify":
            lead.disqualified = True
            lead.disqualify_reason = "rejeitou via story reply"
            self.db.commit()
            return

        if result["message"]:
            try:
                user_id = self.client.user_id_from_username(lead.instagram_username)
                self.client.direct_send(result["message"], [user_id])
                history.append({"role": "user", "content": reply_text})
                history.append({"role": "assistant", "content": result["message"]})
                lead.conversation = json.dumps(history)
                lead.responded = True
                lead.responded_at = datetime.utcnow()
            except Exception as e:
                print(f"[Stories] Erro ao responder @{lead.instagram_username}: {e}")

        if result["action"] == "schedule":
            lead.call_scheduled = True
            lead.call_scheduled_at = datetime.utcnow()
            lead.qualified = True

        self.db.commit()
