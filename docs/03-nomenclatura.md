# 03 — Nomenclatura e Padrões VendasFlow

## Regra geral

- **Código e nomes técnicos:** inglês
- **Textos, comentários, documentação:** português (Brasil)
- **Dúvida?** Consulte este arquivo antes de nomear qualquer coisa

---

## Workflows n8n

| Regra | CERTO | ERRADO |
|---|---|---|
| kebab-case, verbo-substantivo | `outbound-prospeccao` | `OutboundProspeccao`, `outbound_prospeccao` |
| Prefixo pelo tipo | `conversa-whatsapp`, `followup-automatico` | `whatsapp`, `auto` |
| Descritivo, sem abreviações | `reativacao-30dias` | `reativ30`, `r30d` |

---

## Tabelas Supabase

| Regra | CERTO | ERRADO |
|---|---|---|
| snake_case, plural | `leads`, `conversas`, `agendamentos` | `Lead`, `Conversa`, `tblAgendamento` |
| Chave estrangeira: `{tabela}_id` | `tenant_id`, `lead_id` | `tenantID`, `idLead` |
| Timestamps padronizados | `created_at`, `updated_at` | `criado`, `data_criacao` |
| Soft delete | `deleted_at` (nullable) | coluna `ativo` boolean |

---

## Colunas e campos

| Tipo | Padrão | Exemplo |
|---|---|---|
| Texto | snake_case | `nome`, `telefone`, `empresa` |
| Status/enum | UPPER_SNAKE | `NOVO`, `QUALIFICANDO`, `CALL_AGENDADA` |
| JSON/config | sufixo `_json` | `historico_json`, `config_json` |
| Booleano | prefixo `is_` | `is_active`, `is_verified` |
| Data/hora | sufixo `_at` ou `_em` | `created_at`, `agendado_em` |

---

## Variáveis de ambiente

| Regra | CERTO | ERRADO |
|---|---|---|
| UPPER_SNAKE | `CLAUDE_API_KEY` | `claudeApiKey`, `claude_key` |
| Prefixo por serviço | `WHATSAPP_TOKEN`, `SUPABASE_URL` | `TOKEN`, `URL` |
| Sem valores default no .env | usar `.env.example` | hardcode no workflow |

---

## Nomes de credenciais no n8n

| Regra | CERTO | ERRADO |
|---|---|---|
| Serviço + ambiente | `supabase-prod`, `whatsapp-prod` | `minha-chave`, `key1` |
| Nunca reutilizar entre tenants | uma credencial por serviço | compartilhar tokens |

---

## Status do funil (enum)

Sempre UPPER_SNAKE, sempre em inglês no banco:

```
NOVO
QUALIFICANDO
INTERESSE
CALL_AGENDADA
CONCLUIDO
PERDIDO
```

---

## Campos de histórico de conversa

```json
{
  "role": "user" | "assistant",
  "conteudo": "texto da mensagem",
  "created_at": "ISO 8601"
}
```

---

## Cheat Sheet

| O que nomear | Padrão | Exemplo |
|---|---|---|
| Workflow n8n | kebab-case | `conversa-whatsapp` |
| Tabela Supabase | snake_case plural | `leads` |
| Coluna | snake_case | `tenant_id` |
| Status/enum | UPPER_SNAKE | `CALL_AGENDADA` |
| Variável de ambiente | UPPER_SNAKE com prefixo | `CALCOM_API_KEY` |
| Credencial n8n | serviço-ambiente | `supabase-prod` |
| Campo JSON | sufixo `_json` | `config_json` |
