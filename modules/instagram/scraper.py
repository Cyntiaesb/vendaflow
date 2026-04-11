"""
Instagram Finder — busca perfis B2B pelo nome da empresa.

Usado para enriquecer leads Apollo com o handle do Instagram.
NÃO faz mais scraping por hashtag — aquele fluxo foi removido.

Fluxo:
1. Apollo encontra lead (nome + empresa)
2. find_instagram_by_company() busca o handle no Instagram
3. Salva instagram_username no banco
4. InstagramBot usa esse handle para enviar DM
"""

import time
from typing import Optional
from instagrapi import Client
from modules.database.models import Lead, get_session


class InstagramFinder:
    def __init__(self, username: str, password: str):
        self.client = Client()
        self.db = get_session()
        self._login(username, password)

    def _login(self, username: str, password: str):
        try:
            self.client.login(username, password)
            print(f"[Finder] Login OK: @{username}")
        except Exception as e:
            print(f"[Finder] Erro no login: {e}")
            raise

    def find_instagram_by_company(
        self,
        company_name: str,
        fallback_full_name: Optional[str] = None,
    ) -> Optional[str]:
        """
        Busca o handle do Instagram de uma empresa pelo nome.
        Retorna o @username ou None se não encontrar perfil B2B.
        """
        queries = [q for q in [company_name, fallback_full_name] if q]

        for query in queries:
            try:
                results = self.client.search_users(query.strip()[:50])
                for user in results[:5]:
                    try:
                        info = self.client.user_info(user.pk)
                        if info.is_business or (info.category and info.category.strip()):
                            print(f"[Finder] Encontrado: @{info.username} para '{query}'")
                            return info.username
                    except Exception:
                        continue
                time.sleep(2)
            except Exception as e:
                print(f"[Finder] Erro na busca '{query}': {e}")

        return None

    def bulk_find_instagram(self, limit: int = 30) -> int:
        """
        Enriquece leads Apollo sem instagram_username buscando seus perfis.
        Retorna quantidade de handles encontrados.
        """
        leads = (
            self.db.query(Lead)
            .filter(
                Lead.source == "apollo_intent",
                Lead.instagram_username == None,
                Lead.instagram_lookup_tried == False,
                Lead.disqualified == False,
            )
            .limit(limit)
            .all()
        )

        print(f"[Finder] Buscando Instagram de {len(leads)} leads Apollo...")
        found = 0

        for lead in leads:
            lead.instagram_lookup_tried = True
            company = lead.niche if lead.niche and lead.niche != "desconhecido" else None
            handle = self.find_instagram_by_company(
                company_name=company or lead.full_name or "",
                fallback_full_name=lead.full_name if company else None,
            )
            if handle:
                lead.instagram_username = handle
                found += 1
            else:
                lead.instagram_not_found = True
            self.db.commit()
            time.sleep(3)

        print(f"[Finder] Handles encontrados: {found}/{len(leads)}")
        return found
