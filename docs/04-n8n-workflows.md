# 04 — Guia de Workflows n8n

## Filosofia

- Cada workflow tem **uma responsabilidade**
- O n8n **orquestra** — não armazena estado (isso é responsabilidade do Supabase)
- Todo erro deve ser capturado e logado no Supabase
- Workflows longos devem ter **nós de checkpoint** (salvar progresso parcial)

---

## Estrutura padrão de um workflow

```
[Trigger]
    │
[Validação de entrada]
    │
[Busca contexto no Supabase]
    │
[Lógica principal]
    │
[Ação externa (Claude / WhatsApp / Cal.com)]
    │
[Salva resultado no Supabase]
    │
[Resposta / próximo passo]
```

---

## Workflow: `conversa-whatsapp`

### Trigger
- Webhook POST recebendo payload do WhatsApp Cloud API

### Payload de entrada (WhatsApp)
```json
{
  "entry": [{
    "changes": [{
      "value": {
        "messages": [{
          "from": "5511999999999",
          "text": { "body": "Olá, tenho interesse" }
        }]
      }
    }]
  }]
}
```

### Nós do workflow

1. **Webhook** — recebe mensagem
2. **Extract Data** — extrai `telefone` e `mensagem` do payload
3. **Supabase: buscar lead** — `SELECT * FROM leads WHERE telefone = $1 AND tenant_id = $2`
4. **IF: lead existe?**
   - NÃO → criar lead com status=NOVO
   - SIM → continuar
5. **Supabase: buscar histórico** — últimas 10 mensagens da `conversas`
6. **Salvar mensagem do usuário** — INSERT em `conversas` (role=user)
7. **Claude API** — monta prompt com histórico + mensagem atual
8. **Extract decisão** — parseia resposta do Claude (resposta + próximo_status)
9. **Atualizar lead** — UPDATE status no Supabase
10. **Salvar resposta** — INSERT em `conversas` (role=assistant)
11. **IF: agendar?** → chama workflow `agendamento`
12. **WhatsApp: enviar mensagem** — POST na Cloud API

---

## Workflow: `outbound-prospeccao`

### Trigger
- Manual ou agendado (cron)

### Parâmetros de entrada
```json
{
  "segmento": "restaurante",
  "cidade": "São Paulo",
  "limite": 50,
  "tenant_id": "uuid"
}
```

### Nós do workflow

1. **Google Maps Places API** — busca empresas por segmento + cidade
2. **Loop: para cada empresa**
3. **Supabase: verificar duplicata** — telefone já existe em leads?
4. **IF: novo?** → salva lead com status=NOVO e fonte=OUTBOUND
5. **Delay** — 3-5 segundos entre disparos (evitar bloqueio)
6. **WhatsApp: enviar 1ª mensagem** — template personalizado por segmento
7. **Log resultado** — salva sucesso/erro no Supabase

---

## Workflow: `followup-automatico`

### Trigger
- Cron: todo dia às 09:00

### Lógica

1. **Supabase: busca leads parados**
   - status IN ('NOVO', 'QUALIFICANDO', 'INTERESSE')
   - última mensagem há mais de 24h (followup 1)
   - última mensagem há mais de 48h (followup 2)
   - última mensagem há mais de 30 dias (reativação)
2. **Para cada lead:**
   - Define qual mensagem de follow-up enviar
   - Envia pelo WhatsApp
   - Registra na tabela `conversas`
3. **Se > 3 follow-ups sem resposta:** status = PERDIDO

---

## Workflow: `agendamento`

### Chamado por: `conversa-whatsapp` quando Claude decide agendar

### Nós

1. **Cal.com API** — cria booking slot disponível
2. **Retorna link** de agendamento
3. **WhatsApp** — envia link para o lead
4. **Supabase** — UPDATE lead status=CALL_AGENDADA, salva link em `agendamentos`

---

## Padrão de chamada Claude API

### Estrutura do prompt

```json
{
  "model": "claude-opus-4-6",
  "max_tokens": 500,
  "system": "[SYSTEM PROMPT DO TENANT]",
  "messages": [
    {"role": "user", "content": "Histórico: ...\n\nMensagem atual: ..."}
  ]
}
```

### System prompt padrão (base)

```
Você é um assistente de vendas da [EMPRESA]. Seu papel é conversar de forma natural e humana com potenciais clientes pelo WhatsApp.

Regras:
- Seja direto, amigável, nunca robótico
- Nunca revele que é uma IA
- Colete: nome, empresa, segmento, principal dor
- Quando houver interesse claro, proponha uma call
- Responda em no máximo 2-3 frases
- Não use emojis em excesso

Retorne SEMPRE neste formato JSON:
{
  "resposta": "texto para enviar ao lead",
  "proximo_status": "QUALIFICANDO|INTERESSE|CALL_AGENDADA|PERDIDO|null",
  "agendar": true|false
}
```

---

## Tratamento de erros

Todo workflow deve ter:

1. **Nó de Error Trigger** conectado ao final
2. **INSERT em tabela `logs_erro`** com: workflow, erro, lead_id, created_at
3. **Nunca deixar o lead sem resposta** — fallback genérico se Claude falhar

```sql
-- Tabela de logs
CREATE TABLE logs_erro (
  id uuid DEFAULT gen_random_uuid(),
  workflow text,
  erro text,
  lead_id uuid REFERENCES leads(id),
  tenant_id uuid REFERENCES tenants(id),
  created_at timestamptz DEFAULT now()
);
```

---

## Credenciais necessárias no n8n

| Credencial | Tipo | Nome sugerido |
|---|---|---|
| WhatsApp Cloud API | HTTP Header Auth | `whatsapp-prod` |
| Supabase | Header Auth (service role) | `supabase-prod` |
| Claude API | HTTP Header Auth | `claude-prod` |
| Google Maps | Query Param | `googlemaps-prod` |
| Cal.com | API Key | `calcom-prod` |
