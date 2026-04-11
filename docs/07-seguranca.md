# 07 — Segurança

## Variáveis de ambiente

- **Nunca** hardcodar tokens no workflow ou no código
- Usar as credenciais do n8n para armazenar API keys
- `.env` nunca vai para o git — usar `.env.example` com valores em branco

---

## Webhook WhatsApp (verificação)

O WhatsApp envia um GET de verificação antes de aceitar o webhook:

```javascript
// Code node no n8n — verificação do webhook
const mode = $input.params['hub.mode'];
const token = $input.params['hub.verify_token'];
const challenge = $input.params['hub.challenge'];

if (mode === 'subscribe' && token === process.env.WHATSAPP_VERIFY_TOKEN) {
  return [{ json: { response: challenge } }];
}

return [{ json: { error: 'Forbidden' } }];
```

O `WHATSAPP_VERIFY_TOKEN` deve ser uma string aleatória longa — você define, a Meta usa para confirmar.

---

## Supabase: chaves

| Chave | Uso | Expõe ao frontend? |
|---|---|---|
| `anon key` | Frontend (com RLS ativo) | SIM |
| `service_role key` | n8n e backends (bypassa RLS) | **NUNCA** |

---

## Rate limiting WhatsApp

- Máximo de mensagens por número: respeitar limites da Meta
- Adicionar delay de 3-5 segundos entre disparos no outbound
- Não disparar mais de 200 mensagens/hora por número novo

---

## RLS no Supabase

Todo acesso via frontend deve passar por RLS. Verificar:

```sql
-- Confirmar que RLS está ativo
SELECT schemaname, tablename, rowsecurity
FROM pg_tables
WHERE schemaname = 'public';
```

---

## Checklist de segurança pré-deploy

- [ ] Todas as API keys em variáveis de ambiente / credenciais n8n
- [ ] `service_role key` nunca exposta em frontend
- [ ] RLS ativo em todas as tabelas de dados sensíveis
- [ ] Webhook WhatsApp com verify_token configurado
- [ ] Workflows com tratamento de erro (não expor stack trace)
- [ ] `.env` no `.gitignore`
- [ ] Rotação de tokens programada (a cada 90 dias)
