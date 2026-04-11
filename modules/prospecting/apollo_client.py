"""
Apollo.io integration — purchase intent search + lead enrichment.

Fluxo:
1. search_by_intent()  → busca pessoas/empresas por keywords de intenção
2. enrich_lead()       → adiciona telefone, email e score ao lead existente
3. bulk_enrich()       → processa fila de leads sem contato ainda
"""

import time
import requests
from typing import Optional
from modules.database.models import Lead, get_session
from config.settings import APOLLO_API_KEY

BASE_URL = "https://api.apollo.io/v1"


class ApolloClient:
    def __init__(self):
        self.headers = {
            "Content-Type": "application/json",
            "Cache-Control": "no-cache",
            "X-Api-Key": APOLLO_API_KEY,
        }
        self.session = get_session()

    # ------------------------------------------------------------------
    # 1. Purchase Intent Search
    # ------------------------------------------------------------------

    def search_by_intent(
        self,
        keywords: list[str],
        location: Optional[str] = None,
        intent_score: str = "high",         # "high" | "medium" | "low"
        limit: int = 100,
    ) -> list[dict]:
        """
        Busca leads com intenção de compra ativa baseada em keywords.

        Args:
            keywords:     termos que a pessoa pesquisou (ex: ["automação whatsapp"])
            location:     cidade/estado (ex: "São Paulo, BR")
            intent_score: prioridade mínima do intent
            limit:        máximo de leads retornados

        Returns:
            lista de dicts com dados brutos da API
        """
        score_map = {"high": 3, "medium": 2, "low": 1}
        min_score = score_map.get(intent_score, 2)

        payload = {
            "q_keywords": " OR ".join(keywords),
            "prospected_by_current_team": ["no"],
            "per_page": min(limit, 100),
            "page": 1,
            "person_titles": [],           # sem filtro de cargo por padrão
            "contact_email_status": ["verified", "guessed", "unavailable"],
        }

        if location:
            payload["person_locations"] = [location]

        # Filtro de intent via topic signals
        payload["q_organization_intent_topics"] = keywords
        payload["organization_intent_lookback_days"] = 7
        payload["organization_intent_min_score"] = min_score

        try:
            resp = requests.post(
                f"{BASE_URL}/mixed_people/search",
                headers=self.headers,
                json=payload,
                timeout=20,
            )
            resp.raise_for_status()
            data = resp.json()
            contacts = data.get("people", []) or data.get("contacts", [])
            print(
                f"[Apollo] Intent search → {len(contacts)} leads "
                f"(keywords: {keywords}, score: {intent_score})"
            )
            return contacts
        except Exception as e:
            print(f"[Apollo] Erro na busca por intent: {e}")
            return []

    def save_intent_leads(
        self,
        keywords: list[str],
        location: Optional[str] = None,
        intent_score: str = "high",
        limit: int = 100,
    ) -> int:
        """Executa search_by_intent e salva no banco. Retorna qtd inserida."""
        contacts = self.search_by_intent(keywords, location, intent_score, limit)
        saved = 0

        for c in contacts:
            # Monta username a partir do LinkedIn ou nome
            username = self._derive_username(c)
            if not username:
                continue

            exists = self.session.query(Lead).filter_by(username=username).first()
            if exists:
                continue

            phone = self._extract_phone(c)
            email = self._extract_email(c)

            lead = Lead(
                username=username,
                full_name=c.get("name") or f"{c.get('first_name','')} {c.get('last_name','')}".strip(),
                niche=self._extract_niche(c),
                followers=0,                        # N/A para leads Apollo
                phone=phone,
                email=email,
                intent_score=intent_score,
                source="apollo_intent",
                location=location or "",
            )
            self.session.add(lead)
            saved += 1

        self.session.commit()
        print(f"[Apollo] {saved} novos leads de intent salvos no banco")
        return saved

    # ------------------------------------------------------------------
    # 2. Lead Enrichment
    # ------------------------------------------------------------------

    def enrich_lead(self, lead: Lead) -> bool:
        """
        Enriquece um lead existente com telefone, email e score via Apollo.
        Retorna True se encontrou dados úteis.
        """
        if not lead.full_name:
            return False

        name_parts = lead.full_name.strip().split()
        first = name_parts[0] if name_parts else ""
        last = " ".join(name_parts[1:]) if len(name_parts) > 1 else ""

        payload = {
            "first_name": first,
            "last_name": last,
            "reveal_personal_emails": True,
            "reveal_phone_number": True,
        }

        # Tenta usar domínio da empresa se disponível
        if lead.niche:
            payload["organization_name"] = lead.niche

        try:
            resp = requests.post(
                f"{BASE_URL}/people/match",
                headers=self.headers,
                json=payload,
                timeout=15,
            )
            resp.raise_for_status()
            person = resp.json().get("person") or {}

            phone = self._extract_phone(person)
            email = self._extract_email(person)

            if not phone and not email:
                return False

            if phone and not lead.phone:
                lead.phone = phone
            if email and not lead.email:
                lead.email = email

            # Score de seniority como proxy de qualidade
            seniority = person.get("seniority", "")
            if seniority in ("director", "vp", "c_suite", "owner", "founder"):
                lead.intent_score = "high"
            elif seniority in ("manager", "senior"):
                lead.intent_score = "medium"
            elif not lead.intent_score:
                lead.intent_score = "low"

            self.session.commit()
            print(
                f"[Apollo] Enriquecido @{lead.username}: "
                f"tel={'✓' if phone else '✗'}  email={'✓' if email else '✗'}"
            )
            return True

        except Exception as e:
            print(f"[Apollo] Erro ao enriquecer @{lead.username}: {e}")
            return False

    def bulk_enrich(self, limit: int = 50, delay: float = 1.2) -> int:
        """
        Enriquece em lote leads que ainda não têm telefone/email.
        Respeita rate-limit do Apollo (≈1 req/s no plano básico).
        """
        leads = (
            self.session.query(Lead)
            .filter(
                Lead.contacted == False,
                Lead.disqualified == False,
                Lead.phone == None,
                Lead.email == None,
            )
            .limit(limit)
            .all()
        )

        print(f"[Apollo] Iniciando enriquecimento de {len(leads)} leads...")
        enriched = 0

        for lead in leads:
            ok = self.enrich_lead(lead)
            if ok:
                enriched += 1
            time.sleep(delay)

        print(f"[Apollo] Enriquecimento concluído: {enriched}/{len(leads)}")
        return enriched

    # ------------------------------------------------------------------
    # Helpers privados
    # ------------------------------------------------------------------

    def _derive_username(self, contact: dict) -> Optional[str]:
        """Gera um username único a partir dos dados do Apollo."""
        linkedin = contact.get("linkedin_url", "")
        if linkedin:
            slug = linkedin.rstrip("/").split("/")[-1]
            if slug:
                return f"apollo_{slug}"

        name = contact.get("name") or ""
        if name:
            slug = name.lower().replace(" ", "_")[:40]
            return f"apollo_{slug}"

        return None

    def _extract_phone(self, contact: dict) -> Optional[str]:
        phones = contact.get("phone_numbers") or []
        for p in phones:
            if isinstance(p, dict) and p.get("sanitized_number"):
                return p["sanitized_number"]
        return contact.get("phone_number") or None

    def _extract_email(self, contact: dict) -> Optional[str]:
        email = contact.get("email")
        if email and "@" in email:
            return email
        for e in contact.get("email_addresses") or []:
            if isinstance(e, dict) and e.get("email"):
                return e["email"]
        return None

    def _extract_niche(self, contact: dict) -> str:
        org = contact.get("organization") or {}
        industry = org.get("industry") or contact.get("organization_industry") or ""
        title = contact.get("title") or ""
        return industry or title or "desconhecido"
