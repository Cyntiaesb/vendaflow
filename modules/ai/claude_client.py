import anthropic
from config.settings import ANTHROPIC_API_KEY, CALENDLY_LINK
from config.prompts import (
    SYSTEM_PROMPT,
    QUALIFICATION_PROMPT,
    FIRST_MESSAGE_PROMPT,
    WHATSAPP_SYSTEM_PROMPT,
    WHATSAPP_QUALIFICATION_PROMPT,
    WHATSAPP_FIRST_MESSAGE_PROMPT,
    AD_INBOUND_FIRST_RESPONSE,
    AD_INBOUND_QUALIFICATION_PROMPT,
    CALENDLY_MESSAGE,
    WHATSAPP_CALENDLY_MESSAGE,
)

INTEREST_WORDS = [
    "sim", "claro", "interesse", "como funciona", "quero saber",
    "pode ser", "me conta mais", "fala mais", "curioso", "curiosa",
    "o que é", "como assim", "me manda", "manda mais", "top", "legal",
]

REJECT_WORDS = [
    "não", "nao", "obrigado não", "para de", "spam", "chega",
    "remove", "não tenho interesse", "ocupado", "sem interesse",
]


class ClaudeClient:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        self.model = "claude-opus-4-5"

    # ── Instagram DM ───────────────────────────────────────────────────

    def generate_first_message(self, lead_info: dict) -> str:
        """Gera mensagem inicial personalizada para Instagram DM."""
        prompt = FIRST_MESSAGE_PROMPT.format(
            full_name=lead_info.get("full_name", ""),
            niche=lead_info.get("niche", ""),
            followers=lead_info.get("followers", 0),
        )
        response = self.client.messages.create(
            model=self.model,
            max_tokens=200,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip()

    def handle_reply(self, conversation_history: list, last_reply: str) -> dict:
        """Processa resposta do lead via Instagram DM."""
        messages = conversation_history + [{"role": "user", "content": last_reply}]
        reply_lower = last_reply.lower()

        if any(w in reply_lower for w in REJECT_WORDS):
            return {"message": "", "action": "disqualify"}

        response = self.client.messages.create(
            model=self.model,
            max_tokens=300,
            system=QUALIFICATION_PROMPT,
            messages=messages,
        )
        ai_message = response.content[0].text.strip()

        if any(w in reply_lower for w in INTEREST_WORDS):
            schedule_msg = CALENDLY_MESSAGE.format(calendly_link=CALENDLY_LINK)
            return {"message": schedule_msg, "action": "schedule"}

        return {"message": ai_message, "action": "continue"}

    # ── WhatsApp ───────────────────────────────────────────────────────

    def generate_whatsapp_first_message(self, lead_info: dict) -> str:
        """Gera mensagem inicial personalizada para WhatsApp."""
        prompt = WHATSAPP_FIRST_MESSAGE_PROMPT.format(
            full_name=lead_info.get("full_name", ""),
            niche=lead_info.get("niche", ""),
            intent_score=lead_info.get("intent_score", "medium"),
            location=lead_info.get("location", ""),
        )
        response = self.client.messages.create(
            model=self.model,
            max_tokens=200,
            system=WHATSAPP_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip()

    def handle_whatsapp_reply(self, conversation_history: list, last_reply: str) -> dict:
        """Processa resposta do lead via WhatsApp."""
        messages = conversation_history + [{"role": "user", "content": last_reply}]
        reply_lower = last_reply.lower()

        if any(w in reply_lower for w in REJECT_WORDS):
            return {"message": "", "action": "disqualify"}

        response = self.client.messages.create(
            model=self.model,
            max_tokens=300,
            system=WHATSAPP_QUALIFICATION_PROMPT,
            messages=messages,
        )
        ai_message = response.content[0].text.strip()

        if any(w in reply_lower for w in INTEREST_WORDS):
            schedule_msg = WHATSAPP_CALENDLY_MESSAGE.format(calendly_link=CALENDLY_LINK)
            return {"message": schedule_msg, "action": "schedule"}

        return {"message": ai_message, "action": "continue"}

    # ── Leads inbound de anúncios ──────────────────────────────────────

    def generate_ad_inbound_response(self, lead_info: dict) -> str:
        """
        Gera a primeira resposta para lead que veio de anúncio (Click-to-WhatsApp).
        Tom diferente: eles vieram até nós — resposta mais calorosa e direta.
        """
        prompt = AD_INBOUND_FIRST_RESPONSE.format(
            full_name=lead_info.get("full_name", "você"),
            ad_source=lead_info.get("ad_source", "anúncio"),
            ad_name=lead_info.get("ad_name", ""),
            niche=lead_info.get("niche", ""),
        )
        response = self.client.messages.create(
            model=self.model,
            max_tokens=200,
            system=WHATSAPP_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip()

    def handle_ad_inbound_reply(self, conversation_history: list, last_reply: str) -> dict:
        """
        Processa respostas de leads inbound de anúncios.
        Fluxo acelerado: chega ao Calendly em 3-4 trocas.
        """
        messages = conversation_history + [{"role": "user", "content": last_reply}]
        reply_lower = last_reply.lower()

        if any(w in reply_lower for w in REJECT_WORDS):
            return {"message": "", "action": "disqualify"}

        response = self.client.messages.create(
            model=self.model,
            max_tokens=300,
            system=AD_INBOUND_QUALIFICATION_PROMPT,
            messages=messages,
        )
        ai_message = response.content[0].text.strip()

        if any(w in reply_lower for w in INTEREST_WORDS):
            schedule_msg = WHATSAPP_CALENDLY_MESSAGE.format(calendly_link=CALENDLY_LINK)
            return {"message": schedule_msg, "action": "schedule"}

        return {"message": ai_message, "action": "continue"}

    def generate_warm_instagram_dm(self, lead_info: dict) -> str:
        """
        Gera DM para lead Apollo com instagram_username encontrado.
        Tom mais direto que cold outreach — lead já tem intenção de compra.
        """
        from config.prompts import WARM_INSTAGRAM_DM_PROMPT
        prompt = WARM_INSTAGRAM_DM_PROMPT.format(
            full_name=lead_info.get("full_name", ""),
            niche=lead_info.get("niche", ""),
            intent_score=lead_info.get("intent_score", "high"),
            location=lead_info.get("location", ""),
        )
        response = self.client.messages.create(
            model=self.model,
            max_tokens=200,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip()

    def generate_cold_email(self, step: int, lead_info: dict) -> dict:
        """
        Gera email frio personalizado para lead Apollo.
        Retorna {"subject": "...", "body": "..."}.
        step: 1 = primeiro contato, 2 = follow-up, 3 = último contato
        """
        from config.prompts import COLD_EMAIL_STEP1, COLD_EMAIL_STEP2, COLD_EMAIL_STEP3
        from config.settings import EMAIL_FROM_NAME

        templates = {1: COLD_EMAIL_STEP1, 2: COLD_EMAIL_STEP2, 3: COLD_EMAIL_STEP3}
        template = templates.get(step, COLD_EMAIL_STEP1)

        prompt = template.format(
            full_name=lead_info.get("full_name", ""),
            niche=lead_info.get("niche", ""),
            location=lead_info.get("location", ""),
            intent_score=lead_info.get("intent_score", "high"),
            sender_name=EMAIL_FROM_NAME,
        )

        response = self.client.messages.create(
            model=self.model,
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()

        # Parseia o formato "ASSUNTO: ... CORPO: ..."
        subject, body = "", ""
        for line in raw.split("\n"):
            if line.startswith("ASSUNTO:"):
                subject = line.replace("ASSUNTO:", "").strip()
            elif line.startswith("CORPO:"):
                body = line.replace("CORPO:", "").strip()
            elif body:
                body += "\n" + line

        # Fallback se parsing falhar
        if not subject or not body:
            parts = raw.split("\n", 1)
            subject = parts[0].strip()
            body = parts[1].strip() if len(parts) > 1 else raw

        return {"subject": subject, "body": body + f"\n\n{CALENDLY_LINK}"}

    # ── Instagram Comments ─────────────────────────────────────────────

    def generate_comment_public_reply(self, comment_text: str) -> str:
        """Gera resposta pública curta para comentário com interesse."""
        from config.prompts import COMMENT_PUBLIC_REPLY_PROMPT
        prompt = COMMENT_PUBLIC_REPLY_PROMPT.format(comment_text=comment_text[:200])
        response = self.client.messages.create(
            model=self.model, max_tokens=80,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip()

    def generate_comment_dm_followup(self, info: dict) -> str:
        """Gera DM de qualificação após resposta pública a comentário."""
        from config.prompts import COMMENT_DM_FOLLOWUP_PROMPT
        prompt = COMMENT_DM_FOLLOWUP_PROMPT.format(
            full_name=info.get("full_name", ""),
            niche=info.get("niche", "negócio"),
            comment_text=info.get("comment_text", "")[:200],
            is_business=info.get("is_business", False),
        )
        response = self.client.messages.create(
            model=self.model, max_tokens=200,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip()

    # ── Instagram Stories ──────────────────────────────────────────────

    def generate_story_reply_response(self, info: dict) -> str:
        """Gera resposta para quem interagiu com uma story/reel."""
        from config.prompts import STORY_REPLY_PROMPT
        prompt = STORY_REPLY_PROMPT.format(
            full_name=info.get("full_name", ""),
            niche=info.get("niche", "negócio"),
            reply_text=info.get("reply_text", "")[:300],
            story_type=info.get("story_type", "story"),
            story_text=info.get("story_text", "")[:200],
        )
        response = self.client.messages.create(
            model=self.model, max_tokens=200,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip()

    # ── DM Inbound Orgânico ────────────────────────────────────────────

    def generate_inbound_dm_response(self, info: dict) -> str:
        """Gera resposta para DM inbound orgânico (alguém que achou o perfil)."""
        from config.prompts import INBOUND_DM_PROMPT
        prompt = INBOUND_DM_PROMPT.format(
            full_name=info.get("full_name", ""),
            niche=info.get("niche", "desconhecido"),
            first_message=info.get("first_message", "")[:300],
            is_business=info.get("is_business", False),
        )
        response = self.client.messages.create(
            model=self.model, max_tokens=200,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip()

    # ── Scoring de perfil Instagram (Apify data) ──────────────────────

    def score_instagram_profile(
        self, profile_data: dict, target_niche: str
    ) -> dict:
        """
        Analisa os dados brutos do Apify e retorna score do lead.
        Retorna {"score": "hot"|"warm"|"cold", "reason": "..."}.
        """
        from config.prompts import PROFILE_SCORE_PROMPT
        from modules.prospecting.apify_client import ApifyClient

        summary = ApifyClient.extract_profile_summary(profile_data)

        prompt = PROFILE_SCORE_PROMPT.format(
            target_niche=target_niche,
            username=summary["username"],
            full_name=summary["full_name"],
            bio=summary["bio"] or "(sem bio)",
            followers=summary["followers"],
            following=summary["following"],
            posts_count=summary["posts_count"],
            is_business=summary["is_business"],
            category=summary["category"] or "(sem categoria)",
            website=summary["website"] or "(sem website)",
            city=summary["city"] or "(sem cidade)",
            recent_captions=" | ".join(summary["recent_post_captions"]) or "(sem posts recentes)",
        )

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=150,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = response.content[0].text.strip()
            # Remove possível markdown
            raw = raw.replace("```json", "").replace("```", "").strip()
            import json as _json
            result = _json.loads(raw)
            return {
                "score": result.get("score", "cold"),
                "reason": result.get("reason", ""),
            }
        except Exception as e:
            print(f"[Claude] Erro ao pontuar perfil: {e}")
            return {"score": "cold", "reason": "Erro na análise"}
