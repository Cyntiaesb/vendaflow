"""
Email outreach — canal para leads Apollo com email mas sem telefone,
ou como canal adicional para leads que também têm telefone.

Provedor: SendGrid (API REST simples, boa deliverability, free até 100/dia)
Alternativa: Resend.com (developer-friendly, free até 100/dia)

Fluxo:
1. primeiro_contato()  → email personalizado pelo Claude
2. follow_up_1()       → 3 dias depois se não respondeu
3. follow_up_2()       → 7 dias depois se ainda não respondeu
4. Desqualifica após follow_up_2 sem resposta

Webhook de eventos (SendGrid):
  POST /webhook/email  → recebe: open, click, bounce, unsubscribe, reply
"""

import requests
import json
from datetime import datetime
from typing import Optional
from modules.database.models import Lead, get_session
from modules.ai.claude_client import ClaudeClient
from config.settings import (
    SENDGRID_API_KEY,
    EMAIL_FROM_ADDRESS,
    EMAIL_FROM_NAME,
    CALENDLY_LINK,
)


class EmailClient:
    SENDGRID_URL = "https://api.sendgrid.com/v3/mail/send"

    def __init__(self):
        self.db = get_session()
        self.ai = ClaudeClient()
        self.headers = {
            "Authorization": f"Bearer {SENDGRID_API_KEY}",
            "Content-Type": "application/json",
        }

    # ── Envio ─────────────────────────────────────────────────────────

    def send(
        self,
        to_email: str,
        to_name: str,
        subject: str,
        body: str,
        lead_id: Optional[int] = None,
    ) -> bool:
        """
        Envia um email via SendGrid.
        Inclui custom_args com lead_id para rastreamento no webhook.
        """
        if not SENDGRID_API_KEY:
            print(f"[Email] SENDGRID_API_KEY não configurada — pulando")
            return False

        payload = {
            "personalizations": [
                {
                    "to": [{"email": to_email, "name": to_name}],
                    "custom_args": {"lead_id": str(lead_id or "")},
                }
            ],
            "from": {"email": EMAIL_FROM_ADDRESS, "name": EMAIL_FROM_NAME},
            "subject": subject,
            "content": [{"type": "text/plain", "value": body}],
            "tracking_settings": {
                "click_tracking": {"enable": True},
                "open_tracking": {"enable": True},
            },
        }

        try:
            resp = requests.post(
                self.SENDGRID_URL,
                headers=self.headers,
                json=payload,
                timeout=15,
            )
            resp.raise_for_status()
            print(f"[Email] ✅ Enviado para {to_email} ({to_name}) — assunto: {subject}")
            return True
        except Exception as e:
            print(f"[Email] ❌ Erro ao enviar para {to_email}: {e}")
            return False

    # ── Sequência de emails ───────────────────────────────────────────

    def send_first_contact(self, lead: Lead) -> bool:
        """
        Primeiro email da sequência — apresentação e geração de interesse.
        """
        if not lead.email or lead.email_bounced or lead.email_unsubscribed:
            return False
        if lead.email_contacted:
            return False

        content = self.ai.generate_cold_email(
            step=1,
            lead_info={
                "full_name": lead.full_name,
                "niche": lead.niche,
                "intent_score": lead.intent_score,
                "location": lead.location or "",
                "company": lead.niche,
            },
        )

        ok = self.send(
            to_email=lead.email,
            to_name=lead.full_name or "",
            subject=content["subject"],
            body=content["body"],
            lead_id=lead.id,
        )

        if ok:
            lead.email_contacted = True
            lead.email_contacted_at = datetime.utcnow()
            lead.email_sequence_step = 1
            self.db.commit()

        return ok

    def send_follow_up(self, lead: Lead) -> bool:
        """
        Follow-up para leads que não responderam.
        step 2: 3 dias após o primeiro contato
        step 3: 7 dias após o primeiro contato (último)
        """
        if not lead.email or lead.email_bounced or lead.email_unsubscribed:
            return False
        if lead.email_replied or lead.call_scheduled or lead.disqualified:
            return False

        next_step = (lead.email_sequence_step or 1) + 1
        if next_step > 3:
            return False

        content = self.ai.generate_cold_email(
            step=next_step,
            lead_info={
                "full_name": lead.full_name,
                "niche": lead.niche,
                "intent_score": lead.intent_score,
                "location": lead.location or "",
                "company": lead.niche,
            },
        )

        ok = self.send(
            to_email=lead.email,
            to_name=lead.full_name or "",
            subject=content["subject"],
            body=content["body"],
            lead_id=lead.id,
        )

        if ok:
            lead.email_sequence_step = next_step
            if next_step == 3:
                # Último follow-up sem resposta → desqualifica suavemente
                lead.disqualified = True
                lead.disqualify_reason = "sem resposta após 3 emails"
            self.db.commit()

        return ok

    # ── Campanhas em lote ─────────────────────────────────────────────

    def run_first_contact_campaign(self, limit: int = 50) -> int:
        """
        Envia primeiro email para leads Apollo que:
        - Têm email
        - Não foram contatados por email ainda
        - Não agendaram nem foram desqualificados
        - NÃO têm telefone (os com telefone já recebem WhatsApp)
        - OU têm telefone mas o email é canal adicional de alcance
        """
        # Prioriza leads SEM telefone (só têm email como canal)
        # e High intent primeiro
        leads = (
            self.db.query(Lead)
            .filter(
                Lead.source == "apollo_intent",
                Lead.email != None,
                Lead.email_contacted == False,
                Lead.email_bounced == False,
                Lead.email_unsubscribed == False,
                Lead.disqualified == False,
                Lead.call_scheduled == False,
            )
            .order_by(
                # Leads sem telefone têm prioridade (email é o único canal)
                Lead.phone == None,
                Lead.intent_score.desc(),
            )
            .limit(limit)
            .all()
        )

        print(f"[Email] 📧 Campanha: {len(leads)} leads")
        sent = 0
        for lead in leads:
            ok = self.send_first_contact(lead)
            if ok:
                sent += 1
        print(f"[Email] Campanha encerrada: {sent}/{len(leads)} enviados")
        return sent

    def run_followup_campaign(self, limit: int = 30) -> int:
        """
        Processa follow-ups pendentes.
        Roda 1x por dia — envia step 2 ou 3 para quem não respondeu.
        """
        from datetime import timedelta

        # Step 2: leads no step 1 há mais de 3 dias sem resposta
        leads_step2 = (
            self.db.query(Lead)
            .filter(
                Lead.email_sequence_step == 1,
                Lead.email_replied == False,
                Lead.email_bounced == False,
                Lead.email_unsubscribed == False,
                Lead.disqualified == False,
                Lead.call_scheduled == False,
                Lead.email_contacted_at <= datetime.utcnow() - timedelta(days=3),
            )
            .limit(limit // 2)
            .all()
        )

        # Step 3: leads no step 2 há mais de 4 dias sem resposta
        leads_step3 = (
            self.db.query(Lead)
            .filter(
                Lead.email_sequence_step == 2,
                Lead.email_replied == False,
                Lead.email_bounced == False,
                Lead.email_unsubscribed == False,
                Lead.disqualified == False,
                Lead.call_scheduled == False,
                Lead.email_contacted_at <= datetime.utcnow() - timedelta(days=7),
            )
            .limit(limit // 2)
            .all()
        )

        sent = 0
        for lead in leads_step2 + leads_step3:
            ok = self.send_follow_up(lead)
            if ok:
                sent += 1

        print(f"[Email] Follow-ups enviados: {sent}")
        return sent

    # ── Webhook handler ───────────────────────────────────────────────

    def process_sendgrid_event(self, event: dict) -> None:
        """
        Processa um evento SendGrid (open, click, bounce, unsubscribe, delivered).
        Chamado pelo endpoint POST /webhook/email no Flask.
        """
        lead_id = event.get("lead_id") or event.get("custom_args", {}).get("lead_id")
        event_type = event.get("event", "")

        if not lead_id:
            return

        try:
            lead = self.db.query(Lead).filter(Lead.id == int(lead_id)).first()
            if not lead:
                return

            if event_type == "open" and not lead.email_opened:
                lead.email_opened = True
                print(f"[Email] 📬 Email aberto por {lead.full_name}")

            elif event_type in ("bounce", "dropped"):
                lead.email_bounced = True
                print(f"[Email] ❌ Bounce: {lead.email}")

            elif event_type == "unsubscribe":
                lead.email_unsubscribed = True
                lead.disqualified = True
                lead.disqualify_reason = "unsubscribe email"
                print(f"[Email] 🚫 Unsubscribe: {lead.email}")

            self.db.commit()

        except Exception as e:
            print(f"[Email] Erro ao processar evento {event_type}: {e}")
