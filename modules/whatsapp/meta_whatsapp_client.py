"""
Meta WhatsApp Business Cloud API — cliente oficial.

Substitui completamente a Evolution API (número pessoal).

Conceitos fundamentais:
─────────────────────────────────────────────────────────────────────
JANELA DE 24H (Customer Service Window)
  Quando o lead envia uma mensagem para nós, abre uma janela de 24h
  na qual podemos responder com texto livre (free-form).
  Fora dessa janela → obrigatório usar Template Message aprovado.

TEMPLATES (HSM — Highly Structured Messages)
  Mensagens pré-aprovadas pela Meta para iniciar conversas.
  Necessárias para: outbound Apollo, follow-ups sem resposta.
  Aprovação: 1–3 dias úteis após submissão.
  Categorias: MARKETING (primeiro contato) | UTILITY (Calendly link)

STATUS DE MENSAGEM
  Webhook recebe: sent → delivered → read | failed
  Permite saber se a mensagem foi entregue/lida.
─────────────────────────────────────────────────────────────────────

Configuração no Meta:
  1. business.facebook.com → WhatsApp → Getting Started
  2. Crie um app Business no developers.facebook.com
  3. Adicione WhatsApp product → anote Phone Number ID e WABA ID
  4. Crie um System User com permissão whatsapp_business_messaging
  5. Configure webhook apontando para /webhook/whatsapp
"""

import json
import logging
import random
import time
from datetime import datetime, timedelta
from typing import Optional

import requests

from config.settings import (
    META_ACCESS_TOKEN,
    WHATSAPP_PHONE_NUMBER_ID,
    META_API_VERSION,
    DELAY_MIN,
    DELAY_MAX,
    CALENDLY_LINK,
)
from modules.ai.claude_client import ClaudeClient
from modules.compliance.lgpd import LGPDCompliance
from modules.database.models import Lead, get_session
from modules.whatsapp.templates import TemplateManager, TEMPLATE_NAMES

logger = logging.getLogger(__name__)

BASE_URL = f"https://graph.facebook.com/{META_API_VERSION}"


class MetaWhatsAppClient:
    """
    Interface idêntica ao antigo EvolutionClient para zero impacto no resto do código.
    """

    def __init__(self):
        self.phone_number_id = WHATSAPP_PHONE_NUMBER_ID
        self.headers = {
            "Authorization": f"Bearer {META_ACCESS_TOKEN}",
            "Content-Type": "application/json",
        }
        self.ai = ClaudeClient()
        self.db = get_session()
        self.lgpd = LGPDCompliance()
        self.templates = TemplateManager()

    # ── Envio de mensagens ────────────────────────────────────────────

    def send_text(self, phone: str, message: str) -> bool:
        """
        Envia mensagem de texto livre.
        SÓ funciona dentro da janela de 24h após o lead ter mandado mensagem.
        Fora da janela → use send_template().
        """
        clean = self._clean_phone(phone)
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": clean,
            "type": "text",
            "text": {"preview_url": False, "body": message},
        }
        return self._post_message(clean, payload)

    def send_template(
        self,
        phone: str,
        template_name: str,
        variables: list[str],
        language: str = "pt_BR",
    ) -> bool:
        """
        Envia mensagem usando template aprovado pela Meta.
        Usado para: primeiro contato, follow-ups, Calendly link.
        """
        clean = self._clean_phone(phone)
        components = []
        if variables:
            components.append({
                "type": "body",
                "parameters": [{"type": "text", "text": v} for v in variables],
            })

        payload = {
            "messaging_product": "whatsapp",
            "to": clean,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language},
                "components": components,
            },
        }
        return self._post_message(clean, payload)

    def send_reaction(self, phone: str, message_id: str, emoji: str = "👋") -> bool:
        """Envia reação a uma mensagem — humaniza a conversa."""
        clean = self._clean_phone(phone)
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": clean,
            "type": "reaction",
            "reaction": {"message_id": message_id, "emoji": emoji},
        }
        return self._post_message(clean, payload)

    def mark_as_read(self, message_id: str) -> None:
        """Marca a mensagem como lida — mostra os dois ticks azuis."""
        try:
            requests.post(
                f"{BASE_URL}/{self.phone_number_id}/messages",
                headers=self.headers,
                json={
                    "messaging_product": "whatsapp",
                    "status": "read",
                    "message_id": message_id,
                },
                timeout=10,
            )
        except Exception:
            pass

    def _post_message(self, phone: str, payload: dict) -> bool:
        try:
            resp = requests.post(
                f"{BASE_URL}/{self.phone_number_id}/messages",
                headers=self.headers,
                json=payload,
                timeout=15,
            )
            resp.raise_for_status()
            msg_id = resp.json().get("messages", [{}])[0].get("id", "")
            logger.info(f"[WhatsApp] ✅ Enviado para {phone} — id: {msg_id}")
            return True
        except Exception as e:
            logger.error(f"[WhatsApp] ❌ Erro ao enviar para {phone}: {e}")
            return False

    # ── Primeiro contato (outbound Apollo) ───────────────────────────

    def send_first_message(self, lead: Lead) -> bool:
        """
        Envia TEMPLATE de primeiro contato para lead Apollo.
        Template obrigatório pois é mensagem iniciada por nós.
        """
        if not lead.phone:
            return False

        # Checagem de compliance
        can, reason = self.lgpd.can_contact_lead(lead, "whatsapp")
        if not can:
            logger.info(f"[WhatsApp] @{lead.username} bloqueado: {reason}")
            return False

        # Usa template primeiro_contato com variáveis: nome, nicho
        first_name = (lead.full_name or "").split()[0] or "Olá"
        niche = lead.niche or "seu segmento"

        ok = self.send_template(
            phone=lead.phone,
            template_name=TEMPLATE_NAMES["primeiro_contato"],
            variables=[first_name, niche],
        )

        if ok:
            history = [{
                "role": "assistant",
                "content": f"[template:{TEMPLATE_NAMES['primeiro_contato']}] {first_name} / {niche}",
                "channel": "whatsapp",
            }]
            lead.whatsapp_contacted = True
            lead.whatsapp_contacted_at = datetime.utcnow()
            lead.whatsapp_conversation = json.dumps(history)
            if not lead.contacted:
                lead.contacted = True
                lead.contacted_at = datetime.utcnow()
                lead.contacted_by = f"meta_wa:{self.phone_number_id}"
            self.db.commit()

        return ok

    # ── Processamento de webhook Meta ─────────────────────────────────

    def process_webhook_message(self, message: dict, metadata: dict) -> Optional[str]:
        """
        Processa uma mensagem recebida via webhook Meta.
        Retorna a resposta enviada ou None.

        message: objeto message do payload Meta
        metadata: objeto metadata com phone_number_id, display_phone_number
        """
        msg_type = message.get("type", "")
        phone    = message.get("from", "")
        msg_id   = message.get("id", "")
        timestamp= int(message.get("timestamp", 0))

        # Extrai texto (suporta text, button reply, interactive reply)
        text = self._extract_message_text(message)
        if not text:
            logger.debug(f"[WhatsApp] Mensagem sem texto de {phone} (tipo: {msg_type})")
            return None

        # Marca como lida
        self.mark_as_read(msg_id)

        # Verifica opt-out LGPD
        if self.lgpd.is_opt_out_request(text):
            lead = self._find_lead(phone)
            if lead:
                self.lgpd.process_opt_out(lead, "whatsapp")
            self.send_text(phone,
                "Tudo bem! Você foi removido da nossa lista e não receberá mais mensagens. "
                "Se mudar de ideia, é só chamar aqui. Até mais! 👋"
            )
            return None

        # Extrai informações de anúncio (Click-to-WhatsApp)
        ad_info = self._extract_ad_referral(message)

        # Busca ou cria o lead
        lead = self._find_lead(phone)
        is_new_lead = lead is None

        if is_new_lead:
            lead = self._create_inbound_lead(phone, text, ad_info)
        else:
            # Atualiza campos de anúncio se ainda não preenchidos
            if ad_info and not lead.ad_source:
                lead.ad_source    = ad_info.get("ad_source")
                lead.ad_id        = ad_info.get("ad_id")
                lead.campaign_id  = ad_info.get("campaign_id")
                lead.ctwa_clid    = ad_info.get("ctwa_clid")
                lead.intent_score = "high"

        if lead.call_scheduled or lead.disqualified:
            self.db.commit()
            return None

        # Atualiza janela de 24h
        lead.whatsapp_last_inbound_at = datetime.utcnow()

        # Escolhe o prompt correto
        history = json.loads(lead.whatsapp_conversation or "[]")
        is_ad_lead     = bool(lead.ad_source)
        is_first_reply = len([m for m in history if m.get("role") == "user"]) == 0

        if is_ad_lead and is_first_reply:
            reply = self.ai.generate_ad_inbound_response({
                "full_name": lead.full_name or "você",
                "ad_source": lead.ad_source,
                "ad_name":   lead.ad_name or "",
                "niche":     lead.niche or "",
            })
            result = {"message": reply, "action": "continue"}
        elif is_new_lead and is_first_reply:
            # DM orgânica nova — usa fluxo inbound
            reply = self.ai.generate_inbound_dm_response({
                "full_name":    lead.full_name or "",
                "niche":        lead.niche or "",
                "first_message":text,
                "is_business":  False,
            })
            result = {"message": reply, "action": "continue"}
        elif is_ad_lead:
            result = self.ai.handle_ad_inbound_reply(history, text)
        else:
            result = self.ai.handle_whatsapp_reply(history, text)

        # Processa resultado
        if result["action"] == "disqualify":
            lead.disqualified      = True
            lead.disqualify_reason = "rejeitou via whatsapp"
            self.db.commit()
            return None

        reply_text = result.get("message", "")
        if not reply_text:
            self.db.commit()
            return None

        # Dentro da janela 24h → texto livre; fora → template Calendly se for schedule
        if result["action"] == "schedule":
            reply_text = self._format_calendly_message(lead)
            self.send_text(phone, reply_text)
            lead.call_scheduled    = True
            lead.call_scheduled_at = datetime.utcnow()
            lead.qualified         = True
            if lead.ad_source == "meta":
                self._send_meta_conversion(lead)
            logger.info(f"[WhatsApp] 📅 Calendly enviado para @{lead.username}")
        else:
            self.send_text(phone, reply_text)

        history.append({"role": "user",      "content": text})
        history.append({"role": "assistant",  "content": reply_text, "channel": "whatsapp"})
        lead.whatsapp_conversation = json.dumps(history)
        lead.responded             = True
        lead.responded_at          = datetime.utcnow()

        self.db.commit()
        return reply_text

    # ── Campanha em lote ──────────────────────────────────────────────

    def run_whatsapp_campaign(self, limit: int = 40) -> int:
        """
        Envia template de primeiro contato para leads Apollo com telefone.
        High intent primeiro. Respeita janela horária via LGPDCompliance.
        """
        if not LGPDCompliance.is_sending_allowed():
            logger.info("[WhatsApp] Fora da janela horária — campanha adiada")
            return 0

        leads = (
            self.db.query(Lead)
            .filter(
                Lead.phone != None,
                Lead.whatsapp_contacted == False,
                Lead.whatsapp_invalid   == False,
                Lead.disqualified       == False,
                Lead.opted_out          != True,
            )
            .order_by(Lead.intent_score.desc())
            .limit(limit)
            .all()
        )

        logger.info(f"[WhatsApp] 🚀 Campanha: {len(leads)} leads")
        sent = 0

        for lead in leads:
            ok = self.send_first_message(lead)
            if ok:
                sent += 1
            secs = random.uniform(DELAY_MIN, DELAY_MAX)
            logger.debug(f"[WhatsApp] Aguardando {secs:.0f}s...")
            time.sleep(secs)

        logger.info(f"[WhatsApp] Campanha encerrada: {sent}/{len(leads)}")
        return sent

    # ── Helpers ───────────────────────────────────────────────────────

    def _find_lead(self, phone: str) -> Optional[Lead]:
        clean = "".join(filter(str.isdigit, phone))
        if len(clean) >= 8:
            return self.db.query(Lead).filter(
                Lead.phone.contains(clean[-8:])
            ).first()
        return None

    def _create_inbound_lead(self, phone: str, text: str, ad_info: dict) -> Lead:
        """Cria lead novo para mensagem inbound orgânica ou de anúncio."""
        username = f"wa_inbound_{phone[-8:]}_{int(datetime.utcnow().timestamp())}"
        lead = Lead(
            username          = username,
            phone             = phone,
            source            = f"{ad_info.get('ad_source')}_ad" if ad_info.get("ad_source") else "whatsapp_inbound",
            intent_score      = "high",
            contacted         = True,
            contacted_at      = datetime.utcnow(),
            contacted_by      = f"meta_wa:{self.phone_number_id}",
            whatsapp_contacted= True,
            whatsapp_contacted_at= datetime.utcnow(),
            ad_source         = ad_info.get("ad_source"),
            ad_id             = ad_info.get("ad_id"),
            campaign_id       = ad_info.get("campaign_id"),
            ctwa_clid         = ad_info.get("ctwa_clid"),
        )
        self.db.add(lead)
        self.db.commit()
        return lead

    @staticmethod
    def _extract_message_text(message: dict) -> str:
        """Extrai texto de vários tipos de mensagem Meta."""
        msg_type = message.get("type", "")
        if msg_type == "text":
            return message.get("text", {}).get("body", "")
        if msg_type == "button":
            return message.get("button", {}).get("text", "")
        if msg_type == "interactive":
            inter = message.get("interactive", {})
            if inter.get("type") == "button_reply":
                return inter.get("button_reply", {}).get("title", "")
            if inter.get("type") == "list_reply":
                return inter.get("list_reply", {}).get("title", "")
        return ""

    @staticmethod
    def _extract_ad_referral(message: dict) -> dict:
        """Extrai dados de rastreamento de anúncio Click-to-WhatsApp."""
        referral = message.get("referral") or {}
        if not referral:
            return {}
        return {
            "ad_source":   "meta",
            "ad_id":       referral.get("source_id", ""),
            "campaign_id": referral.get("ads_context_data", {}).get("campaign_id", ""),
            "ad_name":     referral.get("headline", ""),
            "ctwa_clid":   referral.get("ctwa_clid", ""),
        }

    def _format_calendly_message(self, lead: Lead) -> str:
        first_name = (lead.full_name or "").split()[0] or "você"
        return (
            f"Perfeito, {first_name}! 🎉\n\n"
            f"Aqui está o link para escolher o melhor horário — são só 20 minutos:\n"
            f"{CALENDLY_LINK}"
        )

    def _send_meta_conversion(self, lead: Lead) -> None:
        """Envia evento Schedule para Meta Conversions API."""
        try:
            from modules.ads.meta_client import MetaAdsClient
            MetaAdsClient().send_conversion(
                event_name="Schedule",
                phone=lead.phone or "",
                click_id=lead.ctwa_clid,
            )
        except Exception as e:
            logger.warning(f"[WhatsApp] Conversão Meta não enviada: {e}")

    @staticmethod
    def _clean_phone(phone: str) -> str:
        digits = "".join(filter(str.isdigit, phone))
        if not digits.startswith("55") and len(digits) <= 11:
            digits = "55" + digits
        return digits
