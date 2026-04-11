"""
Evolution API — outreach via WhatsApp.

Suporta:
- Envio de texto simples (send_text)
- Verificar se número tem WhatsApp (check_number)
- Processar respostas recebidas (process_webhook_reply)
- Campanha em lote (run_whatsapp_campaign)

Configurar webhook no painel Evolution para:
  POST {SEU_SERVIDOR}/webhook/whatsapp
"""

import time
import json
import random
import requests
from datetime import datetime
from typing import Optional
from modules.database.models import Lead, get_session
from modules.ai.claude_client import ClaudeClient
from modules.compliance.lgpd import LGPDCompliance
from config.settings import (
    EVOLUTION_API_URL,
    EVOLUTION_API_KEY,
    EVOLUTION_INSTANCE,
    DELAY_MIN,
    DELAY_MAX,
    CALENDLY_LINK,
)
from config.prompts import WHATSAPP_FIRST_MESSAGE_PROMPT, CALENDLY_MESSAGE


class EvolutionClient:
    def __init__(self):
        self.base = EVOLUTION_API_URL.rstrip("/")
        self.instance = EVOLUTION_INSTANCE
        self.headers = {
            "Content-Type": "application/json",
            "apikey": EVOLUTION_API_KEY,
        }
        self.ai = ClaudeClient()
        self.db = get_session()

    # ------------------------------------------------------------------
    # Verificação de número
    # ------------------------------------------------------------------

    def check_number(self, phone: str) -> bool:
        """Verifica se o número existe no WhatsApp antes de enviar."""
        clean = self._clean_phone(phone)
        try:
            resp = requests.get(
                f"{self.base}/chat/whatsappNumbers/{self.instance}",
                headers=self.headers,
                params={"numbers": clean},
                timeout=10,
            )
            resp.raise_for_status()
            result = resp.json()

            # Estrutura: [{"number": "...", "exists": true}]
            for item in result if isinstance(result, list) else []:
                if item.get("exists"):
                    return True
            return False

        except Exception as e:
            print(f"[WhatsApp] Erro ao verificar número {phone}: {e}")
            return False

    # ------------------------------------------------------------------
    # Envio de mensagem
    # ------------------------------------------------------------------

    def send_text(self, phone: str, message: str, delay_ms: int = 1200) -> bool:
        """
        Envia mensagem de texto para um número.

        Args:
            phone:    número com DDI (ex: "5511999999999")
            message:  texto da mensagem
            delay_ms: delay de digitação simulada em ms
        """
        clean = self._clean_phone(phone)
        payload = {
            "number": clean,
            "options": {
                "delay": delay_ms,
                "presence": "composing",   # exibe "digitando..."
            },
            "textMessage": {"text": message},
        }

        try:
            resp = requests.post(
                f"{self.base}/message/sendText/{self.instance}",
                headers=self.headers,
                json=payload,
                timeout=15,
            )
            resp.raise_for_status()
            print(f"[WhatsApp] ✅ Enviado para {clean}: {message[:60]}...")
            return True

        except Exception as e:
            print(f"[WhatsApp] ❌ Erro ao enviar para {clean}: {e}")
            return False

    # ------------------------------------------------------------------
    # Primeira mensagem a um lead
    # ------------------------------------------------------------------

    def send_first_message(self, lead: Lead) -> bool:
        """Gera e envia a primeira mensagem WhatsApp para um lead."""
        if not lead.phone:
            print(f"[WhatsApp] @{lead.username} sem telefone — pulando")
            return False

        # Verifica existência no WhatsApp
        if not self.check_number(lead.phone):
            print(f"[WhatsApp] {lead.phone} não tem WhatsApp")
            lead.whatsapp_invalid = True
            self.db.commit()
            return False

        # Gera mensagem personalizada via Claude
        message = self.ai.generate_whatsapp_first_message({
            "full_name": lead.full_name,
            "niche": lead.niche,
            "intent_score": lead.intent_score or "medium",
            "location": lead.location or "",
        })

        ok = self.send_text(lead.phone, message)

        if ok:
            history = [{"role": "assistant", "content": message, "channel": "whatsapp"}]
            lead.whatsapp_contacted = True
            lead.whatsapp_contacted_at = datetime.utcnow()
            lead.whatsapp_conversation = json.dumps(history)
            # Marca como contatado globalmente também
            if not lead.contacted:
                lead.contacted = True
                lead.contacted_at = datetime.utcnow()
                lead.contacted_by = f"whatsapp:{self.instance}"
            self.db.commit()

        return ok

    # ------------------------------------------------------------------
    # Processar resposta via webhook
    # ------------------------------------------------------------------

    def process_webhook_reply(self, webhook_payload: dict) -> Optional[str]:
        """
        Processa payload recebido pelo webhook da Evolution API.

        Detecta automaticamente se a mensagem veio de um anúncio Meta
        (campo referral no payload) ou tem UTM params de Google.
        Usa fluxo de qualificação acelerado para leads de anúncio.
        """
        try:
            data = webhook_payload.get("data", {})
            msg_type = webhook_payload.get("event", "")

            if msg_type not in ("messages.upsert", "MESSAGES_UPSERT"):
                return None

            from_me = data.get("key", {}).get("fromMe", True)
            if from_me:
                return None

            phone_raw = data.get("key", {}).get("remoteJid", "")
            phone = phone_raw.replace("@s.whatsapp.net", "").replace("@c.us", "")
            text = (
                data.get("message", {}).get("conversation")
                or data.get("message", {}).get("extendedTextMessage", {}).get("text")
                or ""
            )

            if not phone or not text:
                return None

            # ── Verifica opt-out LGPD ─────────────────────────────────
            lgpd = LGPDCompliance()
            if lgpd.is_opt_out_request(text):
                # Busca o lead e processa opt-out
                lead_for_opt = self.db.query(Lead).filter(
                    Lead.phone.contains(phone[-8:])
                ).first()
                if lead_for_opt:
                    lgpd.process_opt_out(lead_for_opt, channel="whatsapp")
                    self.send_text(phone, "Ok, você foi removido da nossa lista. Não receberá mais mensagens. Até mais!")
                return None

            # ── Detecta origem do anúncio ─────────────────────────────
            ad_info = self._extract_ad_info(data, text)

            # ── Busca ou cria o lead ──────────────────────────────────
            lead = self.db.query(Lead).filter(
                Lead.phone.contains(phone[-8:])
            ).first()

            if not lead:
                # Lead novo vindo de anúncio — cria registro inbound
                username = f"ad_{phone[-8:]}_{int(datetime.utcnow().timestamp())}"
                lead = Lead(
                    username=username,
                    phone=phone,
                    source=f"{ad_info['ad_source']}_ad" if ad_info.get("ad_source") else "whatsapp_inbound",
                    intent_score="high",
                    contacted=True,
                    contacted_at=datetime.utcnow(),
                    contacted_by="inbound",
                    whatsapp_contacted=True,
                    whatsapp_contacted_at=datetime.utcnow(),
                )
                self.db.add(lead)

            # Atualiza campos de rastreamento de anúncio se disponíveis
            if ad_info.get("ad_source") and not lead.ad_source:
                lead.ad_source    = ad_info.get("ad_source")
                lead.ad_id        = ad_info.get("ad_id")
                lead.adset_id     = ad_info.get("adset_id")
                lead.campaign_id  = ad_info.get("campaign_id")
                lead.ad_name      = ad_info.get("ad_name")
                lead.ctwa_clid    = ad_info.get("ctwa_clid")
                lead.utm_source   = ad_info.get("utm_source")
                lead.utm_campaign = ad_info.get("utm_campaign")
                lead.utm_medium   = ad_info.get("utm_medium")
                lead.intent_score = "high"  # veio de anúncio = quente

            if lead.call_scheduled or lead.disqualified:
                self.db.commit()
                return None

            # ── Escolhe fluxo Claude correto ──────────────────────────
            history = json.loads(lead.whatsapp_conversation or "[]")
            is_ad_lead = bool(lead.ad_source)
            is_first_message = len(history) == 0

            if is_ad_lead and is_first_message:
                # Primeira mensagem de lead de anúncio → resposta inbound calorosa
                reply = self.ai.generate_ad_inbound_response({
                    "full_name": lead.full_name or "você",
                    "ad_source": lead.ad_source,
                    "ad_name": lead.ad_name or "",
                    "niche": lead.niche or "",
                })
                result = {"message": reply, "action": "continue"}
            elif is_ad_lead:
                # Resposta subsequente de lead de anúncio → qualificação acelerada
                result = self.ai.handle_ad_inbound_reply(history, text)
            else:
                # Lead outbound normal
                result = self.ai.handle_whatsapp_reply(history, text)

            if result["action"] == "disqualify":
                lead.disqualified = True
                lead.disqualify_reason = "rejeitou via whatsapp"
                self.db.commit()
                return None

            reply = result.get("message", "")
            if not reply:
                return None

            self.send_text(phone, reply)

            history.append({"role": "user", "content": text})
            history.append({"role": "assistant", "content": reply, "channel": "whatsapp"})
            lead.whatsapp_conversation = json.dumps(history)
            lead.responded = True
            lead.responded_at = datetime.utcnow()

            if result["action"] == "schedule":
                lead.call_scheduled = True
                lead.call_scheduled_at = datetime.utcnow()
                lead.qualified = True
                # Envia conversão para Meta se vier de anúncio Meta
                if lead.ad_source == "meta":
                    self._send_meta_conversion(lead)
                print(f"[WhatsApp] 📅 Call agendada via WA para @{lead.username}")

            self.db.commit()
            return reply

        except Exception as e:
            print(f"[WhatsApp] Erro ao processar webhook: {e}")
            return None

    def _extract_ad_info(self, data: dict, text: str) -> dict:
        """
        Extrai informações de rastreamento de anúncio do payload do webhook.

        Meta Click-to-WhatsApp envia um objeto 'referral' na mensagem com:
          sourceUrl, sourceId, sourceType, headline, body, ctwaClid
        """
        info: dict = {}

        # Meta referral (Click-to-WhatsApp)
        referral = (
            data.get("message", {}).get("extendedTextMessage", {}).get("contextInfo", {}).get("externalAdReply")
            or data.get("referral")
            or data.get("message", {}).get("referral")
            or {}
        )

        if referral:
            info["ad_source"]   = "meta"
            info["ad_id"]       = referral.get("adId") or referral.get("sourceId", "")
            info["adset_id"]    = referral.get("adsetId", "")
            info["campaign_id"] = referral.get("campaignId", "")
            info["ad_name"]     = referral.get("headline") or referral.get("body", "")
            info["ctwa_clid"]   = referral.get("ctwaClid") or referral.get("clid", "")
            return info

        # Google UTM (via texto pré-preenchido no anúncio)
        from modules.ads.google_ads_client import GoogleAdsClient
        utm = GoogleAdsClient.extract_utm_from_text(text)
        if utm:
            info["ad_source"]   = utm.get("utm_source", "google")
            info["utm_source"]  = utm.get("utm_source")
            info["utm_campaign"]= utm.get("utm_campaign")
            info["utm_medium"]  = utm.get("utm_medium")
            info["campaign_id"] = utm.get("utm_campaign") or utm.get("gclid", "")

        return info

    def _send_meta_conversion(self, lead: Lead) -> None:
        """Envia evento Schedule para Meta Conversions API quando lead agenda."""
        try:
            from modules.ads.meta_client import MetaAdsClient
            from config.settings import META_ACCESS_TOKEN
            if not META_ACCESS_TOKEN:
                return
            meta = MetaAdsClient()
            meta.send_conversion(
                event_name="Schedule",
                phone=lead.phone or "",
                click_id=lead.ctwa_clid,
            )
        except Exception as e:
            print(f"[WhatsApp] Erro ao enviar conversão Meta: {e}")

    # ------------------------------------------------------------------
    # Campanha em lote
    # ------------------------------------------------------------------

    def run_whatsapp_campaign(self, limit: int = 40) -> int:
        """
        Executa campanha de WhatsApp priorizando leads High intent.
        Retorna quantidade de mensagens enviadas.
        """
        # Prioriza High → Medium → Low intent
        leads = (
            self.db.query(Lead)
            .filter(
                Lead.phone != None,
                Lead.whatsapp_contacted == False,
                Lead.whatsapp_invalid == False,
                Lead.disqualified == False,
            )
            .order_by(
                # High intent primeiro
                Lead.intent_score.desc()
            )
            .limit(limit)
            .all()
        )

        print(f"[WhatsApp] 🚀 Campanha WA: {len(leads)} leads")
        sent = 0

        for lead in leads:
            ok = self.send_first_message(lead)
            if ok:
                sent += 1
            secs = random.uniform(DELAY_MIN, DELAY_MAX)
            print(f"[WhatsApp] Aguardando {secs:.0f}s...")
            time.sleep(secs)

        print(f"[WhatsApp] Campanha encerrada: {sent}/{len(leads)} enviadas")
        return sent

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _clean_phone(self, phone: str) -> str:
        """Remove caracteres não numéricos e garante DDI 55 para BR."""
        digits = "".join(filter(str.isdigit, phone))
        if not digits.startswith("55") and len(digits) <= 11:
            digits = "55" + digits
        return digits
