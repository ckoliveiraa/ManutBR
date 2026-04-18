# PRD — ManutBR: Produto de Dados de Gestão de Manutenção Industrial

**Versão:** 1.0  
**Data:** 2026-04-18  
**Autor:** Carlos Oliveira  
**Status:** Em desenvolvimento

---

## 1. Visão do Produto

**ManutBR** é um produto de dados end-to-end para gestão de manutenção industrial, construído sobre GCP. Ele conecta dados operacionais brutos (ordens de serviço, equipamentos, técnicos) a KPIs estratégicos de facilities e disponibilidade de ativos — permitindo que gestores tomem decisões baseadas em dados sobre paradas, custos e desempenho da equipe técnica.

### Problema que resolve

Dados de manutenção ficam fragmentados em sistemas operacionais sem visibilidade analítica. Gestores não sabem quais equipamentos param mais, qual o custo real por ativo, nem a performance dos técnicos.

### Público-alvo

| Perfil | Necessidade |
|--------|------------|
| Gestores de facilities | KPIs de custo e disponibilidade por setor |
| Coordenadores de manutenção | Performance de técnicos e recorrência de falhas |
| Engenheiros de dados | Pipeline confiável, testado e documentado |
| Analistas de BI | Camada Marts pronta para consumo em qualquer ferramenta |

### Fora de escopo

- Desenvolvimento de dashboards ou relatórios visuais
- Integração com sistemas CMMS externos
- Notificações ou alertas operacionais em tempo real

---

## 2. KPIs & Métricas de Negócio

### Facilities

| KPI | Descrição |
|-----|-----------|
| Custo total de manutenção por setor | Soma de `custo_pecas + custo_mao_obra` agrupado por setor, mensal e anual |
| Custo médio por OS por setor | Média de custo total por ordem de serviço por setor |
| Distribuição por tipo de manutenção | % de OS Preventiva / Corretiva / Preditiva |
| OS abertas vs. concluídas | Volume de ordens por status no período |

### Parada de Equipamentos

| KPI | Descrição |
|-----|-----------|
| MTTR (Mean Time to Repair) | Média de `horas_parada` por equipamento |
| Horas totais de parada | Soma de `horas_parada` por equipamento e setor |
| Taxa de recorrência de falhas | Número de OS corretivas por equipamento no período |
| Equipamentos críticos com maior parada | Equipamentos com criticidade A e maior MTTR |

### Performance de Técnicos

| KPI | Descrição |
|-----|-----------|
| OS concluídas por técnico | Contagem de OS com status `Finalizada` por técnico no período |
| Custo médio de mão de obra por especialidade | Média de `custo_mao_obra` por especialidade |
| Tempo médio de atendimento por nível | Média de `horas_parada` agrupado por `nivel_experiencia` |

---

## 3. Arquitetura de Dados

### Stack

- **Armazenamento de arquivos:** Google Cloud Storage (GCS)
- **Ingestão:** Cloud Run (Python / Flask)
- **Data Warehouse:** BigQuery
- **Transformações:** dbt
- **Orquestração:** Cloud Scheduler (Fase 3)

### Camadas

| Camada | Responsável | Dataset BQ | Responsabilidade |
|--------|------------|-----------|-----------------|
| **Staging** | Cloud Run | `staging` | Ingestão GCS → BQ; dados limpos e tipados na chegada |
| **Intermediate** | dbt | `intermediate` | Joins, enriquecimento e regras de negócio entre entidades |
| **Marts** | dbt | `marts` | Modelos analíticos agregados, prontos para consumo de BI |

### Fluxo de dados

```
GCS (raw/) → Cloud Run → Staging (BQ) → dbt Intermediate → dbt Marts → BI (externo)
```

### Tabelas fonte (Staging)

| Tabela | Descrição |
|--------|-----------|
| `equipamentos` | Cadastro de ativos industriais com criticidade e setor |
| `tecnicos` | Cadastro de técnicos com especialidade e nível |
| `ordens_servico` | Registro de OS com tipo, prioridade, custos e horas de parada |

### Modelos dbt planejados

**Intermediate:**

| Modelo | Descrição |
|--------|-----------|
| `int_ordens_servico_enriched` | OS com dados desnormalizados de equipamento e técnico |
| `int_equipamentos_parada` | Cálculo de MTTR e horas paradas consolidadas por ativo |

**Marts:**

| Modelo | Descrição |
|--------|-----------|
| `mart_facilities_custos` | Custos de manutenção por setor e período |
| `mart_equipamentos_parada` | KPIs de disponibilidade, MTTR e recorrência de falhas |
| `mart_tecnicos_performance` | Produtividade e custo por técnico e especialidade |

---

## 4. Roadmap por Fases

### Fase 1 — Fundação ✅ Concluída

- Pipeline de ingestão GCS → BQ (Cloud Run)
- Camada Staging com tabelas: `equipamentos`, `tecnicos`, `ordens_servico`
- Audit log de ingestão (`ingestion_logs`) no BQ

### Fase 2 — Transformações dbt 🔄 Em andamento

- Configuração do projeto dbt conectado ao BigQuery
- Modelos Intermediate: `int_ordens_servico_enriched`, `int_equipamentos_parada`
- Testes de qualidade: `not_null`, `unique`, `relationships` nas chaves primárias e estrangeiras

### Fase 3 — Marts & Entrega ao Negócio

- `mart_facilities_custos`
- `mart_equipamentos_parada` (MTTR, horas paradas, recorrência)
- `mart_tecnicos_performance`
- Documentação dbt (descriptions e lineage para todos os modelos)
- Agendamento da ingestão via Cloud Scheduler

---

## 5. Critérios de Sucesso

- Camada Marts disponível no BigQuery com dados atualizados diariamente
- Todos os KPIs definidos na Seção 2 calculáveis a partir dos marts
- Cobertura de testes dbt em todas as chaves primárias e estrangeiras
- Lineage documentado do raw ao mart para todos os modelos
