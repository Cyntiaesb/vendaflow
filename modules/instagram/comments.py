"""
Instagram Comments — monitora comentários, responde publicamente
e migra conversas qualificadas para DM.

Fluxo:
1. Busca os últimos posts da conta
2. Para cada comentário novo com sinal de interesse:
   a. Posta uma resposta pública breve ("Te mandei um DM!")
   b. Envia DM ao autor do comentário iniciando a qualificação
   c. Salva como lead no banco com source="instagram_comment"
3. Comentários sem sinal de interesse são ignorados

Sinais que disparam resposta:
- Perguntas diretas: "quanto custa?", "como funciona?", "tem whatsapp?"
- Interesse genérico: "quero", "interesse", "me manda", "saiba mais"
- Pedido de contato: "chama", "entra em contato", "fala comigo"
"""

import time
import json
from datetime import datetime
from typing import Optional
from instagrapi import Client
from modules.database.models import Lead, get_session
from modules.ai.claude_client import ClaudeClient
from config.settings import DELAY_MIN, DELAY_MAX
import random

# Palavras que indicam interesse em comentários
COMMENT_INTEREST_SIGNALS = [
    "quanto custa", "como funciona", "tem whatsapp", "qual o valor",
    "quero saber", "me manda", "me chama", "chama no", "fala comigo",
    "entra em contato", "quero mais", "interesse", "quero contratar",
    "como faço", "como contrato", "tem link", "qual o site",
    "quero sim", "top", "incrível", "preciso disso", "eu preciso",
    "onde compro", "como compro", "me add", "me segue",
]

# Comentários que NÃO devem gerar resposta
COMMENT_IGNORE_SIGNALS = [
    "spam", "fake", "mentira", "golpe", "cuidado", "fraude",
    "não acredito", "denunciar",
]


class CommentHandler:
    def __init__(self, bot_username: str, client: Client):
        self.bot_username = bot_username
        self.client = client
        self.db = get_session()
        self.ai = ClaudeClient()

    # ── Monitoramento ─────────────────────────────────────────────────

    def monitor_recent_posts(self, posts_limit: int = 5) -> int:
        """
        Verifica comentários nos últimos N posts da conta.
        Retorna quantidade de comentários processados.
        """
        try:
            user_id = self.client.user_id
            medias = self.client.user_medias(user_id, posts_limit)
        except Exception as e:
            print(f"[Comments @{self.bot_username}] Erro ao buscar posts: {e}")
            return 0

        processed = 0
        for media in medias:
            processed += self._process_media_comments(media)
            time.sleep(2)

        return processed

    def _process_media_comments(self, media) -> int:
        """Processa comentários de um post específico."""
        try:
            comments = self.client.media_comments(media.id, amount=30)
        except Exception as e:
            print(f"[Comments] Erro ao buscar comentários do post {media.id}: {e}")
            return 0

        handled = 0
        for comment in comments:
            # Ignora comentários da própria conta
            if str(comment.user.pk) == str(self.client.user_id):
                continue

            # Verifica se já processamos este comentário
            comment_key = f"comment_{comment.pk}"
            existing = self.db.query(Lead).filter(
                Lead.username == comment_key
            ).first()
            if existing:
                continue

            text_lower = comment.text.lower()

            # Ignora sinais negativos
            if any(s in text_lower for s in COMMENT_IGNORE_SIGNALS):
                continue

            # Verifica sinal de interesse
            has_interest = any(s in text_lower for s in COMMENT_INTEREST_SIGNALS)
            is_question = "?" in comment.text

            if has_interest or is_question:
                self._handle_interested_comment(comment, media)
                handled += 1
                time.sleep(random.uniform(15, 30))  # delay humano entre respostas

        return handled

    # ── Resposta a comentário com interesse ───────────────────────────

    def _handle_interested_comment(self, comment, media) -> None:
        """
        Para um comentário com sinal de interesse:
        1. Posta resposta pública curta
        2. Envia DM iniciando qualificação
        3. Salva lead no banco
        """
        commenter = comment.user
        print(f"[Comments @{self.bot_username}] 💬 Comentário de @{commenter.username}: {comment.text[:60]}")

        # 1. Resposta pública (não deve parecer robótica)
        public_reply = self.ai.generate_comment_public_reply(comment.text)
        try:
            self.client.media_comment(media.id, public_reply, replied_to_comment_id=comment.pk)
            print(f"[Comments] ✅ Resposta pública postada para @{commenter.username}")
        except Exception as e:
            print(f"[Comments] ❌ Erro ao responder comentário: {e}")

        time.sleep(random.uniform(5, 12))

        # 2. Busca informações do perfil
        try:
            user_info = self.client.user_info(commenter.pk)
            niche = user_info.category or "negócio"
            full_name = user_info.full_name or commenter.username
            is_business = user_info.is_business or bool(user_info.category)
        except Exception:
            niche = "negócio"
            full_name = commenter.username
            is_business = False

        # 3. Salva como lead
        lead = Lead(
            username=f"comment_{comment.pk}",
            full_name=full_name,
            niche=niche,
            followers=getattr(commenter, "follower_count", 0),
            instagram_username=commenter.username,
            instagram_lookup_tried=True,
            source="instagram_comment",
            intent_score="high" if is_business else "medium",
            contacted=True,
            contacted_at=datetime.utcnow(),
            contacted_by=self.bot_username,
        )
        self.db.add(lead)

        # 4. DM de qualificação
        dm_message = self.ai.generate_comment_dm_followup({
            "full_name": full_name,
            "niche": niche,
            "comment_text": comment.text,
            "is_business": is_business,
        })

        try:
            user_id = self.client.user_id_from_username(commenter.username)
            self.client.direct_send(dm_message, [user_id])

            history = [
                {"role": "context", "content": f"Lead veio de comentário: '{comment.text}'"},
                {"role": "assistant", "content": dm_message, "channel": "instagram_dm"},
            ]
            lead.conversation = json.dumps(history)
            self.db.commit()
            print(f"[Comments] 📨 DM enviado para @{commenter.username}")
        except Exception as e:
            print(f"[Comments] ❌ Erro ao enviar DM para @{commenter.username}: {e}")
            self.db.commit()
