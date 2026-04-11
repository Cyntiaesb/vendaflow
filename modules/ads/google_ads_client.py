"""
Google Ads API — gestão de campanhas.

Usa google-ads-python SDK via REST simplificado.
Para campanhas que direcionam para WhatsApp via landing page com UTM params.

Fluxo típico:
  Google Ad → Landing Page (?utm_source=google&utm_campaign=ID) → Botão WhatsApp
  → webhook Evolution recebe utm_campaign no referral ou no texto da mensagem
"""

import requests
from typing import Optional
from config.settings import (
    GOOGLE_ADS_DEVELOPER_TOKEN,
    GOOGLE_ADS_CUSTOMER_ID,
    GOOGLE_ADS_ACCESS_TOKEN,
)

# Google Ads REST API (mais simples que o SDK gRPC)
BASE = "https://googleads.googleapis.com/v16"


class GoogleAdsClient:

    def __init__(self):
        self.headers = {
            "Authorization": f"Bearer {GOOGLE_ADS_ACCESS_TOKEN}",
            "developer-token": GOOGLE_ADS_DEVELOPER_TOKEN,
            "Content-Type": "application/json",
        }
        self.customer_id = GOOGLE_ADS_CUSTOMER_ID.replace("-", "")

    # ── Buscar campanhas ──────────────────────────────────────────────

    def get_campaigns(self) -> list:
        """Lista campanhas ativas com métricas dos últimos 7 dias."""
        query = """
            SELECT
              campaign.id,
              campaign.name,
              campaign.status,
              campaign.advertising_channel_type,
              metrics.clicks,
              metrics.impressions,
              metrics.cost_micros,
              metrics.conversions,
              metrics.ctr,
              metrics.average_cpc
            FROM campaign
            WHERE campaign.status IN ('ENABLED', 'PAUSED')
              AND segments.date DURING LAST_7_DAYS
            ORDER BY metrics.cost_micros DESC
            LIMIT 50
        """
        try:
            resp = requests.post(
                f"{BASE}/customers/{self.customer_id}/googleAds:searchStream",
                headers=self.headers,
                json={"query": query},
                timeout=20,
            )
            resp.raise_for_status()

            campaigns = []
            for batch in resp.json():
                for result in batch.get("results", []):
                    c = result.get("campaign", {})
                    m = result.get("metrics", {})
                    campaigns.append({
                        "id": c.get("id"),
                        "name": c.get("name"),
                        "status": c.get("status"),
                        "channel": c.get("advertisingChannelType"),
                        "clicks": int(m.get("clicks") or 0),
                        "impressions": int(m.get("impressions") or 0),
                        "cost_brl": round(int(m.get("costMicros") or 0) / 1_000_000, 2),
                        "conversions": float(m.get("conversions") or 0),
                        "ctr": round(float(m.get("ctr") or 0) * 100, 2),
                        "avg_cpc_brl": round(int(m.get("averageCpc") or 0) / 1_000_000, 2),
                    })
            return campaigns

        except Exception as e:
            print(f"[Google Ads] Erro ao buscar campanhas: {e}")
            return []

    def get_ad_groups(self, campaign_id: str) -> list:
        """Lista grupos de anúncios de uma campanha com métricas."""
        query = f"""
            SELECT
              ad_group.id,
              ad_group.name,
              ad_group.status,
              metrics.clicks,
              metrics.cost_micros,
              metrics.conversions
            FROM ad_group
            WHERE campaign.id = {campaign_id}
              AND ad_group.status = 'ENABLED'
              AND segments.date DURING LAST_7_DAYS
        """
        try:
            resp = requests.post(
                f"{BASE}/customers/{self.customer_id}/googleAds:searchStream",
                headers=self.headers,
                json={"query": query},
                timeout=15,
            )
            resp.raise_for_status()
            results = []
            for batch in resp.json():
                for r in batch.get("results", []):
                    ag = r.get("adGroup", {})
                    m = r.get("metrics", {})
                    results.append({
                        "id": ag.get("id"),
                        "name": ag.get("name"),
                        "clicks": int(m.get("clicks") or 0),
                        "cost_brl": round(int(m.get("costMicros") or 0) / 1_000_000, 2),
                        "conversions": float(m.get("conversions") or 0),
                    })
            return results
        except Exception as e:
            print(f"[Google Ads] Erro ao buscar ad groups: {e}")
            return []

    # ── Controle de campanhas ─────────────────────────────────────────

    def pause_campaign(self, campaign_id: str) -> bool:
        """Pausa uma campanha Google Ads."""
        try:
            resp = requests.post(
                f"{BASE}/customers/{self.customer_id}/campaigns:mutate",
                headers=self.headers,
                json={
                    "operations": [
                        {
                            "update": {
                                "resourceName": f"customers/{self.customer_id}/campaigns/{campaign_id}",
                                "status": "PAUSED",
                            },
                            "updateMask": "status",
                        }
                    ]
                },
                timeout=10,
            )
            resp.raise_for_status()
            print(f"[Google Ads] Campanha {campaign_id} pausada.")
            return True
        except Exception as e:
            print(f"[Google Ads] Erro ao pausar campanha {campaign_id}: {e}")
            return False

    def update_campaign_budget(
        self, campaign_budget_resource: str, new_amount_micros: int
    ) -> bool:
        """
        Atualiza o orçamento de uma campanha.
        new_amount_micros: valor em micros (R$ 50,00 = 50_000_000)
        """
        try:
            resp = requests.post(
                f"{BASE}/customers/{self.customer_id}/campaignBudgets:mutate",
                headers=self.headers,
                json={
                    "operations": [
                        {
                            "update": {
                                "resourceName": campaign_budget_resource,
                                "amountMicros": str(new_amount_micros),
                            },
                            "updateMask": "amount_micros",
                        }
                    ]
                },
                timeout=10,
            )
            resp.raise_for_status()
            reais = new_amount_micros / 1_000_000
            print(f"[Google Ads] Budget atualizado para R$ {reais:.2f}/dia")
            return True
        except Exception as e:
            print(f"[Google Ads] Erro ao atualizar budget: {e}")
            return False

    # ── Keywords ──────────────────────────────────────────────────────

    def get_keywords_performance(self) -> list:
        """Lista todas as keywords ativas com métricas dos últimos 7 dias."""
        query = """
            SELECT
              ad_group_criterion.keyword.text,
              ad_group_criterion.keyword.match_type,
              ad_group_criterion.status,
              campaign.name,
              ad_group.name,
              metrics.clicks,
              metrics.impressions,
              metrics.cost_micros,
              metrics.conversions,
              metrics.ctr,
              metrics.average_cpc,
              metrics.search_impression_share
            FROM ad_group_criterion
            WHERE ad_group_criterion.type = 'KEYWORD'
              AND ad_group_criterion.status = 'ENABLED'
              AND campaign.status = 'ENABLED'
              AND segments.date DURING LAST_7_DAYS
            ORDER BY metrics.clicks DESC
            LIMIT 100
        """
        try:
            resp = requests.post(
                f"{BASE}/customers/{self.customer_id}/googleAds:searchStream",
                headers=self.headers,
                json={"query": query},
                timeout=20,
            )
            resp.raise_for_status()
            keywords = []
            for batch in resp.json():
                for r in batch.get("results", []):
                    kw = r.get("adGroupCriterion", {}).get("keyword", {})
                    m  = r.get("metrics", {})
                    keywords.append({
                        "keyword":     kw.get("text", ""),
                        "match_type":  kw.get("matchType", ""),
                        "campaign":    r.get("campaign", {}).get("name", ""),
                        "ad_group":    r.get("adGroup", {}).get("name", ""),
                        "clicks":      int(m.get("clicks") or 0),
                        "impressions": int(m.get("impressions") or 0),
                        "cost_brl":    round(int(m.get("costMicros") or 0) / 1_000_000, 2),
                        "conversions": float(m.get("conversions") or 0),
                        "ctr":         round(float(m.get("ctr") or 0) * 100, 2),
                        "avg_cpc_brl": round(int(m.get("averageCpc") or 0) / 1_000_000, 2),
                        "impression_share": round(float(m.get("searchImpressionShare") or 0) * 100, 1),
                    })
            return keywords
        except Exception as e:
            print(f"[Google Ads] Erro ao buscar keywords: {e}")
            return []

    def get_keyword_ideas(self, seed_keywords: list, language_id: str = "1014", country_code: str = "BR") -> list:
        """
        Busca sugestões de keywords via Keyword Planner.
        seed_keywords: lista de palavras-chave base (ex: APOLLO_INTENT_KEYWORDS)
        language_id: 1014 = Português
        """
        try:
            resp = requests.post(
                f"{BASE}/customers/{self.customer_id}:generateKeywordIdeas",
                headers=self.headers,
                json={
                    "keywordSeed": {"keywords": seed_keywords[:10]},
                    "language": f"languageConstants/{language_id}",
                    "geoTargetConstants": [f"geoTargetConstants/2076"],  # Brasil
                    "includeAdultKeywords": False,
                    "keywordPlanNetwork": "GOOGLE_SEARCH",
                    "pageSize": 50,
                },
                timeout=20,
            )
            resp.raise_for_status()
            ideas = []
            for r in resp.json().get("results", []):
                kw = r.get("text", "")
                m  = r.get("keywordIdeaMetrics", {})
                ideas.append({
                    "keyword":          kw,
                    "avg_monthly_searches": int(m.get("avgMonthlySearches") or 0),
                    "competition":      m.get("competition", "UNSPECIFIED"),
                    "low_cpc_brl":      round(int(m.get("lowTopOfPageBidMicros") or 0) / 1_000_000, 2),
                    "high_cpc_brl":     round(int(m.get("highTopOfPageBidMicros") or 0) / 1_000_000, 2),
                })
            return sorted(ideas, key=lambda x: x["avg_monthly_searches"], reverse=True)
        except Exception as e:
            print(f"[Google Ads] Erro ao buscar keyword ideas: {e}")
            return []

    def add_keywords_to_ad_group(self, ad_group_id: str, keywords: list, match_type: str = "BROAD") -> bool:
        """
        Adiciona keywords a um grupo de anúncios existente.
        match_type: BROAD | PHRASE | EXACT
        keywords: lista de strings
        """
        operations = [
            {
                "create": {
                    "adGroup": f"customers/{self.customer_id}/adGroups/{ad_group_id}",
                    "keyword": {"text": kw, "matchType": match_type},
                    "status": "ENABLED",
                }
            }
            for kw in keywords
        ]
        try:
            resp = requests.post(
                f"{BASE}/customers/{self.customer_id}/adGroupCriteria:mutate",
                headers=self.headers,
                json={"operations": operations},
                timeout=15,
            )
            resp.raise_for_status()
            print(f"[Google Ads] {len(keywords)} keywords adicionadas ao grupo {ad_group_id}")
            return True
        except Exception as e:
            print(f"[Google Ads] Erro ao adicionar keywords: {e}")
            return False

    # ── Rastrear UTM de lead via WhatsApp ─────────────────────────────

    @staticmethod
    def extract_utm_from_text(text: str) -> dict:
        """
        Extrai parâmetros UTM de um texto de mensagem.
        Leads do Google costumam incluir UTMs no texto pré-preenchido do ad.
        Ex: "Vim pelo anúncio utm_campaign=search_sp utm_medium=cpc"
        """
        import re
        params = {}
        for key in ("utm_source", "utm_medium", "utm_campaign", "utm_content", "gclid"):
            match = re.search(rf"{key}[=:]([^\s&]+)", text, re.IGNORECASE)
            if match:
                params[key] = match.group(1)
        return params
