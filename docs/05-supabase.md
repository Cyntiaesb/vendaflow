# 05 — Supabase (Banco + Auth)

## Schema completo

```sql
-- Tenants (clientes da plataforma)
CREATE TABLE tenants (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  nome text NOT NULL,
  config_json jsonb DEFAULT '{}',
  created_at timestamptz DEFAULT now()
);

-- Leads
CREATE TABLE leads (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  tenant_id uuid REFERENCES tenants(id) NOT NULL,
  nome text,
  telefone text NOT NULL,
  empresa text,
  segmento text,
  cidade text,
  status text DEFAULT 'NOVO' CHECK (status IN ('NOVO','QUALIFICANDO','INTERESSE','CALL_AGENDADA','CONCLUIDO','PERDIDO')),
  fonte text CHECK (fonte IN ('OUTBOUND','INBOUND_META','INBOUND_GOOGLE')),
  historico_json jsonb DEFAULT '[]',
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now(),
  deleted_at timestamptz
);

-- Conversas
CREATE TABLE conversas (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  lead_id uuid REFERENCES leads(id) NOT NULL,
  tenant_id uuid REFERENCES tenants(id) NOT NULL,
  role text CHECK (role IN ('user','assistant')),
  conteudo text NOT NULL,
  created_at timestamptz DEFAULT now()
);

-- Agendamentos
CREATE TABLE agendamentos (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  lead_id uuid REFERENCES leads(id) NOT NULL,
  tenant_id uuid REFERENCES tenants(id) NOT NULL,
  link_cal text,
  data_hora timestamptz,
  status text DEFAULT 'PENDENTE' CHECK (status IN ('PENDENTE','CONFIRMADO','CANCELADO','REALIZADO')),
  created_at timestamptz DEFAULT now()
);

-- Campanhas
CREATE TABLE campanhas (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  tenant_id uuid REFERENCES tenants(id) NOT NULL,
  tipo text CHECK (tipo IN ('META_ADS','GOOGLE_ADS','OUTBOUND')),
  nome text NOT NULL,
  status text DEFAULT 'ATIVA',
  config_json jsonb DEFAULT '{}',
  created_at timestamptz DEFAULT now()
);

-- Logs de erro
CREATE TABLE logs_erro (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  workflow text,
  erro text,
  lead_id uuid REFERENCES leads(id),
  tenant_id uuid REFERENCES tenants(id),
  created_at timestamptz DEFAULT now()
);
```

---

## Row Level Security (RLS)

Habilitar RLS em todas as tabelas para isolamento multi-tenant.

```sql
-- Habilitar RLS
ALTER TABLE leads ENABLE ROW LEVEL SECURITY;
ALTER TABLE conversas ENABLE ROW LEVEL SECURITY;
ALTER TABLE agendamentos ENABLE ROW LEVEL SECURITY;
ALTER TABLE campanhas ENABLE ROW LEVEL SECURITY;

-- Política: usuário só vê dados do seu tenant
-- (usado com Supabase Auth — o JWT contém o tenant_id)
CREATE POLICY "tenant_isolation_leads" ON leads
  USING (tenant_id = (auth.jwt() ->> 'tenant_id')::uuid);

CREATE POLICY "tenant_isolation_conversas" ON conversas
  USING (tenant_id = (auth.jwt() ->> 'tenant_id')::uuid);
```

> **n8n usa service_role key** (ignora RLS) — sempre passar `tenant_id` explicitamente nas queries.

---

## Queries mais usadas

### Buscar lead por telefone
```sql
SELECT * FROM leads
WHERE telefone = '5511999999999'
  AND tenant_id = 'uuid-do-tenant'
  AND deleted_at IS NULL
LIMIT 1;
```

### Buscar histórico de conversa (últimas 10)
```sql
SELECT role, conteudo, created_at
FROM conversas
WHERE lead_id = 'uuid-do-lead'
ORDER BY created_at DESC
LIMIT 10;
```

### Leads para follow-up (parados há 24h)
```sql
SELECT l.* FROM leads l
LEFT JOIN conversas c ON c.lead_id = l.id
WHERE l.status IN ('NOVO', 'QUALIFICANDO', 'INTERESSE')
  AND l.tenant_id = 'uuid-do-tenant'
  AND l.deleted_at IS NULL
GROUP BY l.id
HAVING MAX(c.created_at) < NOW() - INTERVAL '24 hours'
   OR MAX(c.created_at) IS NULL;
```

### Atualizar status do lead
```sql
UPDATE leads
SET status = 'CALL_AGENDADA', updated_at = NOW()
WHERE id = 'uuid-do-lead'
  AND tenant_id = 'uuid-do-tenant';
```

---

## Soft delete

Nunca deletar leads. Usar `deleted_at`:

```sql
UPDATE leads SET deleted_at = NOW() WHERE id = 'uuid';
```

Todas as queries devem ter `AND deleted_at IS NULL`.

---

## Índices importantes

```sql
CREATE INDEX idx_leads_telefone ON leads(telefone);
CREATE INDEX idx_leads_tenant_status ON leads(tenant_id, status);
CREATE INDEX idx_conversas_lead ON conversas(lead_id, created_at DESC);
```
