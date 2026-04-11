"""
VendasFlow — Pipeline completo de prospecção multi-canal

Fontes de leads:
  - Apollo.io     → leads com purchase intent ativo (buscaram keywords nos últimos 7 dias)
  - Google Maps   → empresas locais por segmento e cidade
  - Instagram     → seguidores + análise de perfil via Apify + Claude

Canais de contato:
  - WhatsApp      → Meta Cloud API (oficial)
  - Instagram DM  → multi-conta via instagrapi
  - Email         → SendGrid (leads sem telefone ou como canal adicional)
Scheduler diário:
  07:00  analyze_follower_profiles() → pontua seguidores via Apify + Claude
  07:30  optimize_ads()              → pausa anúncios ruins, escala bons
  08:00  fetch_apollo_leads()        → leads por purchase intent (Apollo)
  08:30  fetch_maps_leads()          → empresas locais por segmento (Google Maps)
  09:00  enrich_leads()              → adiciona telefone/email (Apollo Match API)
  09:30  find_instagram_handles()    → busca perfil B2B no Instagram p/ leads Apollo/Maps
  10:00  run_instagram_campaign()    → DMs para leads com instagram_username
  10:30  run_whatsapp_campaign()     → WhatsApp para leads com telefone
  11:00  run_email_campaign()        → Email para leads com email
  11:30  run_email_followups()       → Follow-ups de email
  */30m  check_instagram_replies()   → verifica e responde DMs recebidas
  */60m  check_new_followers()       → detecta novos seguidores
"""

import schedule
import time
from dotenv import load_dotenv

load_dotenv()

from modules.utils.logger import setup_logging, get_logger
from config.settings import LOG_LEVEL
setup_logging(LOG_LEVEL)
logger = get_logger("main")

from config.settings import (
    APOLLO_API_KEY,
    APOLLO_INTENT_KEYWORDS,
    APOLLO_LOCATION,
    APOLLO_INTENT_SCORE,
    APOLLO_LEADS_PER_DAY,
    MESSAGES_PER_DAY,
    WHATSAPP_MESSAGES_PER_DAY,
    WHATSAPP_PHONE_NUMBER_ID,
    META_ACCESS_TOKEN,
    GOOGLE_ADS_ACCESS_TOKEN,
    GOOGLE_MAPS_API_KEY,
    MAPS_TARGET_SEGMENT,
    MAPS_TARGET_CITY,
    MAPS_LEADS_PER_DAY,
    get_accounts,
)
from modules.prospecting.apollo_client import ApolloClient
from modules.prospecting.google_maps_client import GoogleMapsClient
from modules.instagram.scraper import InstagramFinder
from modules.instagram.account_manager import AccountManager
from modules.whatsapp.meta_whatsapp_client import MetaWhatsAppClient
from modules.ads.optimizer import AdOptimizer
from modules.email.email_client import EmailClient


# ── Pipeline functions ─────────────────────────────────────────────────────

def run_lgpd_purge():
    """Purge semanal de dados pessoais vencidos (LGPD Art. 15)."""
    from modules.compliance.lgpd import LGPDCompliance
    logger.info("LGPD: iniciando purge semanal de dados...")
    try:
        stats = LGPDCompliance().run_purge()
        logger.info(f"LGPD purge concluído: {stats}")
    except Exception as e:
        logger.error(f"Erro no purge LGPD: {e}", exc_info=True)


def check_new_followers():
    """Detecta novos seguidores e salva no CRM."""
    accounts = get_accounts()
    if not accounts:
        return
    print("\n[Main] 👥 Instagram: verificando novos seguidores...")
    try:
        manager = AccountManager()
        found = manager.check_new_followers(fetch_limit=100)
        print(f"[Main] {found} novo(s) seguidor(es) adicionado(s) ao CRM")
    except Exception as e:
        print(f"[Main] Erro ao verificar seguidores: {e}")


def analyze_follower_profiles():
    """
    Analisa perfis de seguidores novos via Apify + Claude.
    Hot → intent_score=high (será contactado)
    Warm → intent_score=medium
    Cold → não será contactado
    """
    from config.settings import APIFY_API_KEY
    if not APIFY_API_KEY:
        print("[Main] APIFY_API_KEY não configurada — pulando análise de seguidores")
        return
    accounts = get_accounts()
    if not accounts:
        return
    print("\n[Main] 🔍 Apify: analisando perfis de seguidores...")
    try:
        manager = AccountManager()
        analyzed = manager.analyze_follower_profiles(batch_size=50)
        print(f"[Main] {analyzed} perfis pontuados")
    except Exception as e:
        print(f"[Main] Erro na análise de seguidores: {e}")


def optimize_ads():
    """Otimiza anúncios Meta e Google com base no CPA real."""
    if not META_ACCESS_TOKEN and not GOOGLE_ADS_ACCESS_TOKEN:
        return
    print("\n[Main] 📊 Otimizando anúncios...")
    try:
        AdOptimizer().run()
    except Exception as e:
        print(f"[Main] Erro na otimização: {e}")


def fetch_maps_leads():
    """Busca empresas locais por segmento e cidade via Google Maps Places API."""
    if not GOOGLE_MAPS_API_KEY:
        print("[Main] GOOGLE_MAPS_API_KEY não configurada — pulando")
        return
    print(f"\n[Main] 🗺️ Google Maps: buscando {MAPS_TARGET_SEGMENT} em {MAPS_TARGET_CITY}...")
    try:
        maps = GoogleMapsClient()
        saved = maps.multi_segment_prospect(
            segments=MAPS_TARGET_SEGMENT,
            city=MAPS_TARGET_CITY,
            limit_per_segment=MAPS_LEADS_PER_DAY // max(len(MAPS_TARGET_SEGMENT), 1),
            fetch_details=True,
        )
        print(f"[Main] Google Maps: {saved} novos leads salvos")
    except Exception as e:
        print(f"[Main] Erro Google Maps: {e}")


def fetch_apollo_leads():
    """Busca leads com intenção de compra ativa via Apollo.io."""
    if not APOLLO_API_KEY:
        print("[Main] APOLLO_API_KEY não configurada — pulando")
        return
    print("\n[Main] 🎯 Apollo: buscando leads por purchase intent...")
    try:
        apollo = ApolloClient()
        saved = apollo.save_intent_leads(
            keywords=APOLLO_INTENT_KEYWORDS,
            location=APOLLO_LOCATION or None,
            intent_score=APOLLO_INTENT_SCORE,
            limit=APOLLO_LEADS_PER_DAY,
        )
        print(f"[Main] Apollo: {saved} novos leads salvos")
    except Exception as e:
        print(f"[Main] Erro Apollo: {e}")


def enrich_leads():
    """Enriquece leads Apollo com telefone/email via Apollo Match API."""
    if not APOLLO_API_KEY:
        return
    print("\n[Main] 📋 Apollo: enriquecendo com telefone/email...")
    try:
        apollo = ApolloClient()
        enriched = apollo.bulk_enrich(limit=50)
        print(f"[Main] Apollo: {enriched} leads enriquecidos")
    except Exception as e:
        print(f"[Main] Erro enriquecimento: {e}")


def find_instagram_handles():
    """
    Para leads Apollo sem instagram_username, busca perfil B2B no Instagram.
    Usa InstagramFinder (search por nome da empresa).
    """
    accounts = get_accounts()
    if not accounts:
        print("[Main] Nenhuma conta Instagram configurada — pulando busca de handles")
        return
    print("\n[Main] 🔍 Buscando handles Instagram de leads Apollo...")
    try:
        finder = InstagramFinder(accounts[0]["username"], accounts[0]["password"])
        found = finder.bulk_find_instagram(limit=30)
        print(f"[Main] Handles encontrados: {found}")
    except Exception as e:
        print(f"[Main] Erro na busca de handles: {e}")


def run_instagram_campaign():
    """Envia DMs apenas para leads Apollo com instagram_username encontrado."""
    accounts = get_accounts()
    if not accounts:
        print("[Main] Nenhuma conta Instagram configurada — pulando campanha")
        return
    print("\n[Main] 📨 Instagram: campanha Apollo→DM...")
    try:
        manager = AccountManager()
        per_account = MESSAGES_PER_DAY // max(len(manager.bots), 1)
        manager.run_campaigns(messages_per_account=per_account)
    except Exception as e:
        print(f"[Main] Erro campanha Instagram: {e}")


def run_email_campaign():
    """
    Email para leads Apollo com email.
    Prioriza leads SEM telefone (email é o único canal deles).
    Leads com telefone também recebem email como canal adicional.
    """
    from config.settings import SENDGRID_API_KEY
    if not SENDGRID_API_KEY:
        print("[Main] SENDGRID_API_KEY não configurada — pulando email")
        return
    print("\n[Main] 📧 Email: campanha de primeiro contato...")
    try:
        EmailClient().run_first_contact_campaign(limit=50)
    except Exception as e:
        print(f"[Main] Erro campanha email: {e}")


def run_email_followups():
    """Envia follow-ups de email (step 2 e 3) para leads sem resposta."""
    from config.settings import SENDGRID_API_KEY
    if not SENDGRID_API_KEY:
        return
    print("\n[Main] 📧 Email: follow-ups...")
    try:
        EmailClient().run_followup_campaign(limit=30)
    except Exception as e:
        print(f"[Main] Erro follow-ups email: {e}")


def run_whatsapp_campaign():
    """WhatsApp para leads Apollo com telefone (High intent primeiro)."""
    if not WHATSAPP_PHONE_NUMBER_ID or not META_ACCESS_TOKEN:
        print("[Main] EVOLUTION_API_KEY não configurada — pulando")
        return
    print("\n[Main] 💬 WhatsApp: campanha Apollo...")
    try:
        wa = MetaWhatsAppClient()
        sent = wa.run_whatsapp_campaign(limit=WHATSAPP_MESSAGES_PER_DAY)
        print(f"[Main] WhatsApp: {sent} mensagens enviadas")
    except Exception as e:
        print(f"[Main] Erro campanha WhatsApp: {e}")


def monitor_instagram_comments():
    """Monitora comentários nos posts — responde publicamente + envia DM."""
    accounts = get_accounts()
    if not accounts:
        return
    print("\n[Main] 💬 Instagram: monitorando comentários...")
    try:
        manager = AccountManager()
        total = manager.monitor_comments(posts_limit=5)
        print(f"[Main] Comentários processados: {total}")
    except Exception as e:
        print(f"[Main] Erro ao monitorar comentários: {e}")


def process_story_replies():
    """Processa respostas e reações a stories."""
    accounts = get_accounts()
    if not accounts:
        return
    print("\n[Main] 📱 Instagram: processando story replies...")
    try:
        manager = AccountManager()
        total = manager.process_story_replies()
        print(f"[Main] Story replies processados: {total}")
    except Exception as e:
        print(f"[Main] Erro ao processar story replies: {e}")


def check_instagram_replies():
    """Verifica e responde DMs recebidas no Instagram."""
    accounts = get_accounts()
    if not accounts:
        return
    print("\n[Main] 📬 Instagram: verificando respostas...")
    try:
        manager = AccountManager()
        manager.check_replies()
    except Exception as e:
        print(f"[Main] Erro ao verificar respostas: {e}")


# ── Scheduler ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("  VendasFlow — Pipeline Multi-Canal de Prospecção IA")
    print("  Fontes: Apollo (intent) + Google Maps + Instagram")
    print("  Canais: WhatsApp + Instagram DM + Email + Voz")
    print("=" * 60)

    # ── Scheduler ──────────────────────────────────────────────────────
    schedule.every().week.do(run_lgpd_purge)
    schedule.every(60).minutes.do(check_new_followers)
    schedule.every().day.at("07:00").do(analyze_follower_profiles)
    schedule.every().day.at("07:30").do(optimize_ads)
    schedule.every().day.at("08:00").do(fetch_apollo_leads)
    schedule.every().day.at("08:30").do(fetch_maps_leads)      # ← Google Maps
    schedule.every().day.at("09:00").do(enrich_leads)
    schedule.every().day.at("09:30").do(find_instagram_handles)
    schedule.every().day.at("10:00").do(run_instagram_campaign)
    schedule.every().day.at("10:30").do(run_whatsapp_campaign)
    schedule.every().day.at("11:00").do(run_email_campaign)
    schedule.every().day.at("11:30").do(run_email_followups)
    schedule.every(30).minutes.do(check_instagram_replies)
    schedule.every(30).minutes.do(monitor_instagram_comments)
    schedule.every(30).minutes.do(process_story_replies)

    # ── Executa pipeline completo ao iniciar ───────────────────────────
    fetch_apollo_leads()
    fetch_maps_leads()                                          # ← Google Maps
    enrich_leads()
    find_instagram_handles()
    run_instagram_campaign()
    run_whatsapp_campaign()
    run_email_campaign()

    print("\n[Main] ✅ Scheduler ativo. Ctrl+C para parar.\n")
    while True:
        schedule.run_pending()
        time.sleep(60)
