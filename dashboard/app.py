from flask import Flask, jsonify, request, abort, render_template
from functools import wraps
from config.settings import DASHBOARD_API_TOKEN
from sqlalchemy import func
from datetime import datetime
from modules.database.models import Lead, get_session
from config.settings import DASHBOARD_PORT

import os
app = Flask(__name__, template_folder="templates", static_folder="static")

# ── Basic token auth ───────────────────────────────────────────────────────
def require_token(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if DASHBOARD_API_TOKEN:
            token = request.headers.get("X-API-Token") or request.args.get("token")
            if token != DASHBOARD_API_TOKEN:
                abort(401)
        return f(*args, **kwargs)
    return decorated


def _today():
    return datetime.utcnow().date()


@app.route("/")
def index():
    return render_template("index.html", token=DASHBOARD_API_TOKEN)

@app.route("/ads")
def ads_page():
    return render_template("ads.html", token=DASHBOARD_API_TOKEN)


@app.route("/api/stats")
@require_token
def stats():
    db = get_session()
    today = _today()

    total_leads = db.query(func.count(Lead.id)).scalar()

    # Instagram
    ig_contacted_total = db.query(func.count(Lead.id)).filter(Lead.contacted == True).scalar()
    ig_contacted_today = (
        db.query(func.count(Lead.id))
        .filter(Lead.contacted == True, func.date(Lead.contacted_at) == today)
        .scalar()
    )

    # WhatsApp
    wa_contacted_total = db.query(func.count(Lead.id)).filter(Lead.whatsapp_contacted == True).scalar()
    wa_contacted_today = (
        db.query(func.count(Lead.id))
        .filter(Lead.whatsapp_contacted == True, func.date(Lead.whatsapp_contacted_at) == today)
        .scalar()
    )
    wa_invalid = db.query(func.count(Lead.id)).filter(Lead.whatsapp_invalid == True).scalar()

    # Funil geral
    replied = db.query(func.count(Lead.id)).filter(Lead.responded == True).scalar()
    calls_total = db.query(func.count(Lead.id)).filter(Lead.call_scheduled == True).scalar()
    calls_today = (
        db.query(func.count(Lead.id))
        .filter(Lead.call_scheduled == True, func.date(Lead.call_scheduled_at) == today)
        .scalar()
    )
    disqualified = db.query(func.count(Lead.id)).filter(Lead.disqualified == True).scalar()

    # Por fonte
    from_instagram = db.query(func.count(Lead.id)).filter(Lead.source == "instagram").scalar()
    from_apollo    = db.query(func.count(Lead.id)).filter(Lead.source == "apollo_intent").scalar()
    from_maps      = db.query(func.count(Lead.id)).filter(Lead.source == "google_maps").scalar()
    from_meta      = db.query(func.count(Lead.id)).filter(Lead.ad_source == "meta").scalar()
    from_google_ads= db.query(func.count(Lead.id)).filter(Lead.ad_source == "google").scalar()

    # Por intent score
    high_intent = db.query(func.count(Lead.id)).filter(Lead.intent_score == "high").scalar()
    medium_intent = db.query(func.count(Lead.id)).filter(Lead.intent_score == "medium").scalar()
    low_intent = db.query(func.count(Lead.id)).filter(Lead.intent_score == "low").scalar()

    total_contacted = ig_contacted_total + wa_contacted_total
    conversion = (
        f"{(calls_total / total_contacted * 100):.2f}%"
        if total_contacted > 0
        else "0%"
    )

    return jsonify({
        "date": str(today),
        "total_leads_db": total_leads,
        "sources": {
            "instagram":   from_instagram,
            "apollo_intent": from_apollo,
            "google_maps": from_maps,
            "meta_ads":    from_meta,
            "google_ads":  from_google_ads,
        },
        "intent_breakdown": {
            "high": high_intent,
            "medium": medium_intent,
            "low": low_intent,
        },
        "instagram": {
            "contacted_total": ig_contacted_total,
            "contacted_today": ig_contacted_today,
        },
        "whatsapp": {
            "contacted_total": wa_contacted_total,
            "contacted_today": wa_contacted_today,
            "invalid_numbers": wa_invalid,
        },
        "funnel": {
            "replied": replied,
            "calls_scheduled_total": calls_total,
            "calls_scheduled_today": calls_today,
            "disqualified": disqualified,
            "conversion_rate": conversion,
        },
    })


@app.route("/api/leads/recent")
@require_token
def recent_leads():
    db = get_session()
    leads = (
        db.query(Lead)
        .filter(Lead.contacted == True)
        .order_by(Lead.contacted_at.desc())
        .limit(30)
        .all()
    )
    return jsonify([_lead_dict(l) for l in leads])


@app.route("/api/leads/qualified")
@require_token
def qualified_leads():
    db = get_session()
    leads = db.query(Lead).filter(Lead.call_scheduled == True).all()
    return jsonify([_lead_dict(l) for l in leads])


@app.route("/api/leads/high-intent")
@require_token
def high_intent_leads():
    """Leads High Intent ainda não contatados — próximos a abordar."""
    db = get_session()
    leads = (
        db.query(Lead)
        .filter(
            Lead.intent_score == "high",
            Lead.contacted == False,
            Lead.whatsapp_contacted == False,
            Lead.disqualified == False,
        )
        .order_by(Lead.created_at.desc())
        .limit(50)
        .all()
    )
    return jsonify([_lead_dict(l) for l in leads])


@app.route("/api/ads/stats")
def ads_stats():
    """Performance dos anúncios cruzada com agendamentos do banco."""
    db = get_session()
    from sqlalchemy import func

    # Agendamentos por fonte de anúncio
    by_source = (
        db.query(Lead.ad_source, func.count(Lead.id).label("leads"),
                 func.sum(Lead.call_scheduled.cast(db.bind.dialect.name == "sqlite" and "INTEGER" or "INTEGER")).label("scheduled"))
        .filter(Lead.ad_source != None)
        .group_by(Lead.ad_source)
        .all()
    )

    # Top 10 anúncios por agendamentos
    top_ads = (
        db.query(
            Lead.ad_id,
            Lead.ad_name,
            Lead.ad_source,
            func.count(Lead.id).label("total_leads"),
            func.sum(Lead.call_scheduled.cast("INTEGER")).label("scheduled"),
        )
        .filter(Lead.ad_id != None)
        .group_by(Lead.ad_id)
        .order_by(func.sum(Lead.call_scheduled.cast("INTEGER")).desc())
        .limit(10)
        .all()
    )

    # Leads inbound sem ad_id mas via WhatsApp
    inbound_total = db.query(func.count(Lead.id)).filter(
        Lead.source.contains("inbound")
    ).scalar() or 0

    return jsonify({
        "by_source": [
            {"source": r.ad_source, "leads": r.leads, "scheduled": int(r.scheduled or 0)}
            for r in by_source
        ],
        "top_ads": [
            {
                "ad_id": r.ad_id,
                "ad_name": r.ad_name,
                "source": r.ad_source,
                "total_leads": r.total_leads,
                "scheduled": int(r.scheduled or 0),
            }
            for r in top_ads
        ],
        "inbound_total": inbound_total,
    })


@app.route("/api/ads/leads")
def ads_leads():
    """Últimos 50 leads que vieram de anúncios."""
    db = get_session()
    leads = (
        db.query(Lead)
        .filter(Lead.ad_source != None)
        .order_by(Lead.created_at.desc())
        .limit(50)
        .all()
    )
    return jsonify([
        {
            "username": l.username,
            "full_name": l.full_name,
            "phone": l.phone,
            "ad_source": l.ad_source,
            "ad_name": l.ad_name,
            "campaign_id": l.campaign_id,
            "intent_score": l.intent_score,
            "responded": l.responded,
            "call_scheduled": l.call_scheduled,
            "created_at": l.created_at.isoformat() if l.created_at else None,
        }
        for l in leads
    ])
@app.route("/webhook/whatsapp", methods=["GET"])
def whatsapp_webhook_verify():
    """Meta verifica a URL com GET + hub.challenge."""
    from config.settings import META_WEBHOOK_VERIFY_TOKEN
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    if mode == "subscribe" and token == META_WEBHOOK_VERIFY_TOKEN:
        return challenge, 200
    return "Forbidden", 403


@app.route("/webhook/whatsapp", methods=["POST"])
def whatsapp_webhook():
    """WhatsApp Business API oficial (Meta Cloud API)."""
    import hmac, hashlib
    from config.settings import META_APP_SECRET
    if META_APP_SECRET:
        sig = request.headers.get("X-Hub-Signature-256", "")
        if sig.startswith("sha256="):
            exp = hmac.new(META_APP_SECRET.encode(), request.get_data(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(exp, sig[7:]):
                return "Unauthorized", 401
    payload = request.get_json(silent=True) or {}
    try:
        from modules.whatsapp.meta_whatsapp_client import MetaWhatsAppClient
        client = MetaWhatsAppClient()
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                metadata = value.get("metadata", {})
                for msg in value.get("messages", []):
                    client.process_webhook_message(msg, metadata)
                for st in value.get("statuses", []):
                    if st.get("status") == "failed":
                        app.logger.warning(f"[WA] Mensagem falhou: {st.get('errors')}")
    except Exception as e:
        app.logger.error(f"[Webhook/WA] Erro: {e}", exc_info=True)
    return jsonify({"ok": True}), 200
# ── Helper ────────────────────────────────────────────────────────────────

def _lead_dict(l: Lead) -> dict:
    return {
        "username": l.username,
        "full_name": l.full_name,
        "niche": l.niche,
        "phone": l.phone,
        "email": l.email,
        "location": l.location,
        "intent_score": l.intent_score,
        "source": l.source,
        "followers": l.followers,
        "contacted_at": l.contacted_at.isoformat() if l.contacted_at else None,
        "whatsapp_contacted": l.whatsapp_contacted,
        "responded": l.responded,
        "qualified": l.qualified,
        "call_scheduled": l.call_scheduled,
        "disqualified": l.disqualified,
    }




if __name__ == "__main__":
    app.run(debug=True, port=DASHBOARD_PORT)


@app.route("/webhook/email", methods=["POST"])
def email_webhook():
    """Recebe eventos do SendGrid: open, bounce, unsubscribe, click."""
    events = request.get_json(silent=True) or []
    if not isinstance(events, list):
        events = [events]
    try:
        from modules.email.email_client import EmailClient
        client = EmailClient()
        for event in events:
            client.process_sendgrid_event(event)
    except Exception as e:
        print(f"[Webhook/Email] Erro: {e}")
    return jsonify({"ok": True}), 200


@app.route("/api/email/stats")
def email_stats():
    """Métricas do canal email."""
    from sqlalchemy import func
    db = get_session()
    total     = db.query(func.count(Lead.id)).filter(Lead.email_contacted == True).scalar() or 0
    opened    = db.query(func.count(Lead.id)).filter(Lead.email_opened == True).scalar() or 0
    bounced   = db.query(func.count(Lead.id)).filter(Lead.email_bounced == True).scalar() or 0
    unsub     = db.query(func.count(Lead.id)).filter(Lead.email_unsubscribed == True).scalar() or 0
    scheduled = db.query(func.count(Lead.id)).filter(
        Lead.email_contacted == True, Lead.call_scheduled == True
    ).scalar() or 0
    return jsonify({
        "total_sent": total,
        "opened": opened,
        "open_rate": f"{(opened/total*100):.1f}%" if total else "0%",
        "bounced": bounced,
        "unsubscribed": unsub,
        "scheduled": scheduled,
        "conversion_rate": f"{(scheduled/total*100):.1f}%" if total else "0%",
    })


@app.route("/webhook/calendly", methods=["POST"])
def calendly_webhook():
    """
    Recebe eventos do Calendly.
    invitee.created  → lead agendou de verdade → call_scheduled=True
    invitee.canceled → lead cancelou → reabre oportunidade
    """
    payload     = request.get_json(silent=True) or {}
    signature   = request.headers.get("Calendly-Webhook-Signature", "")
    raw_payload = request.get_data()

    from modules.scheduler.calendly_webhook import CalendlyWebhookHandler
    handler = CalendlyWebhookHandler()

    if not handler.verify_signature(raw_payload, signature):
        abort(401)

    result = handler.process_event(payload)
    return jsonify(result), 200


@app.route("/api/google/keywords")
@require_token
def google_keywords():
    """Keywords ativas no Google Ads com performance."""
    from config.settings import GOOGLE_ADS_DEVELOPER_TOKEN
    if not GOOGLE_ADS_DEVELOPER_TOKEN:
        return jsonify({"error": "Google Ads não configurado", "keywords": [], "ideas": []})
    try:
        from modules.ads.google_ads_client import GoogleAdsClient
        from config.settings import APOLLO_INTENT_KEYWORDS
        client = GoogleAdsClient()
        keywords = client.get_keywords_performance()
        ideas    = client.get_keyword_ideas(APOLLO_INTENT_KEYWORDS[:10])
        return jsonify({"keywords": keywords, "ideas": ideas})
    except Exception as e:
        return jsonify({"error": str(e), "keywords": [], "ideas": []})


@app.route("/api/compliance/purge", methods=["POST"])
@require_token
def run_purge():
    """Executa purge manual de dados LGPD vencidos."""
    from modules.compliance.lgpd import LGPDCompliance
    stats = LGPDCompliance().run_purge()
    return jsonify(stats), 200


# ── Controle de campanha ───────────────────────────────────────────────────

_campaign_process = None

@app.route("/api/campaign/start", methods=["POST"])
@require_token
def campaign_start():
    global _campaign_process
    import subprocess, sys
    if _campaign_process and _campaign_process.poll() is None:
        return jsonify({"status": "already_running"}), 200
    _campaign_process = subprocess.Popen(
        [sys.executable, "main.py"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return jsonify({"status": "started", "pid": _campaign_process.pid})


@app.route("/api/campaign/stop", methods=["POST"])
@require_token
def campaign_stop():
    global _campaign_process
    if _campaign_process and _campaign_process.poll() is None:
        _campaign_process.terminate()
        return jsonify({"status": "stopped"})
    return jsonify({"status": "not_running"})


@app.route("/api/campaign/status")
@require_token
def campaign_status():
    global _campaign_process
    running = _campaign_process is not None and _campaign_process.poll() is None
    return jsonify({"running": running, "pid": _campaign_process.pid if running else None})


# ── Logs em tempo real ─────────────────────────────────────────────────────

@app.route("/api/logs")
@require_token
def get_logs():
    """Retorna as últimas N linhas do log."""
    lines = int(request.args.get("lines", 50))
    log_path = os.path.join("logs", "savegram.log")
    if not os.path.exists(log_path):
        return jsonify({"lines": []})
    with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
        all_lines = f.readlines()
    return jsonify({"lines": [l.rstrip() for l in all_lines[-lines:]]})


# ── Leads disponíveis na fila ──────────────────────────────────────────────

@app.route("/api/channels/stats")
@require_token
def channels_stats():
    """Estatísticas detalhadas por canal de contato."""
    db = get_session()
    today = _today()

    ig = {
        "enviados_total": db.query(func.count(Lead.id)).filter(Lead.contacted == True).scalar(),
        "enviados_hoje":  db.query(func.count(Lead.id)).filter(Lead.contacted == True, func.date(Lead.contacted_at) == today).scalar(),
        "responderam":    db.query(func.count(Lead.id)).filter(Lead.contacted == True, Lead.responded == True).scalar(),
        "qualificados":   db.query(func.count(Lead.id)).filter(Lead.contacted == True, Lead.qualified == True).scalar(),
        "agendados":      db.query(func.count(Lead.id)).filter(Lead.contacted == True, Lead.call_scheduled == True).scalar(),
        "na_fila":        db.query(func.count(Lead.id)).filter(Lead.instagram_username != None, Lead.contacted == False, Lead.disqualified == False).scalar(),
    }

    wa = {
        "enviados_total": db.query(func.count(Lead.id)).filter(Lead.whatsapp_contacted == True).scalar(),
        "enviados_hoje":  db.query(func.count(Lead.id)).filter(Lead.whatsapp_contacted == True, func.date(Lead.whatsapp_contacted_at) == today).scalar(),
        "responderam":    db.query(func.count(Lead.id)).filter(Lead.whatsapp_contacted == True, Lead.responded == True).scalar(),
        "qualificados":   db.query(func.count(Lead.id)).filter(Lead.whatsapp_contacted == True, Lead.qualified == True).scalar(),
        "agendados":      db.query(func.count(Lead.id)).filter(Lead.whatsapp_contacted == True, Lead.call_scheduled == True).scalar(),
        "invalidos":      db.query(func.count(Lead.id)).filter(Lead.whatsapp_invalid == True).scalar(),
        "na_fila":        db.query(func.count(Lead.id)).filter(Lead.phone != None, Lead.whatsapp_contacted == False, Lead.whatsapp_invalid == False, Lead.disqualified == False).scalar(),
    }

    em = {
        "enviados_total": db.query(func.count(Lead.id)).filter(Lead.email_contacted == True).scalar(),
        "abertos":        db.query(func.count(Lead.id)).filter(Lead.email_opened == True).scalar(),
        "responderam":    db.query(func.count(Lead.id)).filter(Lead.email_replied == True).scalar(),
        "bounced":        db.query(func.count(Lead.id)).filter(Lead.email_bounced == True).scalar(),
        "agendados":      db.query(func.count(Lead.id)).filter(Lead.email_contacted == True, Lead.call_scheduled == True).scalar(),
        "na_fila":        db.query(func.count(Lead.id)).filter(Lead.email != None, Lead.email_contacted == False, Lead.disqualified == False).scalar(),
    }

    return jsonify({"instagram": ig, "whatsapp": wa, "email": em})


@app.route("/api/leads/queue")
@require_token
def leads_queue():
    """Leads prontos para contactar (não contatados, não desqualificados)."""
    db = get_session()
    ig_queue = db.query(func.count(Lead.id)).filter(
        Lead.instagram_username != None,
        Lead.contacted == False,
        Lead.disqualified == False,
        Lead.opted_out == False,
    ).scalar()
    wa_queue = db.query(func.count(Lead.id)).filter(
        Lead.phone != None,
        Lead.whatsapp_contacted == False,
        Lead.whatsapp_invalid == False,
        Lead.disqualified == False,
        Lead.opted_out == False,
    ).scalar()
    email_queue = db.query(func.count(Lead.id)).filter(
        Lead.email != None,
        Lead.email_contacted == False,
        Lead.disqualified == False,
        Lead.opted_out == False,
    ).scalar()
    return jsonify({
        "instagram": ig_queue,
        "whatsapp": wa_queue,
        "email": email_queue,
        "total": ig_queue + wa_queue + email_queue,
    })
