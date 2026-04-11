"""
Otimizador de anúncios — roda todo dia às 07:30 (antes das campanhas de outreach).

Lógica:
1. Busca performance dos anúncios Meta e Google dos últimos 7 dias
2. Cruza com leads/agendamentos do banco (rastreados por ad_id)
3. Calcula CPA real (custo por agendamento confirmado)
4. Pausa anúncios acima do CPA máximo configurado
5. Aumenta budget dos anúncios com CPA abaixo do ideal
6. Gera relatório salvo no banco (AdReport)
"""

from datetime import datetime
from modules.ads.meta_client import MetaAdsClient
from modules.ads.google_ads_client import GoogleAdsClient
from modules.database.models import Lead, AdReport, get_session
from config.settings import (
    META_ACCESS_TOKEN,
    GOOGLE_ADS_ACCESS_TOKEN,
    ADS_MAX_CPA_BRL,
    ADS_SCALE_BUDGET_PCT,
    ADS_MIN_SPEND_TO_EVALUATE,
)


class AdOptimizer:

    def __init__(self):
        self.db = get_session()
        self.meta = MetaAdsClient() if META_ACCESS_TOKEN else None
        self.google = GoogleAdsClient() if GOOGLE_ADS_ACCESS_TOKEN else None

    # ── Entry point ───────────────────────────────────────────────────

    def run(self) -> dict:
        """
        Executa o ciclo completo de otimização.
        Retorna resumo das ações tomadas.
        """
        results = {
            "meta": self._optimize_meta(),
            "google": self._optimize_google(),
            "timestamp": datetime.utcnow().isoformat(),
        }
        self._save_report(results)
        print(f"[Optimizer] Ciclo concluído: {results}")
        return results

    # ── Meta ──────────────────────────────────────────────────────────

    def _optimize_meta(self) -> dict:
        if not self.meta:
            return {"skipped": True, "reason": "META_ACCESS_TOKEN não configurado"}

        ads_data = self.meta.get_all_ads_insights(days=7)
        paused, scaled, evaluated = [], [], []

        for ad in ads_data:
            ad_id = ad.get("ad_id", "")
            ad_name = ad.get("ad_name", "")
            spend = MetaAdsClient.extract_spend(ad)

            # Ignora anúncios com gasto abaixo do mínimo (poucos dados)
            if spend < ADS_MIN_SPEND_TO_EVALUATE:
                continue

            # Conta agendamentos rastreados deste anúncio
            schedulings = (
                self.db.query(Lead)
                .filter(
                    Lead.ad_id == ad_id,
                    Lead.call_scheduled == True,
                )
                .count()
            )

            evaluated.append(ad_name)
            cpa = spend / schedulings if schedulings > 0 else float("inf")

            print(
                f"[Meta] {ad_name}: R${spend:.2f} gasto, "
                f"{schedulings} agendamentos, CPA=R${cpa:.2f}"
            )

            if cpa > ADS_MAX_CPA_BRL and schedulings == 0:
                # CPA acima do limite ou zero conversão com gasto relevante → pausa
                ok = self.meta.pause_ad(ad_id)
                if ok:
                    paused.append({"id": ad_id, "name": ad_name, "cpa": cpa, "spend": spend})

            elif cpa < ADS_MAX_CPA_BRL * 0.6 and schedulings >= 2:
                # CPA ótimo (< 60% do máximo) com pelo menos 2 conversões → escala budget
                # Busca o campaign_id do anúncio para ajustar budget
                campaign_id = ad.get("campaign_id", "")
                if campaign_id:
                    current_budget = self._get_meta_campaign_budget(campaign_id)
                    if current_budget > 0:
                        new_budget = int(current_budget * (1 + ADS_SCALE_BUDGET_PCT / 100))
                        ok = self.meta.update_daily_budget(campaign_id, new_budget)
                        if ok:
                            scaled.append({
                                "id": campaign_id,
                                "name": ad_name,
                                "cpa": cpa,
                                "budget_increase_pct": ADS_SCALE_BUDGET_PCT,
                            })

        return {
            "evaluated": len(evaluated),
            "paused": paused,
            "scaled": scaled,
        }

    def _get_meta_campaign_budget(self, campaign_id: str) -> int:
        """Busca o budget diário atual da campanha em centavos."""
        try:
            import requests
            from config.settings import META_ACCESS_TOKEN, META_API_VERSION
            resp = requests.get(
                f"https://graph.facebook.com/{META_API_VERSION}/{campaign_id}",
                params={
                    "access_token": META_ACCESS_TOKEN,
                    "fields": "daily_budget",
                },
                timeout=10,
            )
            resp.raise_for_status()
            return int(resp.json().get("daily_budget") or 0)
        except Exception:
            return 0

    # ── Google ────────────────────────────────────────────────────────

    def _optimize_google(self) -> dict:
        if not self.google:
            return {"skipped": True, "reason": "GOOGLE_ADS_ACCESS_TOKEN não configurado"}

        campaigns = self.google.get_campaigns()
        paused, evaluated = [], []

        for c in campaigns:
            if c["cost_brl"] < ADS_MIN_SPEND_TO_EVALUATE:
                continue

            campaign_id = c["id"]
            spend = c["cost_brl"]

            # Conta agendamentos rastreados desta campanha Google
            schedulings = (
                self.db.query(Lead)
                .filter(
                    Lead.utm_campaign == str(campaign_id),
                    Lead.call_scheduled == True,
                )
                .count()
            )

            evaluated.append(c["name"])
            cpa = spend / schedulings if schedulings > 0 else float("inf")

            print(
                f"[Google] {c['name']}: R${spend:.2f} gasto, "
                f"{schedulings} agendamentos, CPA=R${cpa:.2f}"
            )

            if cpa > ADS_MAX_CPA_BRL and schedulings == 0:
                ok = self.google.pause_campaign(campaign_id)
                if ok:
                    paused.append({"id": campaign_id, "name": c["name"], "cpa": cpa})

        return {
            "evaluated": len(evaluated),
            "paused": paused,
        }

    # ── Relatório ─────────────────────────────────────────────────────

    def _save_report(self, results: dict) -> None:
        """Salva o relatório da otimização no banco."""
        import json
        try:
            report = AdReport(
                platform="all",
                action="optimize",
                details=json.dumps(results),
                created_at=datetime.utcnow(),
            )
            self.db.add(report)
            self.db.commit()
        except Exception as e:
            print(f"[Optimizer] Erro ao salvar relatório: {e}")
