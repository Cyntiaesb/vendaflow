# 99 — Referência Completa para LLMs

> Este arquivo é otimizado para ser usado como contexto em LLMs. Contém as regras e estruturas essenciais do VendasFlow de forma concisa.

---

## O que é o VendasFlow

Plataforma de vendas automatizada multi-tenant. Prospecta leads (outbound via Google Maps e inbound via Meta/Google Ads), conversa via WhatsApp usando Claude como IA, qualifica e agenda reuniões no Cal.com. O cliente só aparece na call.

---

## Stack

- **n8n** (cyntiaesb.app.n8n.cloud) — orquestrador de workflows
- **Claude API** (claude-opus-4-6) — inteligência das conversas
- **Supabase** (projeto vendasflow) — banco PostgreSQL + Auth
- **WhatsApp Cloud API** (oficial Meta) — canal de comunicação
- **Google Maps Places API** — fonte de leads outbound
- **Cal.com** — agendamento de reuniões

---

## Regras invioláveis

1. n8n orquestra — não armazena estado
2. Claude responde — não executa ações
3. Supabase é a fonte de verdade
4. Toda tabela tem `tenant_id` (multi-tenant)
5. Nunca deletar leads — usar `deleted_at`
6. `service_role key` nunca no frontend

---

## Funil de status

`NOVO → QUALIFICANDO → INTERESSE → CALL_AGENDADA → CONCLUIDO | PERDIDO`

---

## Schema principal

```sql
tenants(id, nome, config_json, created_at)
leads(id, tenant_id, nome, telefone, empresa, segmento, cidade, status, fonte, historico_json, created_at, updated_at, deleted_at)
conversas(id, lead_id, tenant_id, role, conteudo, created_at)
agendamentos(id, lead_id, tenant_id, link_cal, data_hora, status, created_at)
campanhas(id, tenant_id, tipo, nome, status, config_json, created_at)
logs_erro(id, workflow, erro, lead_id, tenant_id, created_at)
```

---

## Workflows n8n

| Workflow | Trigger | Função |
|---|---|---|
| `conversa-whatsapp` | Webhook WhatsApp | Processa mensagem, chama Claude, responde |
| `outbound-prospeccao` | Manual/Cron | Busca no Maps, dispara 1ª mensagem |
| `inbound-lead-ads` | Webhook Meta/Google | Recebe lead de anúncio, inicia conversa |
| `followup-automatico` | Cron diário 09h | Follow-up 24h, 48h e reativação 30 dias |
| `agendamento` | Interno | Cria Cal.com, envia link, atualiza status |

---

## Chamada Claude API

```
POST https://api.anthropic.com/v1/messages
Headers: x-api-key, anthropic-version: 2023-06-01
Body: { model, max_tokens: 500, system, messages }
Resposta esperada: JSON { resposta, proximo_status, agendar, dados_coletados }
```

---

## Nomenclatura

- Workflows n8n: kebab-case (`conversa-whatsapp`)
- Tabelas: snake_case plural (`leads`, `conversas`)
- Colunas: snake_case (`tenant_id`, `created_at`)
- Status/enum: UPPER_SNAKE (`CALL_AGENDADA`)
- Env vars: UPPER_SNAKE com prefixo de serviço (`WHATSAPP_TOKEN`)

---

## Variáveis de ambiente necessárias

```
CLAUDE_API_KEY
WHATSAPP_TOKEN
PHONE_NUMBER_ID
WHATSAPP_VERIFY_TOKEN
SUPABASE_URL
SUPABASE_ANON_KEY
SUPABASE_SERVICE_ROLE_KEY
GOOGLE_MAPS_API_KEY
CALCOM_API_KEY
```
