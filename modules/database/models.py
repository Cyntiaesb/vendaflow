from sqlalchemy import create_engine, Column, String, DateTime, Text, Boolean, Integer
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime
from config.settings import DB_PATH

Base = declarative_base()
engine = create_engine(f"sqlite:///{DB_PATH}", echo=False)


class Lead(Base):
    __tablename__ = "leads"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(100), unique=True, nullable=False)
    full_name = Column(String(200))
    niche = Column(String(100))
    followers = Column(Integer, default=0)

    # ── Dados de contato enriquecidos (Apollo) ─────────────────────────
    phone = Column(String(30))
    email = Column(String(200))
    location = Column(String(200))

    # ── Qualidade do lead ──────────────────────────────────────────────
    intent_score           = Column(String(10), default="low")   # "high" | "medium" | "low"
    source                 = Column(String(50), default="apollo_intent")

    # ── Handle Instagram (leads Apollo com perfil B2B) ─────────────────
    instagram_username     = Column(String(100))  # handle real para envio de DM
    instagram_lookup_tried = Column(Boolean, default=False)
    instagram_not_found    = Column(Boolean, default=False)

    # ── Análise de perfil (seguidores → Apify → Claude) ────────────────
    profile_analyzed       = Column(Boolean, default=False)   # Apify já rodou
    profile_score          = Column(String(10))               # "hot"|"warm"|"cold"
    profile_score_reason   = Column(String(500))              # por que esse score
    profile_raw_data       = Column(Text)                     # JSON bruto do Apify
    profile_analyzed_at    = Column(DateTime)

    # ── Contato Instagram DM ───────────────────────────────────────────
    contacted = Column(Boolean, default=False)
    contacted_at = Column(DateTime)
    contacted_by = Column(String(100))

    # ── Contato Email ──────────────────────────────────────────────────
    email_contacted       = Column(Boolean, default=False)
    email_contacted_at    = Column(DateTime)
    email_sequence_step   = Column(Integer, default=0)  # 0=não enviado, 1,2,3=follow-ups
    email_opened          = Column(Boolean, default=False)
    email_replied         = Column(Boolean, default=False)
    email_bounced         = Column(Boolean, default=False)
    email_unsubscribed    = Column(Boolean, default=False)

    # ── Contato WhatsApp ───────────────────────────────────────────────
    whatsapp_contacted = Column(Boolean, default=False)
    whatsapp_contacted_at = Column(DateTime)
    whatsapp_invalid = Column(Boolean, default=False)  # número sem WA
    whatsapp_conversation = Column(Text, default="[]")

    # ── Resposta (qualquer canal) ──────────────────────────────────────
    responded = Column(Boolean, default=False)
    responded_at = Column(DateTime)

    # ── Qualificação ───────────────────────────────────────────────────
    qualified = Column(Boolean, default=False)
    disqualified = Column(Boolean, default=False)
    disqualify_reason = Column(String(200))

    # ── Agendamento ────────────────────────────────────────────────────
    call_scheduled = Column(Boolean, default=False)
    call_scheduled_at = Column(DateTime)

    # ── Conversa Instagram (JSON) ──────────────────────────────────────
    conversation = Column(Text, default="[]")

    # ── LGPD / Compliance ──────────────────────────────────────────────
    opted_out          = Column(Boolean, default=False)
    opted_out_at       = Column(DateTime)
    opted_out_channel  = Column(String(30))  # canal onde pediu saída
    purge_after        = Column(DateTime)    # data para anonimizar dados

    # ── Rastreamento de anúncios ───────────────────────────────────────
    ad_source      = Column(String(20))   # "meta" | "google" | None
    ad_id          = Column(String(100))  # ID do anúncio Meta
    adset_id       = Column(String(100))  # ID do conjunto de anúncios
    campaign_id    = Column(String(100))  # ID da campanha Meta ou Google
    ad_name        = Column(String(200))  # nome do anúncio (para relatórios)
    utm_source     = Column(String(100))  # utm_source (google, facebook…)
    utm_campaign   = Column(String(100))  # utm_campaign
    utm_medium     = Column(String(100))  # utm_medium
    ctwa_clid      = Column(String(200))  # Click-to-WhatsApp click ID (Meta)

    created_at = Column(DateTime, default=datetime.utcnow)


class AdReport(Base):
    """Log de cada ciclo de otimização de anúncios."""
    __tablename__ = "ad_reports"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    platform   = Column(String(20))   # "meta" | "google" | "all"
    action     = Column(String(50))   # "optimize" | "pause" | "scale"
    details    = Column(Text)         # JSON com resultados
    created_at = Column(DateTime, default=datetime.utcnow)



Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)


def get_session():
    return Session()
