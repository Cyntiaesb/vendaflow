"""
Instagram Session Manager — previne bans por login frequente.

Problemas que resolve:
1. Login repetido a cada reinicialização → principal trigger de ban
2. Múltiplas contas no mesmo IP → detecção de automação
3. Checkpoint/challenge sem handler → bot para silenciosamente
4. Device fingerprint inconsistente → flag de automação

Uso:
    from modules.instagram.session_manager import get_instagram_client
    client = get_instagram_client(username, password, proxy="http://user:pass@host:port")
"""

import json
import logging
from pathlib import Path
from typing import Optional
from instagrapi import Client
from instagrapi.exceptions import (
    ChallengeRequired,
    LoginRequired,
    BadPassword,
    TwoFactorRequired,
)
from config.settings import ALERT_EMAIL, EMAIL_FROM_ADDRESS, SENDGRID_API_KEY

logger = logging.getLogger(__name__)

SESSIONS_DIR = Path("sessions")
SESSIONS_DIR.mkdir(exist_ok=True)


def get_instagram_client(
    username: str,
    password: str,
    proxy: Optional[str] = None,
) -> Client:
    """
    Retorna um Client instagrapi autenticado.
    Reutiliza sessão salva se disponível.
    """
    client = Client()
    client.delay_range = [2, 5]  # delay mínimo entre requisições

    if proxy:
        client.set_proxy(proxy)
        logger.info(f"[Session @{username}] Proxy configurado: {proxy[:30]}...")

    session_file = SESSIONS_DIR / f"{username}.json"

    if session_file.exists():
        try:
            client.load_settings(str(session_file))
            client.login(username, password)
            logger.info(f"[Session @{username}] Sessão reutilizada com sucesso")
            _save_session(client, session_file)
            return client
        except LoginRequired:
            logger.warning(f"[Session @{username}] Sessão expirada — fazendo novo login")
        except Exception as e:
            logger.warning(f"[Session @{username}] Erro ao carregar sessão: {e}")

    # Login fresco
    return _fresh_login(client, username, password, session_file)


def _fresh_login(
    client: Client,
    username: str,
    password: str,
    session_file: Path,
) -> Client:
    """Realiza um login fresco e salva a sessão."""
    try:
        client.login(username, password)
        _save_session(client, session_file)
        logger.info(f"[Session @{username}] Login OK — sessão salva")
        return client

    except ChallengeRequired as e:
        msg = f"Instagram pediu verificação de segurança para @{username}. Acesse o app manualmente."
        logger.error(f"[Session @{username}] ChallengeRequired: {e}")
        _send_alert(f"⚠️ Instagram Challenge @{username}", msg)
        raise RuntimeError(msg) from e

    except TwoFactorRequired:
        msg = f"@{username} tem 2FA ativo. Desative temporariamente ou configure TOTP."
        logger.error(f"[Session @{username}] TwoFactorRequired")
        _send_alert(f"⚠️ Instagram 2FA @{username}", msg)
        raise RuntimeError(msg)

    except BadPassword:
        msg = f"Senha incorreta para @{username}. Verifique o .env."
        logger.error(f"[Session @{username}] BadPassword")
        _send_alert(f"❌ Instagram senha errada @{username}", msg)
        raise RuntimeError(msg)

    except Exception as e:
        logger.error(f"[Session @{username}] Erro inesperado no login: {e}")
        _send_alert(f"❌ Instagram login falhou @{username}", str(e))
        raise


def _save_session(client: Client, session_file: Path) -> None:
    """Salva configurações da sessão em disco."""
    try:
        client.dump_settings(str(session_file))
    except Exception as e:
        logger.warning(f"[Session] Erro ao salvar sessão: {e}")


def _send_alert(subject: str, body: str) -> None:
    """Envia alerta por email quando ocorre erro crítico no Instagram."""
    if not ALERT_EMAIL or not SENDGRID_API_KEY:
        logger.warning(f"[Session] ALERTA (sem email configurado): {subject} — {body}")
        return

    import requests
    try:
        requests.post(
            "https://api.sendgrid.com/v3/mail/send",
            headers={
                "Authorization": f"Bearer {SENDGRID_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "personalizations": [{"to": [{"email": ALERT_EMAIL}]}],
                "from": {"email": EMAIL_FROM_ADDRESS or ALERT_EMAIL, "name": "SaveGram Bot"},
                "subject": subject,
                "content": [{"type": "text/plain", "value": body}],
            },
            timeout=10,
        )
        logger.info(f"[Session] Alerta enviado para {ALERT_EMAIL}")
    except Exception as e:
        logger.error(f"[Session] Falha ao enviar alerta: {e}")
