"""
Meta Marketing API — gestão e otimização de campanhas.

Funcionalidades:
- Buscar performance de campanhas/anúncios
- Calcular CPA (custo por agendamento) por anúncio
- Pausar anúncios com CPA acima do limite
- Aumentar budget de anúncios com boa performance
- Registrar conversões (agendamentos) via Conversions API
"""

import requests
from datetime import datetime, timedelta
from typing import Optional
from config.settings import (
    META_ACCESS_TOKEN,
    META_AD_ACCOUNT_ID,
    META_API_VERSION,
)

BASE = f"https://graph.facebook.com/{META_API_VERSION}"


class MetaAdsClient:

    # ── Insights de campanha ──────────────────────────────────────────

    def get_campaigns(self) -> list:
        """Lista campanhas ativas com status e objetivo."""
        try:
            resp = requests.get(
                f"{BASE}/act_{META_AD_ACCOUNT_ID}/campaigns",
                params={
                    "access_token": META_ACCESS_TOKEN,
                    "fields": "id,name,status,objective,daily_budget,lifetime_budget",
                    "filtering": '[{"field":"effective_status","operator":"IN","value":["ACTIVE","PAUSED"]}]',
                    "limit": 50,
                },
                timeout=15,
            )
            resp.raise_for_status()
            return resp.json().get("data", [])
        except Exception as e:
            print(f"[Meta] Erro ao listar campanhas: {e}")
            return []

    def get_campaign_insights(
        self,
        campaign_id: str,
        days: int = 7,
    ) -> dict:
        """
        Retorna métricas da campanha nos últimos N dias.
        Inclui: spend, impressions, clicks, cpc, ctr, leads.
        """
        since = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
        until = datetime.utcnow().strftime("%Y-%m-%d")

        try:
            resp = requests.get(
                f"{BASE}/{campaign_id}/insights",
                params={
                    "access_token": META_ACCESS_TOKEN,
                    "fields": "spend,impressions,clicks,cpc,ctr,actions,cost_per_action_type",
                    "time_range": f'{{"since":"{since}","until":"{until}"}}',
                    "level": "campaign",
                },
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json().get("data", [])
            return data[0] if data else {}
        except Exception as e:
            print(f"[Meta] Erro nos insights da campanha {campaign_id}: {e}")
            return {}

    def get_all_ads_insights(self, days: int = 7) -> list:
        """
        Retorna métricas de todos os anúncios ativos nos últimos N dias.
        Usado pelo optimizer para decidir o que pausar/escalar.
        """
        since = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
        until = datetime.utcnow().strftime("%Y-%m-%d")

        try:
            resp = requests.get(
                f"{BASE}/act_{META_AD_ACCOUNT_ID}/insights",
                params={
                    "access_token": META_ACCESS_TOKEN,
                    "fields": "ad_id,ad_name,adset_id,campaign_id,campaign_name,spend,impressions,clicks,cpc,actions",
                    "time_range": f'{{"since":"{since}","until":"{until}"}}',
                    "level": "ad",
                    "limit": 100,
                },
                timeout=20,
            )
            resp.raise_for_status()
            return resp.json().get("data", [])
        except Exception as e:
            print(f"[Meta] Erro ao buscar insights dos anúncios: {e}")
            return []

    # ── Controle de anúncios ──────────────────────────────────────────

    def pause_ad(self, ad_id: str) -> bool:
        """Pausa um anúncio específico."""
        try:
            resp = requests.post(
                f"{BASE}/{ad_id}",
                params={"access_token": META_ACCESS_TOKEN},
                json={"status": "PAUSED"},
                timeout=10,
            )
            resp.raise_for_status()
            print(f"[Meta] Anúncio {ad_id} pausado.")
            return True
        except Exception as e:
            print(f"[Meta] Erro ao pausar anúncio {ad_id}: {e}")
            return False

    def update_daily_budget(self, campaign_id: str, new_budget_cents: int) -> bool:
        """
        Atualiza o budget diário de uma campanha.
        new_budget_cents: valor em centavos (R$ 50,00 = 5000)
        """
        try:
            resp = requests.post(
                f"{BASE}/{campaign_id}",
                params={"access_token": META_ACCESS_TOKEN},
                json={"daily_budget": str(new_budget_cents)},
                timeout=10,
            )
            resp.raise_for_status()
            reais = new_budget_cents / 100
            print(f"[Meta] Budget de {campaign_id} atualizado para R$ {reais:.2f}/dia")
            return True
        except Exception as e:
            print(f"[Meta] Erro ao atualizar budget {campaign_id}: {e}")
            return False

    # ── Conversions API ───────────────────────────────────────────────

    def send_conversion(
        self,
        event_name: str,
        phone: str,
        value: float = 0.0,
        currency: str = "BRL",
        click_id: Optional[str] = None,
    ) -> bool:
        """
        Envia evento de conversão para o Meta via Conversions API.
        Usar quando lead agendou (event_name='Schedule') ou fechou (event_name='Purchase').

        phone: número no formato E.164 (+5511999999999)
        click_id: ctwa_clid recebido no webhook do WhatsApp
        """
        import hashlib

        def sha256(value: str) -> str:
            return hashlib.sha256(value.strip().lower().encode()).hexdigest()

        pixel_id = META_AD_ACCOUNT_ID  # usa o mesmo account ID como pixel ID se não configurado separado
        endpoint = f"{BASE}/{pixel_id}/events"

        user_data: dict = {}
        if phone:
            clean = "".join(filter(str.isdigit, phone))
            if not clean.startswith("55"):
                clean = "55" + clean
            user_data["ph"] = [sha256(clean)]
        if click_id:
            user_data["ctwa_clid"] = click_id

        payload = {
            "access_token": META_ACCESS_TOKEN,
            "data": [
                {
                    "event_name": event_name,
                    "event_time": int(datetime.utcnow().timestamp()),
                    "action_source": "other",
                    "user_data": user_data,
                    "custom_data": {
                        "value": value,
                        "currency": currency,
                    },
                }
            ],
        }

        try:
            resp = requests.post(endpoint, json=payload, timeout=15)
            resp.raise_for_status()
            print(f"[Meta] Conversão '{event_name}' enviada para pixel.")
            return True
        except Exception as e:
            print(f"[Meta] Erro ao enviar conversão: {e}")
            return False

    # ── Helpers ───────────────────────────────────────────────────────

    @staticmethod
    def extract_leads_count(insights: dict) -> int:
        """Extrai quantidade de leads/mensagens das actions do insight."""
        actions = insights.get("actions") or []
        for action in actions:
            if action.get("action_type") in (
                "onsite_conversion.messaging_conversation_started_7d",
                "lead",
                "omni_initiated_checkout",
            ):
                return int(action.get("value", 0))
        return 0

    @staticmethod
    def extract_spend(insights: dict) -> float:
        return float(insights.get("spend") or 0)
