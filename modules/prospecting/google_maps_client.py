"""
Google Maps Places API — prospecção de empresas locais por segmento e cidade.

Fluxo:
1. search_by_segment()  → busca empresas no Google Maps por nicho + cidade
2. save_maps_leads()    → salva leads encontrados no banco
3. bulk_prospect()      → executa busca e salva em lote
"""

import time
import requests
from typing import Optional
from modules.database.models import Lead, get_session
from config.settings import GOOGLE_MAPS_API_KEY

BASE_URL = "https://maps.googleapis.com/maps/api/place"


class GoogleMapsClient:
    def __init__(self):
        self.api_key = GOOGLE_MAPS_API_KEY
        self.session = get_session()

    # ------------------------------------------------------------------
    # 1. Busca de empresas
    # ------------------------------------------------------------------

    def search_by_segment(
        self,
        segment: str,
        city: str,
        limit: int = 50,
    ) -> list[dict]:
        """
        Busca empresas no Google Maps por segmento e cidade.

        Args:
            segment: nicho da empresa (ex: "restaurante", "clínica odontológica")
            city:    cidade-alvo (ex: "São Paulo")
            limit:   máximo de resultados (Google retorna até 60 via paginação)

        Returns:
            lista de dicts com dados brutos da API
        """
        query = f"{segment} em {city}"
        results = []
        next_page_token = None

        print(f"[GoogleMaps] Buscando: '{query}'...")

        while len(results) < limit:
            params = {
                "query": query,
                "key": self.api_key,
                "language": "pt-BR",
            }
            if next_page_token:
                params = {"pagetoken": next_page_token, "key": self.api_key}
                time.sleep(2)  # Google exige delay antes de usar pagetoken

            try:
                resp = requests.get(
                    f"{BASE_URL}/textsearch/json",
                    params=params,
                    timeout=15,
                )
                resp.raise_for_status()
                data = resp.json()

                if data.get("status") not in ("OK", "ZERO_RESULTS"):
                    print(f"[GoogleMaps] Status inesperado: {data.get('status')}")
                    break

                batch = data.get("results", [])
                results.extend(batch)

                next_page_token = data.get("next_page_token")
                if not next_page_token or len(results) >= limit:
                    break

            except Exception as e:
                print(f"[GoogleMaps] Erro na busca: {e}")
                break

        results = results[:limit]
        print(f"[GoogleMaps] {len(results)} empresas encontradas para '{query}'")
        return results

    def get_place_details(self, place_id: str) -> dict:
        """
        Busca detalhes de um lugar: telefone, website, horários.
        Consome 1 crédito extra — usar com critério.
        """
        try:
            resp = requests.get(
                f"{BASE_URL}/details/json",
                params={
                    "place_id": place_id,
                    "fields": "name,formatted_phone_number,website,rating,user_ratings_total,formatted_address",
                    "key": self.api_key,
                    "language": "pt-BR",
                },
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json().get("result", {})
        except Exception as e:
            print(f"[GoogleMaps] Erro ao buscar detalhes ({place_id}): {e}")
            return {}

    # ------------------------------------------------------------------
    # 2. Salvar no banco
    # ------------------------------------------------------------------

    def save_maps_leads(
        self,
        segment: str,
        city: str,
        results: list[dict],
        fetch_details: bool = False,
    ) -> int:
        """
        Salva empresas encontradas no banco como leads.
        Retorna quantidade inserida.
        """
        saved = 0

        for place in results:
            place_id = place.get("place_id", "")
            name = place.get("name", "").strip()

            if not name or not place_id:
                continue

            # Username único baseado no place_id
            username = f"maps_{place_id}"

            exists = self.session.query(Lead).filter_by(username=username).first()
            if exists:
                continue

            phone = None
            website = None

            if fetch_details:
                details = self.get_place_details(place_id)
                phone = details.get("formatted_phone_number")
                website = details.get("website")
                time.sleep(0.5)
            else:
                # Tenta extrair do resultado básico (nem sempre disponível)
                phone = place.get("formatted_phone_number")

            address = place.get("formatted_address") or place.get("vicinity") or city
            rating = place.get("rating")
            total_ratings = place.get("user_ratings_total", 0)

            # Prioridade: empresas com mais avaliações têm presença online maior
            intent = "high" if total_ratings >= 50 else "medium" if total_ratings >= 10 else "low"

            lead = Lead(
                username=username,
                full_name=name,
                niche=segment,
                followers=total_ratings,      # usa total_ratings como proxy de tamanho
                phone=self._clean_phone(phone),
                location=address,
                intent_score=intent,
                source="google_maps",
            )
            self.session.add(lead)
            saved += 1

        self.session.commit()
        print(f"[GoogleMaps] {saved} novos leads salvos (segmento: {segment}, cidade: {city})")
        return saved

    # ------------------------------------------------------------------
    # 3. Pipeline completo
    # ------------------------------------------------------------------

    def bulk_prospect(
        self,
        segment: str,
        city: str,
        limit: int = 50,
        fetch_details: bool = False,
        delay: float = 1.0,
    ) -> int:
        """
        Pipeline completo: busca + salva no banco.

        Args:
            segment:        nicho alvo
            city:           cidade
            limit:          máximo de empresas
            fetch_details:  se True, busca telefone via Place Details (mais créditos)
            delay:          delay entre requisições

        Returns:
            quantidade de leads salvos
        """
        results = self.search_by_segment(segment, city, limit)
        if not results:
            return 0

        time.sleep(delay)
        return self.save_maps_leads(segment, city, results, fetch_details)

    def multi_segment_prospect(
        self,
        segments: list[str],
        city: str,
        limit_per_segment: int = 30,
    ) -> int:
        """
        Prospecta múltiplos segmentos em uma cidade.
        Útil para campanhas multi-nicho.
        """
        total = 0
        for segment in segments:
            saved = self.bulk_prospect(segment, city, limit_per_segment)
            total += saved
            time.sleep(2)  # delay entre segmentos
        print(f"[GoogleMaps] Total geral: {total} leads de {len(segments)} segmentos")
        return total

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _clean_phone(self, phone: Optional[str]) -> Optional[str]:
        """Normaliza número de telefone brasileiro para formato E.164."""
        if not phone:
            return None
        digits = "".join(c for c in phone if c.isdigit())
        if len(digits) == 11 and not digits.startswith("55"):
            digits = "55" + digits
        elif len(digits) == 10 and not digits.startswith("55"):
            digits = "55" + digits
        return digits if len(digits) >= 12 else phone
