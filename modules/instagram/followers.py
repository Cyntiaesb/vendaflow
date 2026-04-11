"""
Follower Monitor — detecta novos seguidores e salva no CRM.

Todo novo seguidor entra no banco com source="instagram_follower".
Depois o ApifyClient analisa o perfil e o Claude decide se é lead quente.
Só leads com profile_score="hot" serão contatados pelo InstagramBot.

Estratégia de detecção de "novo":
- Busca os N seguidores mais recentes via instagrapi
- Compara com o que já existe no banco pelo instagram_username
- Salva os que não existem ainda
- Persiste o timestamp da última verificação em um arquivo local
"""

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Optional
from instagrapi import Client
from modules.database.models import Lead, get_session

# Arquivo que guarda o último estado de seguidores verificados
STATE_FILE = Path("follower_state.json")


class FollowerMonitor:
    def __init__(self, bot_username: str, client: Client):
        self.bot_username = bot_username
        self.client = client
        self.db = get_session()
        self.state = self._load_state()

    # ── Estado persistido ─────────────────────────────────────────────

    def _load_state(self) -> dict:
        if STATE_FILE.exists():
            try:
                return json.loads(STATE_FILE.read_text())
            except Exception:
                pass
        return {"last_follower_ids": [], "last_check": None}

    def _save_state(self, follower_ids: list) -> None:
        self.state["last_follower_ids"] = follower_ids
        self.state["last_check"] = datetime.utcnow().isoformat()
        STATE_FILE.write_text(json.dumps(self.state))

    # ── Detecção de novos seguidores ──────────────────────────────────

    def check_new_followers(self, fetch_limit: int = 100) -> int:
        """
        Busca os N seguidores mais recentes.
        Compara com o último estado salvo e salva os novos no CRM.
        Retorna quantidade de novos seguidores adicionados.
        """
        print(f"[Followers @{self.bot_username}] Verificando novos seguidores...")

        try:
            user_id = self.client.user_id
            followers = self.client.user_followers(user_id, amount=fetch_limit)
        except Exception as e:
            print(f"[Followers] Erro ao buscar seguidores: {e}")
            return 0

        current_ids = [str(uid) for uid in followers.keys()]
        last_ids = set(self.state.get("last_follower_ids", []))
        new_ids = [uid for uid in current_ids if uid not in last_ids]

        if not new_ids:
            print(f"[Followers] Nenhum seguidor novo.")
            self._save_state(current_ids[:500])  # guarda os 500 mais recentes
            return 0

        print(f"[Followers] {len(new_ids)} novo(s) seguidor(es) detectado(s)")
        saved = 0

        for uid in new_ids:
            user_data = followers.get(int(uid))
            if not user_data:
                continue

            username = getattr(user_data, "username", None)
            if not username:
                continue

            # Verifica se já existe no banco
            exists = self.db.query(Lead).filter(
                Lead.instagram_username == username
            ).first()
            if exists:
                continue

            # Salva como lead novo — sem análise ainda
            lead = Lead(
                username=f"follower_{username}",
                full_name=getattr(user_data, "full_name", None) or username,
                instagram_username=username,
                instagram_lookup_tried=True,
                source="instagram_follower",
                intent_score="low",      # será atualizado após análise Apify
                profile_analyzed=False,  # pendente de análise
            )
            self.db.add(lead)
            saved += 1
            time.sleep(0.5)

        self.db.commit()
        self._save_state(current_ids[:500])
        print(f"[Followers] {saved} novos seguidores salvos no CRM")
        return saved

    # ── Fila de análise ───────────────────────────────────────────────

    def get_pending_analysis(self, limit: int = 50) -> list:
        """
        Retorna lista de usernames de seguidores que ainda não
        foram analisados pelo Apify.
        """
        leads = (
            self.db.query(Lead)
            .filter(
                Lead.source == "instagram_follower",
                Lead.profile_analyzed == False,
                Lead.disqualified == False,
            )
            .limit(limit)
            .all()
        )
        return leads
