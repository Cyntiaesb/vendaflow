"""
Apify — scraping de perfis Instagram para análise de leads.

Actor usado: apify/instagram-profile-scraper
Retorna: bio, seguidores, seguindo, posts, categoria, website, email, engagement.

Fluxo:
1. Recebe lista de usernames de seguidores novos
2. Dispara o actor do Apify em batch
3. Aguarda conclusão (polling)
4. Para cada perfil retornado, chama o ClaudeClient para pontuar
5. Atualiza profile_score e intent_score no banco

Custo estimado: ~$0.50 por 1.000 perfis analisados (Apify free tier: 1.000 results/mês)
"""

import time
import json
import requests
from datetime import datetime
from typing import Optional
from modules.database.models import Lead, get_session
from config.settings import APIFY_API_KEY, TARGET_NICHE

BASE_URL = "https://api.apify.com/v2"
ACTOR_ID = "apify~instagram-profile-scraper"


class ApifyClient:
    def __init__(self):
        self.headers = {
            "Authorization": f"Bearer {APIFY_API_KEY}",
            "Content-Type": "application/json",
        }
        self.db = get_session()

    # ── Execução do actor ─────────────────────────────────────────────

    def run_profile_scraper(self, usernames: list[str]) -> Optional[str]:
        """
        Dispara o actor de scraping de perfis no Apify.
        Retorna o run_id para polling posterior, ou None em caso de erro.
        """
        if not APIFY_API_KEY:
            print("[Apify] APIFY_API_KEY não configurada — pulando análise")
            return None

        payload = {
            "usernames": usernames,
            "resultsType": "details",
            "resultsLimit": len(usernames),
            "scrapePostsUntilDate": None,
            "proxy": {"useApifyProxy": True, "apifyProxyGroups": ["RESIDENTIAL"]},
        }

        try:
            resp = requests.post(
                f"{BASE_URL}/acts/{ACTOR_ID}/runs",
                headers=self.headers,
                json=payload,
                timeout=30,
            )
            resp.raise_for_status()
            run_id = resp.json()["data"]["id"]
            print(f"[Apify] Run iniciado: {run_id} ({len(usernames)} perfis)")
            return run_id
        except Exception as e:
            print(f"[Apify] Erro ao iniciar run: {e}")
            return None

    def wait_for_run(self, run_id: str, timeout_secs: int = 300) -> Optional[list]:
        """
        Aguarda conclusão do run e retorna os resultados.
        Polling a cada 10s até timeout.
        """
        start = time.time()
        while time.time() - start < timeout_secs:
            try:
                resp = requests.get(
                    f"{BASE_URL}/actor-runs/{run_id}",
                    headers=self.headers,
                    timeout=15,
                )
                resp.raise_for_status()
                status = resp.json()["data"]["status"]

                if status == "SUCCEEDED":
                    return self._fetch_results(run_id)
                elif status in ("FAILED", "ABORTED", "TIMED-OUT"):
                    print(f"[Apify] Run {run_id} terminou com status: {status}")
                    return None

                print(f"[Apify] Aguardando run {run_id}... status: {status}")
                time.sleep(10)
            except Exception as e:
                print(f"[Apify] Erro ao verificar run: {e}")
                time.sleep(10)

        print(f"[Apify] Timeout aguardando run {run_id}")
        return None

    def _fetch_results(self, run_id: str) -> list:
        """Busca os resultados do dataset do run."""
        try:
            resp = requests.get(
                f"{BASE_URL}/actor-runs/{run_id}/dataset/items",
                headers=self.headers,
                params={"format": "json"},
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            print(f"[Apify] Erro ao buscar resultados: {e}")
            return []

    # ── Pipeline de análise ───────────────────────────────────────────

    def analyze_follower_batch(self, leads: list, niche: str = "") -> int:
        """
        Analisa um batch de leads seguidores.
        1. Extrai usernames
        2. Roda Apify
        3. Para cada resultado, chama Claude para scoring
        4. Atualiza banco
        Retorna quantidade de leads analisados.
        """
        from modules.ai.claude_client import ClaudeClient

        if not leads:
            return 0

        usernames = [l.instagram_username for l in leads if l.instagram_username]
        if not usernames:
            return 0

        print(f"[Apify] Analisando {len(usernames)} perfis...")

        run_id = self.run_profile_scraper(usernames)
        if not run_id:
            return 0

        results = self.wait_for_run(run_id, timeout_secs=600)
        if not results:
            return 0

        # Mapeia username → dados do perfil
        profile_map = {
            r.get("username", "").lower(): r
            for r in results
            if r.get("username")
        }

        ai = ClaudeClient()
        analyzed = 0

        for lead in leads:
            handle = (lead.instagram_username or "").lower()
            profile_data = profile_map.get(handle)

            lead.profile_analyzed = True
            lead.profile_analyzed_at = datetime.utcnow()

            if not profile_data:
                lead.profile_score = "cold"
                lead.profile_score_reason = "Perfil não encontrado no Apify"
                self.db.commit()
                continue

            # Salva dados brutos
            lead.profile_raw_data = json.dumps(profile_data)

            # Claude analisa e pontua
            score_result = ai.score_instagram_profile(
                profile_data=profile_data,
                target_niche=niche or TARGET_NICHE,
            )

            lead.profile_score = score_result["score"]
            lead.profile_score_reason = score_result["reason"]

            # Atualiza intent_score com base no profile_score
            score_to_intent = {"hot": "high", "warm": "medium", "cold": "low"}
            lead.intent_score = score_to_intent.get(score_result["score"], "low")

            # Atualiza nicho se encontrado
            category = profile_data.get("category") or profile_data.get("businessCategoryName")
            if category and not lead.niche:
                lead.niche = category

            self.db.commit()
            analyzed += 1

            print(
                f"[Apify] @{lead.instagram_username}: "
                f"score={lead.profile_score} — {lead.profile_score_reason[:60]}"
            )

        print(f"[Apify] Análise concluída: {analyzed}/{len(leads)} perfis pontuados")
        return analyzed

    # ── Extração de campos úteis do perfil ────────────────────────────

    @staticmethod
    def extract_profile_summary(profile_data: dict) -> dict:
        """
        Extrai campos relevantes do retorno bruto do Apify
        para passar ao Claude de forma limpa.
        """
        return {
            "username":         profile_data.get("username", ""),
            "full_name":        profile_data.get("fullName", ""),
            "bio":              profile_data.get("biography", "")[:300],
            "followers":        profile_data.get("followersCount", 0),
            "following":        profile_data.get("followsCount", 0),
            "posts_count":      profile_data.get("postsCount", 0),
            "is_business":      profile_data.get("isBusinessAccount", False),
            "is_verified":      profile_data.get("verified", False),
            "category":         profile_data.get("category") or profile_data.get("businessCategoryName", ""),
            "website":          profile_data.get("externalUrl", ""),
            "email":            profile_data.get("businessEmail", ""),
            "phone":            profile_data.get("businessPhoneNumber", ""),
            "city":             profile_data.get("businessCity", ""),
            "engagement_rate":  profile_data.get("igtvVideoCount", 0),
            "recent_post_captions": [
                p.get("caption", "")[:100]
                for p in (profile_data.get("latestPosts") or [])[:3]
            ],
        }
