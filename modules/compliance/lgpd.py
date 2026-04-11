"""
LGPD Compliance — opt-out universal, purge automático e janela horária.

Três responsabilidades:

1. OPT-OUT: detecta pedidos de parada em qualquer canal e executa
   imediatamente — para contato, agenda exclusão em 30 dias.

2. PURGE: cron semanal que anonimiza dados de leads com opt-out
   confirmado há mais de 30 dias e desqualificados há mais de 90 dias.

3. CONTACT WINDOW: verifica se é horário permitido para envios
   e se o lead não foi contatado em outro canal muito recentemente.
"""

import logging
import re
from datetime import datetime, timedelta
from modules.database.models import Lead, get_session

logger = logging.getLogger(__name__)

# Palavras que indicam pedido de opt-out em PT e EN
OPT_OUT_TERMS = [
    # Português
    "sair", "stop", "para", "pare", "chega", "remove",
    "remover", "não quero", "nao quero", "sem interesse",
    "não tenho interesse", "descadastrar", "descadastra",
    "cancelar", "cancela", "bloquear", "me tira", "não me mande",
    "nao me mande", "não mande mais", "nao mande mais",
    # Inglês (comum em apps)
    "unsubscribe", "opt out", "opt-out", "do not contact",
    "remove me", "stop sending",
]

# Horário permitido para envios (BRT = UTC-3)
SEND_HOUR_START = 8   # 08:00
SEND_HOUR_END   = 20  # 20:00

# Intervalo mínimo entre canais para o mesmo lead (horas)
INTER_CHANNEL_HOURS = 24


class LGPDCompliance:

    def __init__(self):
        self.db = get_session()

    # ── 1. Detecção de opt-out ────────────────────────────────────────

    @staticmethod
    def is_opt_out_request(text: str) -> bool:
        """
        Retorna True se o texto contém pedido de opt-out.
        Case-insensitive, ignora acentos parcialmente.
        """
        if not text:
            return False
        normalized = text.lower().strip()
        return any(term in normalized for term in OPT_OUT_TERMS)

    def process_opt_out(self, lead: Lead, channel: str) -> None:
        """
        Executa opt-out imediato:
        - Marca opted_out=True
        - Desqualifica em todos os canais
        - Agenda exclusão em 30 dias
        """
        lead.opted_out        = True
        lead.opted_out_at     = datetime.utcnow()
        lead.opted_out_channel= channel
        lead.disqualified     = True
        lead.disqualify_reason= f"opt-out via {channel}"
        lead.purge_after      = datetime.utcnow() + timedelta(days=30)
        self.db.commit()

        logger.info(
            f"[LGPD] Opt-out registrado: @{lead.instagram_username or lead.username} "
            f"via {channel} — dados serão purgados em 30 dias"
        )

    # ── 2. Purge automático ───────────────────────────────────────────

    def run_purge(self) -> dict:
        """
        Remove dados pessoais de leads elegíveis para purge.
        Roda semanalmente via scheduler.
        Retorna estatísticas de purge.
        """
        now = datetime.utcnow()
        stats = {"purged_opted_out": 0, "purged_disqualified": 0, "anonymized": 0}

        # Purge de opt-outs com prazo vencido
        opted_out_leads = (
            self.db.query(Lead)
            .filter(
                Lead.opted_out == True,
                Lead.purge_after <= now,
            )
            .all()
        )
        for lead in opted_out_leads:
            self._anonymize_lead(lead)
            stats["purged_opted_out"] += 1

        # Purge de desqualificados há mais de 90 dias
        cutoff_disq = now - timedelta(days=90)
        disq_leads = (
            self.db.query(Lead)
            .filter(
                Lead.disqualified == True,
                Lead.opted_out != True,          # já tratados acima
                Lead.created_at <= cutoff_disq,
                Lead.call_scheduled == False,    # mantém clientes
            )
            .all()
        )
        for lead in disq_leads:
            self._anonymize_lead(lead)
            stats["purged_disqualified"] += 1

        stats["anonymized"] = stats["purged_opted_out"] + stats["purged_disqualified"]
        self.db.commit()
        logger.info(f"[LGPD] Purge executado: {stats}")
        return stats

    def _anonymize_lead(self, lead: Lead) -> None:
        """Remove PII, mantém apenas dados agregados para estatística."""
        lead.full_name              = "ANONIMIZADO"
        lead.phone                  = None
        lead.email                  = None
        lead.instagram_username     = None
        lead.conversation           = "[]"
        lead.whatsapp_conversation  = "[]"
        lead.profile_raw_data       = None
        lead.ctwa_clid              = None
        lead.utm_source             = None
        lead.utm_campaign           = None
        lead.utm_medium             = None
        lead.ad_id                  = None
        lead.email_sequence_step    = 0

    # ── 3. Janela horária ─────────────────────────────────────────────

    @staticmethod
    def is_sending_allowed() -> bool:
        """
        Retorna True se estamos dentro da janela horária permitida
        para envio de mensagens (8h-20h BRT).
        """
        now_brt = datetime.utcnow() - timedelta(hours=3)  # UTC-3
        return SEND_HOUR_START <= now_brt.hour < SEND_HOUR_END

    def can_contact_lead(self, lead: Lead, channel: str) -> tuple[bool, str]:
        """
        Verifica se é seguro e permitido contatar este lead agora.

        Retorna (pode_contatar: bool, motivo: str)
        """
        # Opt-out
        if getattr(lead, "opted_out", False):
            return False, "lead fez opt-out"

        # Janela horária
        if not self.is_sending_allowed():
            return False, "fora da janela horária (8h-20h)"

        # Verificação inter-canal: não contatar em outro canal se já foi
        # contatado há menos de INTER_CHANNEL_HOURS horas
        last_contact = self._get_last_contact_time(lead)
        if last_contact:
            hours_since = (datetime.utcnow() - last_contact).total_seconds() / 3600
            if hours_since < INTER_CHANNEL_HOURS:
                return False, (
                    f"lead foi contatado há {hours_since:.0f}h "
                    f"(mínimo: {INTER_CHANNEL_HOURS}h entre canais)"
                )

        return True, "ok"

    def _get_last_contact_time(self, lead: Lead) -> datetime | None:
        """Retorna o timestamp do contato mais recente em qualquer canal."""
        timestamps = [
            t for t in [
                lead.contacted_at,
                lead.whatsapp_contacted_at,
                lead.email_contacted_at,
            ]
            if t is not None
        ]
        return max(timestamps) if timestamps else None
