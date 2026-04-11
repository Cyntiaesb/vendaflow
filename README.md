# SaveGram Bot v2

Bot de prospecção multi-canal com Purchase Intent (Instagram + Apollo.io + WhatsApp).

## O que mudou da v1

| Feature | v1 | v2 |
|---|---|---|
| Fonte de leads | Instagram hashtag (frio) | Instagram + Apollo Intent (quente) |
| Canal de outreach | Só Instagram DM | Instagram DM + WhatsApp |
| Score de intent | ✗ | ✓ High / Medium / Low |
| Telefone / Email | ✗ | ✓ via Apollo enrichment |
| Filtro por localização | Parcial | ✓ Intent por cidade |
| Dashboard | 3 endpoints | 5 endpoints + webhook WA |

## Setup rápido

```bash
# 1. Ambiente virtual
python -m venv venv
source venv/bin/activate

# 2. Dependências
pip install -r requirements.txt

# 3. Configurar variáveis
cp .env.example .env
# Edite o .env — as novas chaves são APOLLO_API_KEY e EVOLUTION_API_KEY

# 4. Rodar o bot
python main.py

# 5. Dashboard (outro terminal)
python dashboard/app.py
```

## Configuração Apollo.io

1. Crie conta em https://app.apollo.io
2. Vá em Settings → Integrations → API Keys
3. Copie a API Key para `APOLLO_API_KEY` no `.env`
4. Defina `APOLLO_INTENT_KEYWORDS` com as palavras que seu cliente pesquisa
   - Exemplo para agência de marketing: `marketing digital,aumentar vendas,gerar leads`
5. Defina `APOLLO_LOCATION` com a cidade-alvo (ex: `São Paulo, BR`)

## Configuração Evolution API (WhatsApp)

1. Instale: https://github.com/EvolutionAPI/evolution-api (Docker recomendado)
2. Crie uma instância e escaneie o QR Code com seu WhatsApp
3. Configure `EVOLUTION_API_URL`, `EVOLUTION_API_KEY` e `EVOLUTION_INSTANCE` no `.env`
4. Aponte o webhook para: `POST http://seu-servidor:5000/webhook/whatsapp`

## Estrutura

```
savegram-bot/
├── config/
│   ├── settings.py           # Lê o .env (inclui Apollo + Evolution)
│   └── prompts.py            # Prompts Claude (Instagram + WhatsApp)
├── modules/
│   ├── ai/
│   │   └── claude_client.py  # Claude API (Instagram + WhatsApp)
│   ├── database/
│   │   └── models.py         # Lead model (+ phone, email, intent_score, source)
│   ├── instagram/
│   │   ├── scraper.py        # Coleta por hashtag/localização
│   │   ├── bot.py            # Envia DMs + processa respostas
│   │   └── account_manager.py
│   ├── prospecting/
│   │   └── apollo_client.py  # Purchase intent + enriquecimento ← NOVO
│   ├── scheduler/
│   │   └── calendly.py
│   └── whatsapp/
│       └── evolution_client.py  # WhatsApp via Evolution API ← NOVO
├── dashboard/
│   └── app.py                # API Flask + webhook WhatsApp
├── main.py                   # Pipeline completo
└── .env.example
```

## Pipeline diário

```
08:00  Instagram scraping (leads frios por hashtag)
08:30  Apollo intent search (leads quentes por keyword)
09:00  Apollo bulk enrich (adiciona telefone/email)
09:30  Instagram DM campaign
10:00  WhatsApp campaign (High intent primeiro)
*/30m  Verificação de respostas Instagram
```

## Endpoints do dashboard

| Endpoint | Descrição |
|---|---|
| `GET /api/stats` | Métricas completas (fonte, intent, canal, funil) |
| `GET /api/leads/recent` | Últimos 30 leads contatados |
| `GET /api/leads/qualified` | Leads com call agendada |
| `GET /api/leads/high-intent` | Fila High Intent ainda não abordados |
| `POST /webhook/whatsapp` | Recebe respostas da Evolution API |

## Avisos

- WhatsApp: comece com 20-30 msg/dia em instâncias novas e suba gradualmente
- Instagram: use delays de 20-60s e máx. 80 msg/dia por conta
- Apollo: plano básico tem ~50 créditos/mês de enriquecimento — use com critério
- Automação pode violar ToS das plataformas — use proxies residenciais para escala
