"""
Sistema de logging estruturado — substitui os print() espalhados pelo código.

Configuração:
- Console: INFO e acima
- Arquivo: DEBUG e acima, rotação diária, mantém 30 dias
- Alerta email: CRITICAL (bot caiu, conta banida, etc.)

Uso:
    from modules.utils.logger import get_logger
    logger = get_logger(__name__)
    logger.info("mensagem")
    logger.error("erro", exc_info=True)
"""

import logging
import logging.handlers
import os
from pathlib import Path

LOGS_DIR = Path("logs")
LOGS_DIR.mkdir(exist_ok=True)

_configured = False


def setup_logging(level: str = "INFO") -> None:
    """Configura o sistema de logging global. Chame uma vez no main.py."""
    global _configured
    if _configured:
        return
    _configured = True

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    console = logging.StreamHandler()
    console.setLevel(getattr(logging, level.upper(), logging.INFO))
    console.setFormatter(fmt)
    root.addHandler(console)

    # Arquivo rotativo diário
    file_handler = logging.handlers.TimedRotatingFileHandler(
        filename=LOGS_DIR / "savegram.log",
        when="midnight",
        backupCount=30,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)

    # Arquivo de erros separado
    error_handler = logging.handlers.TimedRotatingFileHandler(
        filename=LOGS_DIR / "errors.log",
        when="midnight",
        backupCount=30,
        encoding="utf-8",
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(fmt)
    root.addHandler(error_handler)

    # Handler de alerta por email para CRITICAL
    alert_email = os.getenv("ALERT_EMAIL", "")
    sendgrid_key = os.getenv("SENDGRID_API_KEY", "")
    if alert_email and sendgrid_key:
        email_handler = _SendGridHandler(alert_email, sendgrid_key)
        email_handler.setLevel(logging.CRITICAL)
        email_handler.setFormatter(fmt)
        root.addHandler(email_handler)

    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("instagrapi").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Retorna um logger com o nome do módulo."""
    return logging.getLogger(name)


class _SendGridHandler(logging.Handler):
    """Handler que envia email via SendGrid para erros CRITICAL."""

    def __init__(self, to_email: str, api_key: str):
        super().__init__()
        self.to_email = to_email
        self.api_key  = api_key

    def emit(self, record: logging.LogRecord) -> None:
        try:
            import requests as _req
            msg = self.format(record)
            _req.post(
                "https://api.sendgrid.com/v3/mail/send",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "personalizations": [{"to": [{"email": self.to_email}]}],
                    "from": {"email": self.to_email, "name": "SaveGram Bot ALERTA"},
                    "subject": f"[CRÍTICO] SaveGram Bot: {record.getMessage()[:60]}",
                    "content": [{"type": "text/plain", "value": msg}],
                },
                timeout=5,
            )
        except Exception:
            pass  # Não lança exceção dentro de um handler de log
