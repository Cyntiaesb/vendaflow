"""
InstagramBot — envia DMs para leads Apollo com perfil B2B no Instagram.

Diferença do fluxo anterior:
- Antes: contatava leads frios encontrados por hashtag
- Agora: contata APENAS leads Apollo (alta intenção de compra) que têm instagram_username
  identificado pelo InstagramFinder

O prompt de DM é calibrado para leads quentes: referencia o nicho com
mais precisão, mas sem revelar que sabemos que pesquisaram o serviço.
"""

import time
import json
import random
from datetime import datetime
from instagrapi.exceptions import RateLimitError
from modules.instagram.session_manager import get_instagram_client
from modules.compliance.lgpd import LGPDCompliance
from modules.database.models import Lead, get_session
from modules.ai.claude_client import ClaudeClient
from config.settings import DELAY_MIN, DELAY_MAX


class InstagramBot:
    def __init__(self, username: str, password: str):
        from config.settings import get_instagram_proxy
        self.username = username
        self.ai = ClaudeClient()
        self.session = get_session()
        self.lgpd = LGPDCompliance()
        proxy = get_instagram_proxy(username)
        self.client = get_instagram_client(username, password, proxy=proxy or None)

    def _delay(self):
        secs = random.uniform(DELAY_MIN, DELAY_MAX)
        print(f"[Bot @{self.username}] Aguardando {secs:.0f}s...")
        time.sleep(secs)

    # ── Envio da primeira DM ──────────────────────────────────────────

    def send_first_dm(self, lead: Lead) -> bool:
        """
        Envia DM para lead Apollo com instagram_username identificado.
        Usa prompt de lead quente (alta intenção de compra).
        """
        handle = lead.instagram_username
        if not handle:
            print(f"[Bot @{self.username}] Lead {lead.username} sem instagram_username — pulando")
            return False

        try:
            message = self.ai.generate_warm_instagram_dm({
                "full_name": lead.full_name,
                "niche": lead.niche,
                "intent_score": lead.intent_score,
                "location": lead.location or "",
            })

            user_id = self.client.user_id_from_username(handle)
            self.client.direct_send(message, [user_id])

            lead.contacted = True
            lead.contacted_at = datetime.utcnow()
            lead.contacted_by = self.username
            history = [{"role": "assistant", "content": message, "channel": "instagram"}]
            lead.conversation = json.dumps(history)
            self.session.commit()

            print(f"[Bot @{self.username}] ✅ DM → @{handle} ({lead.full_name}): {message[:60]}...")
            return True

        except RateLimitError:
            print(f"[Bot @{self.username}] ⚠️ Rate limit. Pausando 30 min...")
            time.sleep(1800)
            return False
        except Exception as e:
            print(f"[Bot @{self.username}] ❌ Erro ao enviar para @{handle}: {e}")
            return False

    # ── Processar respostas ───────────────────────────────────────────

    def process_replies(self):
        """
        Lê threads recentes e processa:
        - Respostas a DMs enviados por nós (leads Apollo)
        - DMs orgânicos inbound (alguém que achou o perfil e mandou mensagem)
        Stories são tratadas pelo StoryHandler chamado pelo AccountManager.
        """
        try:
            threads = self.client.direct_threads(amount=30)
        except Exception as e:
            print(f"[Bot @{self.username}] Erro ao buscar threads: {e}")
            return

        for thread in threads:
            if not thread.messages:
                continue

            last_msg = thread.messages[0]
            if str(last_msg.user_id) == str(self.client.user_id):
                continue

            sender_username = thread.users[0].username if thread.users else None
            if not sender_username:
                continue

            # Ignora story replies — tratadas pelo StoryHandler
            item_type = str(getattr(last_msg, "item_type", "") or "")
            if item_type in {"reel_share", "story_share", "story_mention", "felix_share"}:
                continue

            # Busca lead existente pelo instagram_username
            lead = (
                self.session.query(Lead)
                .filter(Lead.instagram_username == sender_username)
                .first()
            )

            if lead and (lead.call_scheduled or lead.disqualified):
                continue

            # ── DM orgânico inbound (lead novo — não está no banco) ────
            if not lead:
                lead = self._handle_inbound_dm(sender_username, last_msg.text)
                if not lead:
                    continue
            # ──────────────────────────────────────────────────────────

            history = json.loads(lead.conversation or "[]")
            result = self.ai.handle_reply(history, last_msg.text)

            try:
                user_id = self.client.user_id_from_username(sender_username)

                if result["action"] == "disqualify":
                    lead.disqualified = True
                    lead.disqualify_reason = "rejeitou via instagram"
                    self.session.commit()
                    print(f"[Bot @{self.username}] ❌ Desqualificado: @{sender_username}")
                    continue

                if result["message"]:
                    self.client.direct_send(result["message"], [user_id])
                    history.append({"role": "user", "content": last_msg.text})
                    history.append({"role": "assistant", "content": result["message"]})
                    lead.conversation = json.dumps(history)
                    lead.responded = True
                    lead.responded_at = datetime.utcnow()

                if result["action"] == "schedule":
                    lead.call_scheduled = True
                    lead.call_scheduled_at = datetime.utcnow()
                    lead.qualified = True
                    print(f"[Bot @{self.username}] 📅 Agendamento: @{sender_username}")

                self.session.commit()
                self._delay()

            except Exception as e:
                print(f"[Bot @{self.username}] Erro ao responder @{sender_username}: {e}")

    def _handle_inbound_dm(self, sender_username: str, first_message: str) -> "Lead | None":
        """
        Cria um lead e gera a primeira resposta para quem mandou
        DM organicamente (sem ter sido prospectado por nós).
        """
        try:
            info = self.client.user_info_by_username(sender_username)
            niche = info.category or "desconhecido"
            full_name = info.full_name or sender_username
            is_business = info.is_business or bool(info.category)
        except Exception:
            niche = "desconhecido"
            full_name = sender_username
            is_business = False

        lead = Lead(
            username=f"inbound_{sender_username}",
            full_name=full_name,
            niche=niche,
            followers=getattr(info if "info" in dir() else object(), "follower_count", 0),
            instagram_username=sender_username,
            instagram_lookup_tried=True,
            source="instagram_inbound",
            intent_score="high" if is_business else "medium",
            contacted=True,
            contacted_at=datetime.utcnow(),
            contacted_by=self.username,
            responded=True,
            responded_at=datetime.utcnow(),
        )
        self.session.add(lead)

        # Primeira resposta para DM inbound orgânico
        first_response = self.ai.generate_inbound_dm_response({
            "full_name": full_name,
            "niche": niche,
            "first_message": first_message,
            "is_business": is_business,
        })

        try:
            user_id = self.client.user_id_from_username(sender_username)
            self.client.direct_send(first_response, [user_id])
            history = [
                {"role": "user", "content": first_message},
                {"role": "assistant", "content": first_response, "channel": "instagram_inbound"},
            ]
            lead.conversation = json.dumps(history)
            print(f"[Bot @{self.username}] 📨 Respondido DM inbound de @{sender_username}")
        except Exception as e:
            print(f"[Bot @{self.username}] Erro ao responder inbound @{sender_username}: {e}")

        self.session.commit()
        return lead

    # ── Campanha em lote ──────────────────────────────────────────────

    def run_campaign(self, limit: int = 80) -> int:
        """
        Envia DMs apenas para leads Apollo com instagram_username encontrado
        e que ainda não foram contatados.
        Ordena por intent_score (high primeiro).
        """
        leads = (
            self.session.query(Lead)
            .filter(
                Lead.source == "apollo_intent",
                Lead.instagram_username != None,
                Lead.contacted == False,
                Lead.disqualified == False,
            )
            .order_by(Lead.intent_score.desc())
            .limit(limit)
            .all()
        )

        print(f"[Bot @{self.username}] 🚀 Campanha Apollo→Instagram: {len(leads)} leads")
        sent = 0

        for lead in leads:
            ok = self.send_first_dm(lead)
            if ok:
                sent += 1
            self._delay()

        print(f"[Bot @{self.username}] Campanha encerrada: {sent}/{len(leads)} enviadas")
        return sent
