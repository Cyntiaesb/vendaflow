import os
from dotenv import load_dotenv

load_dotenv()

# ── Anthropic ──────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# ── Calendly ───────────────────────────────────────────────────────────────
CALENDLY_LINK = os.getenv("CALENDLY_LINK")
CALENDLY_API_KEY = os.getenv("CALENDLY_API_KEY")

# ── Instagram ──────────────────────────────────────────────────────────────
MESSAGES_PER_DAY = int(os.getenv("MESSAGES_PER_DAY", 80))
DELAY_MIN = int(os.getenv("DELAY_MIN", 20))
DELAY_MAX = int(os.getenv("DELAY_MAX", 60))
TARGET_NICHE = os.getenv("TARGET_NICHE", "restaurante")

# ── Apollo.io ──────────────────────────────────────────────────────────────
APOLLO_API_KEY = os.getenv("APOLLO_API_KEY", "")
APOLLO_INTENT_KEYWORDS = [
    k.strip()
    for k in os.getenv("APOLLO_INTENT_KEYWORDS", TARGET_NICHE).split(",")
    if k.strip()
]
APOLLO_LOCATION = os.getenv("APOLLO_LOCATION", "")          # ex: "São Paulo, BR"
APOLLO_INTENT_SCORE = os.getenv("APOLLO_INTENT_SCORE", "high")  # high | medium | low
APOLLO_LEADS_PER_DAY = int(os.getenv("APOLLO_LEADS_PER_DAY", 100))

# ── WhatsApp Business API Oficial (Meta Cloud API) ────────────────────────
# Docs: https://developers.facebook.com/docs/whatsapp/cloud-api
WHATSAPP_PHONE_NUMBER_ID     = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
WHATSAPP_BUSINESS_ACCOUNT_ID = os.getenv("WHATSAPP_BUSINESS_ACCOUNT_ID", "")
META_WEBHOOK_VERIFY_TOKEN    = os.getenv("META_WEBHOOK_VERIFY_TOKEN", "savegram_webhook_token")
WHATSAPP_MESSAGES_PER_DAY    = int(os.getenv("WHATSAPP_MESSAGES_PER_DAY", 40))

# ── Compliance / Segurança ────────────────────────────────────────────────
ALERT_EMAIL              = os.getenv("ALERT_EMAIL", "")
CALENDLY_WEBHOOK_SECRET  = os.getenv("CALENDLY_WEBHOOK_SECRET", "")
DASHBOARD_API_TOKEN      = os.getenv("DASHBOARD_API_TOKEN", "")
LOG_LEVEL                = os.getenv("LOG_LEVEL", "INFO")

# Proxy por conta Instagram (formato: conta:proxy)
# Ex: minha_conta:http://user:pass@host:port
def get_instagram_proxy(username: str) -> str:
    return os.getenv(f"INSTAGRAM_PROXY_{username.upper()}", "")

# ── Banco de dados ─────────────────────────────────────────────────────────
# ── Apify ─────────────────────────────────────────────────────────────────
APIFY_API_KEY = os.getenv("APIFY_API_KEY", "")

# ── Meta Ads ───────────────────────────────────────────────────────────────
META_ACCESS_TOKEN    = os.getenv("META_ACCESS_TOKEN", "")
META_AD_ACCOUNT_ID   = os.getenv("META_AD_ACCOUNT_ID", "")  # sem "act_"
META_API_VERSION     = os.getenv("META_API_VERSION", "v19.0")
META_PIXEL_ID        = os.getenv("META_PIXEL_ID", "")
META_APP_SECRET      = os.getenv("META_APP_SECRET", "")

# ── Google Ads ─────────────────────────────────────────────────────────────
GOOGLE_ADS_DEVELOPER_TOKEN = os.getenv("GOOGLE_ADS_DEVELOPER_TOKEN", "")
GOOGLE_ADS_CUSTOMER_ID     = os.getenv("GOOGLE_ADS_CUSTOMER_ID", "")
GOOGLE_ADS_ACCESS_TOKEN    = os.getenv("GOOGLE_ADS_ACCESS_TOKEN", "")

# ── Google Maps Places API ─────────────────────────────────────────────────
GOOGLE_MAPS_API_KEY        = os.getenv("GOOGLE_MAPS_API_KEY", "")
MAPS_TARGET_SEGMENT        = [s.strip() for s in os.getenv("MAPS_TARGET_SEGMENT", TARGET_NICHE).split(",") if s.strip()]
MAPS_TARGET_CITY           = os.getenv("MAPS_TARGET_CITY", "São Paulo")
MAPS_LEADS_PER_DAY         = int(os.getenv("MAPS_LEADS_PER_DAY", 50))

# ── Otimização de anúncios ─────────────────────────────────────────────────
ADS_MAX_CPA_BRL          = float(os.getenv("ADS_MAX_CPA_BRL", "150"))
ADS_SCALE_BUDGET_PCT     = int(os.getenv("ADS_SCALE_BUDGET_PCT", "20"))
ADS_MIN_SPEND_TO_EVALUATE= float(os.getenv("ADS_MIN_SPEND_TO_EVALUATE", "30"))

# ── Email (SendGrid) ───────────────────────────────────────────────────────
SENDGRID_API_KEY  = os.getenv("SENDGRID_API_KEY", "")
EMAIL_FROM_ADDRESS= os.getenv("EMAIL_FROM_ADDRESS", "")
EMAIL_FROM_NAME   = os.getenv("EMAIL_FROM_NAME", "SaveGram")

BUSINESS_NAME        = os.getenv("BUSINESS_NAME", "VendasFlow")
BUSINESS_NICHE       = os.getenv("BUSINESS_NICHE", TARGET_NICHE)

# ── Compliance / Segurança ────────────────────────────────────────────────
ALERT_EMAIL              = os.getenv("ALERT_EMAIL", "")
CALENDLY_WEBHOOK_SECRET  = os.getenv("CALENDLY_WEBHOOK_SECRET", "")
DASHBOARD_API_TOKEN      = os.getenv("DASHBOARD_API_TOKEN", "")
LOG_LEVEL                = os.getenv("LOG_LEVEL", "INFO")

# Proxy por conta Instagram (formato: conta:proxy)
# Ex: minha_conta:http://user:pass@host:port
def get_instagram_proxy(username: str) -> str:
    return os.getenv(f"INSTAGRAM_PROXY_{username.upper()}", "")

# ── Banco de dados ─────────────────────────────────────────────────────────
DB_PATH = os.getenv("DB_PATH", "savegram.db")
DASHBOARD_PORT = int(os.getenv("DASHBOARD_PORT", 5000))


def get_accounts() -> list[dict]:
    accounts = []
    i = 1
    while True:
        username = os.getenv(f"INSTAGRAM_USERNAME_{i}")
        password = os.getenv(f"INSTAGRAM_PASSWORD_{i}")
        if not username or not password:
            break
        accounts.append({"username": username, "password": password})
        i += 1
    return accounts
