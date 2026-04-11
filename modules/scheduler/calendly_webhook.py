"""
Calendly Webhook — registra agendamentos e cancelamentos reais.

Eventos tratados:
- invitee.created  → lead efetivamente agendou → call_scheduled=True
- invitee.canceled → lead cancelou → call_scheduled=False, abre nova oportunidade

Configuração no Calendly:
  Account Settings → Integrations → Webhooks → New Webhook
  URL: https://seu-servidor.com/webhook/calendly
  Events: invitee.created, invitee.canceled

IMPORTANTE: Até este webhook estar ativo, call_scheduled=True era marcado
quando o BOT ENVIOU o link — não quando o lead agendou. Com este webhook,
a lógica muda: enviou link → call_scheduled=False, lead_invited=True.
Recebeu webhook de booking → call_scheduled=True.
"""

import hashlib
import hmac
import json
import logging
import requests
from datetime import datetime
from typing import Optional
from modules.database.models import Lead, get_session
from config.settings import CALENDLY_WEBHOOK_SECRET, CALENDLY_API_KEY

logger = logging.getLogger(__name__)


class CalendlyWebhookHandler:

    def __init__(self):
        self.db = get_session()

    # ── Verificação de assinatura ─────────────────────────────────────

    @staticmethod
    def verify_signature(payload_bytes: bytes, signature_header: str) -> bool:
        """
        Verifica assinatura HMAC-SHA256 do Calendly.
        Header: Calendly-Webhook-Signature: t=timestamp,v1=hash
        """
        if not CALENDLY_WEBHOOK_SECRET:
            logger.warning("[Calendly] CALENDLY_WEBHOOK_SECRET não configurado — pulando verificação")
            return True  # Permite em dev; em prod deve ser False

        try:
            parts = dict(p.split("=", 1) for p in signature_header.split(","))
            timestamp = parts.get("t", "")
            v1_hash   = parts.get("v1", "")

            signed_payload = f"{timestamp}.".encode() + payload_bytes
            expected = hmac.new(
                CALENDLY_WEBHOOK_SECRET.encode(),
                signed_payload,
                hashlib.sha256,
            ).hexdigest()

            return hmac.compare_digest(expected, v1_hash)
        except Exception as e:
            logger.error(f"[Calendly] Erro na verificação de assinatura: {e}")
            return False

    # ── Processamento de eventos ──────────────────────────────────────

    def process_event(self, payload: dict) -> dict:
        """
        Processa evento do Calendly.
        Retorna {"action": str, "lead_username": str | None}
        """
        event_type = payload.get("event", "")
        invitee    = payload.get("payload", {}).get("invitee", {})
        questions  = payload.get("payload", {}).get("questions_and_answers", [])

        if not invitee:
            return {"action": "ignored", "reason": "no invitee data"}

        email = invitee.get("email", "")
        name  = invitee.get("name", "")
        phone = self._extract_phone_from_questions(questions)
        event_start = invitee.get("event", {}).get("start_time", "")

        if event_type == "invitee.created":
            return self._handle_booking(email, name, phone, event_start)

        if event_type == "invitee.canceled":
            return self._handle_cancellation(email, name)

        return {"action": "ignored", "reason": f"event type '{event_type}' not handled"}

    def _handle_booking(
        self, email: str, name: str, phone: str, event_start: str
    ) -> dict:
        """Lead confirmou agendamento — atualiza banco."""
        lead = self._find_lead(email=email, phone=phone, name=name)

        if not lead:
            # Cria lead se não existir (pode vir de canal não rastreado)
            lead = Lead(
                username=f"calendly_{email.replace('@','_at_').replace('.','_')}",
                full_name=name,
                email=email,
                phone=phone or None,
                source="calendly_direct",
                intent_score="high",
                call_scheduled=True,
                call_scheduled_at=datetime.utcnow(),
                qualified=True,
            )
            self.db.add(lead)
            self.db.commit()
            logger.info(f"[Calendly] Novo lead criado via booking: {name} ({email})")
            return {"action": "created", "lead_username": lead.username}

        # Atualiza lead existente
        lead.call_scheduled     = True
        lead.call_scheduled_at  = datetime.utcnow()
        lead.qualified          = True
        if name and not lead.full_name:
            lead.full_name = name
        if phone and not lead.phone:
            lead.phone = phone
        self.db.commit()

        logger.info(
            f"[Calendly] ✅ Agendamento confirmado: {name} ({email}) "
            f"para {event_start} — @{lead.username}"
        )
        return {"action": "scheduled", "lead_username": lead.username}

    def _handle_cancellation(self, email: str, name: str) -> dict:
        """Lead cancelou — reabre oportunidade para follow-up."""
        lead = self._find_lead(email=email, name=name)
        if not lead:
            return {"action": "ignored", "reason": "lead not found for cancellation"}

        lead.call_scheduled    = False
        lead.call_scheduled_at = None
        lead.qualified         = False
        # Não desqualifica — pode reagendar
        self.db.commit()

        logger.info(f"[Calendly] ❌ Agendamento cancelado: {name} ({email})")
        return {"action": "canceled", "lead_username": lead.username}

    # ── Busca de lead ─────────────────────────────────────────────────

    def _find_lead(
        self,
        email: str = "",
        phone: str = "",
        name: str = "",
    ) -> Optional[Lead]:
        """Localiza lead por email, telefone ou nome (nessa ordem de prioridade)."""
        if email:
            lead = self.db.query(Lead).filter(Lead.email == email).first()
            if lead:
                return lead

        if phone:
            clean = "".join(filter(str.isdigit, phone))
            if len(clean) >= 8:
                lead = self.db.query(Lead).filter(
                    Lead.phone.contains(clean[-8:])
                ).first()
                if lead:
                    return lead

        if name:
            lead = self.db.query(Lead).filter(
                Lead.full_name.ilike(f"%{name}%"),
                Lead.call_scheduled == False,
            ).order_by(Lead.created_at.desc()).first()
            return lead

        return None

    @staticmethod
    def _extract_phone_from_questions(questions: list) -> str:
        """Extrai telefone das respostas do formulário do Calendly."""
        for qa in questions:
            q = qa.get("question", "").lower()
            a = qa.get("answer", "")
            if any(k in q for k in ["phone", "telefone", "whatsapp", "celular"]):
                if a:
                    return a
        return ""
