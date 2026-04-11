# 02 — Arquitetura VendasFlow

## Visão geral

```
OUTBOUND                          INBOUND
Google Maps                       Meta Ads / Google Ads
     │                                    │
     ▼                                    ▼
n8n (Prospecção)              n8n (Webhook Lead Ads)
     │                                    │
     └──────────────┬─────────────────────┘
                    ▼
           WhatsApp Cloud API
                    │
                    ▼
            n8n (Conversa)
                    │
                    ▼
              Claude API
            (raciocínio + resposta)
                    │
                    ▼
              Supabase (CRM)
            (salva histórico, status, dados)
                    │
                    ▼
         [status = CALL AGENDADA?]
                    │ SIM
                    ▼
               Cal.com API
            (cria link de reunião)
                    │
                    ▼
         Envia link pelo WhatsApp
```

---

## Fluxo de uma conversa (passo a passo)

```
1. Lead chega (outbound ou inbound)
2. n8n salva lead no Supabase com status=NOVO
3. n8n dispara primeira mensagem pelo WhatsApp
4. Lead responde → WhatsApp envia webhook para n8n
5. n8n busca histórico do lead no Supabase
6. n8n monta contexto e chama Claude API
7. Claude gera resposta + decisão (continuar / qualificar / agendar)
8. n8n envia resposta pelo WhatsApp
9. n8n atualiza status e histórico no Supabase
10. [Se CALL AGENDADA] → n8n cria evento no Cal.com → envia link
11. Follow-up automático: n8n verifica leads parados a cada 24h/48h
```

---

## Workflows n8n (mapa)

| Workflow | Trigger | O que faz |
|---|---|---|
| `outbound-prospeccao` | Manual / Agendado | Busca empresas no Google Maps, filtra, dispara 1ª mensagem |
| `inbound-lead-ads` | Webhook Meta/Google | Recebe lead do anúncio, salva, dispara 1ª mensagem |
| `conversa-whatsapp` | Webhook WhatsApp | Processa mensagem recebida, chama Claude, responde |
| `followup-automatico` | Cron (diário) | Verifica leads parados, dispara follow-up 24h e 48h |
| `reativacao-30dias` | Cron (mensal) | Reativa leads inativos há 30 dias |
| `agendamento` | Chamado internamente | Cria evento Cal.com, envia link, atualiza status |

---

## Estrutura do banco (Supabase)

```
tenants
  id, nome, config_json, created_at

leads
  id, tenant_id, nome, telefone, empresa, segmento, cidade
  status, fonte, historico_json, criado_em, atualizado_em

conversas
  id, lead_id, tenant_id, role (user/assistant), conteudo, created_at

agendamentos
  id, lead_id, tenant_id, link_cal, data_hora, status, created_at

campanhas
  id, tenant_id, tipo (meta_ads/google_ads), nome, status, config_json
```

---

## Funil de status

```
NOVO → QUALIFICANDO → INTERESSE → CALL AGENDADA → CONCLUÍDO
                                                 → PERDIDO
```

| Status | Significado |
|---|---|
| `NOVO` | Lead recém-chegado, ainda não respondeu |
| `QUALIFICANDO` | Conversa em andamento, Claude coletando informações |
| `INTERESSE` | Lead demonstrou interesse, próximo passo é agendar |
| `CALL AGENDADA` | Reunião marcada no Cal.com |
| `CONCLUÍDO` | Processo finalizado (venda fechada ou descartado positivamente) |
| `PERDIDO` | Sem resposta após todos os follow-ups |

---

## Ambientes

| Ambiente | n8n | Supabase | Notas |
|---|---|---|---|
| **Produção** | cyntiaesb.app.n8n.cloud | projeto vendasflow | Dados reais |
| **Local (futuro)** | localhost:5678 | mesmo projeto (cuidado) | Testes de workflow |

---

## Decisões de arquitetura

- **n8n como orquestrador:** toda lógica de fluxo vive no n8n, não em código
- **Claude só responde, não decide o estado:** quem atualiza o Supabase é sempre o n8n
- **Histórico de conversa no Supabase:** Claude recebe o histórico a cada chamada (stateless)
- **Multi-tenant por `tenant_id`:** todo registro tem tenant_id, RLS garante isolamento
- **WhatsApp Cloud API direta:** sem intermediários (não 360dialog)
