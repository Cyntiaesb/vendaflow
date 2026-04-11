# 01 — Onboarding VendasFlow

## O que é o VendasFlow?

Plataforma de vendas automatizada multi-tenant. Ela prospecta, conversa, qualifica e agenda reuniões sozinha — o cliente só aparece na call.

---

## Filosofia do projeto

- **Automação como produto:** o sistema vende enquanto ninguém está olhando
- **IA como vendedor:** Claude conversa como humano, não como bot
- **Multi-tenant:** cada cliente tem seu próprio funil, painel e configurações
- **Dados centralizados:** tudo passa pelo Supabase — n8n orquestra, não armazena

---

## Glossário técnico

| Termo | O que é | Onde aparece |
|---|---|---|
| **n8n** | Orquestrador de workflows — conecta APIs, dispara ações, processa dados | Motor do sistema |
| **Workflow** | Fluxo visual de automação no n8n (equivalente a um programa) | n8n.cloud |
| **Node** | Cada passo dentro de um workflow (ex: "chamar Claude", "salvar no Supabase") | n8n |
| **Webhook** | URL que recebe eventos externos (ex: mensagem chegou no WhatsApp) | n8n |
| **Supabase** | Banco de dados PostgreSQL + Auth + Storage + Realtime na nuvem | Backend/CRM |
| **RLS** | Row Level Security — regra que impede um tenant ver dados de outro | Supabase |
| **Claude API** | API da Anthropic que dá inteligência às conversas | Dentro dos workflows |
| **System Prompt** | Instruções iniciais que definem a personalidade e regras do Claude | Workflows de conversa |
| **WhatsApp Cloud API** | API oficial da Meta para enviar/receber mensagens WhatsApp | Workflow de disparo |
| **Lead** | Contato prospectado que ainda não comprou | Tabela `leads` no Supabase |
| **Funil** | Jornada do lead: NOVO → QUALIFICANDO → INTERESSE → CALL AGENDADA → CONCLUÍDO | Coluna `status` |
| **Tenant** | Cliente da plataforma (empresa que usa o VendasFlow) | Tabela `tenants` |
| **Cal.com** | Ferramenta de agendamento — gera link de reunião automaticamente | Workflow de agendamento |
| **Google Maps Places API** | API para buscar empresas por segmento e cidade | Workflow de prospecção |
| **Outbound** | Prospecção ativa — o sistema vai atrás do lead | Workflow outbound |
| **Inbound** | Prospecção passiva — lead vem pelos anúncios | Workflow inbound |

---

## Stack completa

| Tecnologia | Papel | Por que? |
|---|---|---|
| **n8n** | Orquestrador | Visual, poderoso, sem código, self-hostable |
| **Claude API** | Inteligência das conversas | Melhor em raciocínio e tom humano |
| **Supabase** | Banco + Auth + Realtime | PostgreSQL gerenciado, RLS nativo, dashboard |
| **WhatsApp Cloud API** | Canal de prospecção | API oficial Meta, sem intermediários |
| **Google Maps Places API** | Fonte de leads outbound | Base de dados de empresas locais |
| **Meta Ads + Google Ads** | Fonte de leads inbound | Escala de geração de leads paga |
| **Cal.com** | Agendamento | Open source, API simples |

---

## Variáveis de ambiente

```env
# Claude
CLAUDE_API_KEY=

# WhatsApp
WHATSAPP_TOKEN=
PHONE_NUMBER_ID=
WHATSAPP_VERIFY_TOKEN=

# Supabase
SUPABASE_URL=
SUPABASE_ANON_KEY=
SUPABASE_SERVICE_ROLE_KEY=

# Google Maps
GOOGLE_MAPS_API_KEY=

# Cal.com
CALCOM_API_KEY=

# n8n
N8N_ENCRYPTION_KEY=
N8N_URL=https://cyntiaesb.app.n8n.cloud
```

---

## Checklist do primeiro dia

- [ ] Ler este arquivo (01)
- [ ] Ler 02-arquitetura.md
- [ ] Ler 03-nomenclatura.md
- [ ] Ler 04-n8n-workflows.md
- [ ] Acessar n8n: https://cyntiaesb.app.n8n.cloud
- [ ] Acessar Supabase: projeto vendasflow
- [ ] Verificar .env preenchido
- [ ] Importar workflows do n8n
- [ ] Testar webhook de entrada WhatsApp
