"""
Templates Meta WhatsApp — define, registra e gerencia HSMs.

Templates precisam ser aprovados pela Meta antes do uso (1–3 dias úteis).
Execute o setup UMA VEZ:

    python -m modules.whatsapp.templates

Para verificar status de aprovação:

    python -m modules.whatsapp.templates --status

─────────────────────────────────────────────────────────────────────
TEMPLATES DESTE PROJETO

1. savegram_primeiro_contato (MARKETING)
   Variáveis: {{1}} = nome, {{2}} = nicho
   Body: "Oi {{1}}! Vi que você atua em {{2}} e tenho algo que pode
          ajudar bastante o seu negócio. Posso te explicar em 2 minutos?"

2. savegram_follow_up (MARKETING)
   Variáveis: {{1}} = nome, {{2}} = nicho
   Body: "Oi {{1}}, tentei falar com você alguns dias atrás sobre
          soluções para {{2}}. Ainda faz sentido conversar rapidinho?"

3. savegram_agendar (UTILITY)
   Variáveis: {{1}} = nome, {{2}} = link Calendly
   Body: "Ótimo, {{1}}! Aqui está o link para escolher o melhor
          horário — são só 20 minutos: {{2}}"
─────────────────────────────────────────────────────────────────────
"""

import json
import logging
import requests
from config.settings import META_ACCESS_TOKEN, WHATSAPP_BUSINESS_ACCOUNT_ID, META_API_VERSION

logger = logging.getLogger(__name__)

BASE_URL = f"https://graph.facebook.com/{META_API_VERSION}"

# Nomes dos templates — altere aqui se quiser nomes diferentes
TEMPLATE_NAMES = {
    "primeiro_contato": "savegram_primeiro_contato",
    "follow_up":        "savegram_follow_up",
    "agendar":          "savegram_agendar",
}

# Definições completas dos templates
TEMPLATE_DEFINITIONS = [
    {
        "name": TEMPLATE_NAMES["primeiro_contato"],
        "category": "MARKETING",
        "language": "pt_BR",
        "components": [
            {
                "type": "BODY",
                "text": (
                    "Oi {{1}}! Vi que você atua em {{2}} e tenho algo que pode "
                    "ajudar bastante o seu negócio. Posso te explicar em 2 minutos?"
                ),
            },
            {
                "type": "FOOTER",
                "text": "Para parar de receber mensagens, responda SAIR.",
            },
        ],
    },
    {
        "name": TEMPLATE_NAMES["follow_up"],
        "category": "MARKETING",
        "language": "pt_BR",
        "components": [
            {
                "type": "BODY",
                "text": (
                    "Oi {{1}}, tentei falar com você alguns dias atrás sobre "
                    "soluções para {{2}}. Ainda faz sentido conversar rapidinho?"
                ),
            },
            {
                "type": "FOOTER",
                "text": "Para parar de receber mensagens, responda SAIR.",
            },
        ],
    },
    {
        "name": TEMPLATE_NAMES["agendar"],
        "category": "UTILITY",
        "language": "pt_BR",
        "components": [
            {
                "type": "BODY",
                "text": (
                    "Ótimo, {{1}}! Aqui está o link para escolher o melhor "
                    "horário — são só 20 minutos: {{2}}"
                ),
            },
        ],
    },
]


class TemplateManager:

    def __init__(self):
        self.headers = {
            "Authorization": f"Bearer {META_ACCESS_TOKEN}",
            "Content-Type": "application/json",
        }
        self.waba_id = WHATSAPP_BUSINESS_ACCOUNT_ID

    # ── Registro ──────────────────────────────────────────────────────

    def register_all(self) -> list[dict]:
        """
        Registra todos os templates na conta Meta.
        Retorna lista com status de cada submissão.
        Execute uma única vez.
        """
        results = []
        for tpl in TEMPLATE_DEFINITIONS:
            result = self.register_template(tpl)
            results.append({"name": tpl["name"], **result})
        return results

    def register_template(self, template_def: dict) -> dict:
        """Registra um template e retorna o resultado."""
        try:
            resp = requests.post(
                f"{BASE_URL}/{self.waba_id}/message_templates",
                headers=self.headers,
                json=template_def,
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            logger.info(
                f"[Templates] '{template_def['name']}' submetido — "
                f"id: {data.get('id')}, status: {data.get('status')}"
            )
            return {"status": data.get("status", "PENDING"), "id": data.get("id")}
        except Exception as e:
            logger.error(f"[Templates] Erro ao registrar '{template_def['name']}': {e}")
            return {"status": "ERROR", "error": str(e)}

    # ── Status ────────────────────────────────────────────────────────

    def get_all_statuses(self) -> list[dict]:
        """Retorna o status de aprovação de todos os templates da conta."""
        try:
            resp = requests.get(
                f"{BASE_URL}/{self.waba_id}/message_templates",
                headers=self.headers,
                params={"fields": "name,status,category,language"},
                timeout=15,
            )
            resp.raise_for_status()
            templates = resp.json().get("data", [])

            # Filtra só os templates deste projeto
            our_names = set(TEMPLATE_NAMES.values())
            return [t for t in templates if t.get("name") in our_names]
        except Exception as e:
            logger.error(f"[Templates] Erro ao buscar status: {e}")
            return []

    def are_templates_approved(self) -> bool:
        """Retorna True se todos os templates necessários estão aprovados."""
        statuses = self.get_all_statuses()
        approved = {t["name"] for t in statuses if t.get("status") == "APPROVED"}
        required = set(TEMPLATE_NAMES.values())
        missing  = required - approved

        if missing:
            logger.warning(f"[Templates] Templates pendentes de aprovação: {missing}")
            return False
        return True

    def check_and_print(self) -> None:
        """Exibe status atual de cada template no console."""
        statuses = self.get_all_statuses()
        status_map = {t["name"]: t["status"] for t in statuses}

        print("\n📋 Status dos templates Meta WhatsApp:")
        print("-" * 55)
        for key, name in TEMPLATE_NAMES.items():
            status = status_map.get(name, "NÃO ENCONTRADO")
            icon   = "✅" if status == "APPROVED" else "⏳" if status in ("PENDING", "IN_APPEAL") else "❌"
            print(f"  {icon} {name} → {status}")
        print("-" * 55)

        if all(status_map.get(n) == "APPROVED" for n in TEMPLATE_NAMES.values()):
            print("✅ Todos os templates aprovados — WhatsApp pronto para uso!\n")
        else:
            print("⏳ Aguardando aprovação da Meta (1–3 dias úteis)\n")


# ── CLI ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    from dotenv import load_dotenv
    load_dotenv()

    mgr = TemplateManager()

    if "--status" in sys.argv:
        mgr.check_and_print()
    else:
        print("🚀 Registrando templates no Meta WhatsApp...\n")
        results = mgr.register_all()
        for r in results:
            icon = "✅" if r["status"] not in ("ERROR",) else "❌"
            print(f"  {icon} {r['name']}: {r['status']}")
        print(
            "\n⏳ Templates submetidos para aprovação da Meta.\n"
            "Execute 'python -m modules.whatsapp.templates --status' para verificar.\n"
            "Aprovação leva 1–3 dias úteis.\n"
        )
