# 06 — Claude API (Conversas e Inteligência)

## Papel do Claude no VendasFlow

Claude **não gerencia estado** — isso é função do n8n + Supabase.
Claude **recebe contexto, raciocina e responde**.

A cada mensagem recebida, o n8n monta o contexto completo e envia para o Claude. O Claude retorna a resposta + decisão de próximo passo.

---

## Modelo recomendado

```
claude-opus-4-6  → produção (melhor raciocínio, mais humano)
claude-haiku-4-5-20251001 → fallback/economia (respostas simples)
```

---

## Estrutura da chamada (HTTP via n8n)

**Endpoint:** `https://api.anthropic.com/v1/messages`
**Method:** POST
**Headers:**
```
x-api-key: {{CLAUDE_API_KEY}}
anthropic-version: 2023-06-01
content-type: application/json
```

**Body:**
```json
{
  "model": "claude-opus-4-6",
  "max_tokens": 500,
  "system": "{{system_prompt}}",
  "messages": [
    {
      "role": "user",
      "content": "{{contexto_montado}}"
    }
  ]
}
```

---

## Como montar o contexto (no n8n)

```javascript
// Code node no n8n
const historico = items[0].json.historico; // array de conversas
const mensagem_atual = items[0].json.mensagem;
const dados_lead = items[0].json.lead;

const historico_formatado = historico
  .reverse()
  .map(c => `${c.role === 'user' ? 'Lead' : 'Assistente'}: ${c.conteudo}`)
  .join('\n');

const contexto = `
DADOS DO LEAD:
- Nome: ${dados_lead.nome || 'não informado'}
- Empresa: ${dados_lead.empresa || 'não informada'}
- Segmento: ${dados_lead.segmento || 'não informado'}
- Status atual: ${dados_lead.status}

HISTÓRICO DA CONVERSA:
${historico_formatado}

MENSAGEM ATUAL DO LEAD:
${mensagem_atual}
`;

return [{ json: { contexto } }];
```

---

## System prompt base (copiar e personalizar por tenant)

```
Você é um assistente de vendas da [NOME DA EMPRESA]. Seu objetivo é qualificar potenciais clientes e agendar reuniões.

COMPORTAMENTO:
- Seja natural, humano, direto. Nunca robótico.
- Nunca revele que é uma IA se perguntado diretamente — diga que é um assistente da empresa.
- Responda em no máximo 2-3 frases curtas.
- Não use emojis em excesso (máximo 1 por mensagem, se necessário).
- Use linguagem informal mas profissional.

OBJETIVO DA CONVERSA:
1. Entender o negócio do lead (segmento, tamanho, dor principal)
2. Apresentar brevemente a solução
3. Propor uma call de 30 minutos quando houver interesse

INFORMAÇÕES QUE DEVE COLETAR:
- Nome completo
- Nome da empresa
- Principal desafio/dor

QUANDO AGENDAR:
- Lead demonstra interesse claro
- Lead pergunta sobre preço, detalhes, próximos passos
- Lead pede mais informações que precisam de explicação mais profunda

RETORNE SEMPRE NESTE FORMATO JSON (sem texto fora do JSON):
{
  "resposta": "texto para enviar ao lead via WhatsApp",
  "proximo_status": "QUALIFICANDO" | "INTERESSE" | "CALL_AGENDADA" | "PERDIDO" | null,
  "agendar": true | false,
  "dados_coletados": {
    "nome": "string ou null",
    "empresa": "string ou null",
    "segmento": "string ou null",
    "dor": "string ou null"
  }
}
```

---

## Parsear resposta do Claude (no n8n)

```javascript
// Code node após a chamada Claude
const raw = items[0].json.content[0].text;

let parsed;
try {
  // Remove possível markdown code block
  const clean = raw.replace(/```json\n?|\n?```/g, '').trim();
  parsed = JSON.parse(clean);
} catch (e) {
  // Fallback se Claude não retornar JSON válido
  parsed = {
    resposta: "Obrigado pela mensagem! Deixa eu verificar aqui e te respondo em instantes.",
    proximo_status: null,
    agendar: false,
    dados_coletados: {}
  };
}

return [{ json: parsed }];
```

---

## Limites e boas práticas

| Parâmetro | Valor recomendado | Por quê |
|---|---|---|
| `max_tokens` | 500 | Respostas curtas para WhatsApp |
| Histórico | Últimas 10 mensagens | Evitar context window longa |
| Timeout n8n | 30 segundos | Claude pode demorar em picos |
| Retry | 1x em erro 529 | Rate limit da API |

---

## Anti-patterns

| Erro | Como evitar |
|---|---|
| Enviar histórico inteiro (centenas de mensagens) | Limitar a 10 últimas |
| Não validar JSON de resposta | Sempre usar try/catch com fallback |
| Usar Claude para decidir E executar ações | Claude só decide — n8n executa |
| System prompt sem instrução de formato | Sempre exigir JSON estruturado |
