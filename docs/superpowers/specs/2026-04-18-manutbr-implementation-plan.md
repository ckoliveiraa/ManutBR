# Plano de Implementação — ManutBR dbt Transformations

**Referência:** [PRD ManutBR](./2026-04-18-manutbr-prd.md)  
**Data:** 2026-04-18  
**Stack:** dbt + BigQuery

---

## Contexto

O projeto dbt existe em `ManutBR/` com estrutura padrão, mas apenas modelos de exemplo. A camada Staging já está disponível no BigQuery (gerada pelo Cloud Run). O trabalho aqui é construir as camadas Intermediate e Marts.

---

## Fase 1 — Configurar o projeto dbt

### Tarefa 1.1 — Atualizar `dbt_project.yml`

Substituir a configuração de exemplo pelas camadas reais com materialização e schemas corretos:

```yaml
models:
  ManutBR:
    intermediate:
      +materialized: ephemeral
      +schema: intermediate
    marts:
      +materialized: table
      +schema: marts
```

> Staging não é gerenciada pelo dbt — é produzida pelo Cloud Run diretamente no dataset `staging`.

### Tarefa 1.2 — Remover modelos de exemplo

Deletar `models/example/` inteiramente.

### Tarefa 1.3 — Criar definição de sources

Criar `models/intermediate/_gestao_manutencao__sources.yml` apontando para o dataset `staging`:

```yaml
version: 2

sources:
  - name: gestao_manutencao_industrial
    schema: staging
    tables:
      - name: equipamentos
        columns:
          - name: id
            tests: [unique, not_null]
      - name: tecnicos
        columns:
          - name: id
            tests: [unique, not_null]
      - name: ordens_servico
        columns:
          - name: id
            tests: [unique, not_null]
          - name: equipamento_id
            tests:
              - not_null
              - relationships:
                  to: source('gestao_manutencao_industrial', 'equipamentos')
                  field: id
          - name: tecnico_id
            tests:
              - not_null
              - relationships:
                  to: source('gestao_manutencao_industrial', 'tecnicos')
                  field: id
```

---

## Fase 2 — Modelos Intermediate

### Tarefa 2.1 — `int_ordens_servico_enriched`

**Arquivo:** `models/intermediate/int_ordens_servico_enriched.sql`

Join entre `ordens_servico`, `equipamentos` e `tecnicos`. Resultado: uma linha por OS com todos os atributos desnormalizados necessários para os marts.

Colunas relevantes a trazer:
- Da OS: todas as colunas originais
- Do equipamento: `nome_equipamento`, `setor`, `criticidade`, `tag_ativo`
- Do técnico: `nome_completo`, `especialidade`, `nivel_experiencia`

Materialização: `ephemeral` (sem tabela física — compilado inline nos marts).

### Tarefa 2.2 — `int_equipamentos_parada`

**Arquivo:** `models/intermediate/int_equipamentos_parada.sql`

Agrega por `equipamento_id` a partir de `int_ordens_servico_enriched`:
- `total_os` — total de OS por equipamento
- `total_os_corretivas` — OS com `tipo_manutencao = 'Corretiva'`
- `horas_parada_total` — soma de `horas_parada`
- `mttr` — média de `horas_parada` (apenas OS Finalizadas)
- `taxa_recorrencia` — `total_os_corretivas / total_os`

Filtrar apenas OS com `status = 'Finalizada'` para métricas de MTTR.

Materialização: `ephemeral`.

### Tarefa 2.3 — Documentação dos modelos Intermediate

Criar `models/intermediate/_intermediate__models.yml` com `description` para cada modelo e coluna calculada.

---

## Fase 3 — Modelos Marts

### Tarefa 3.1 — `fct_facilities_custos`

**Arquivo:** `models/marts/fct_facilities_custos.sql`

Agrega custos por `setor` e `data_abertura` (truncado por mês) a partir de `int_ordens_servico_enriched`:
- `setor`
- `ano_mes` — `date_trunc(data_abertura, month)`
- `tipo_manutencao`
- `total_os`
- `custo_pecas_total`
- `custo_mao_obra_total`
- `custo_total` — soma dos dois
- `custo_medio_por_os`

Materialização: `table`.

### Tarefa 3.2 — `fct_equipamentos_parada`

**Arquivo:** `models/marts/fct_equipamentos_parada.sql`

Consome `int_equipamentos_parada` + atributos do equipamento de `int_ordens_servico_enriched`:
- `equipamento_id`, `tag_ativo`, `nome_equipamento`, `setor`, `criticidade`
- `total_os`, `total_os_corretivas`
- `horas_parada_total`, `mttr`
- `taxa_recorrencia`

Ordenar por `horas_parada_total desc` para facilitar consumo analítico.

Materialização: `table`.

### Tarefa 3.3 — `fct_tecnicos_performance`

**Arquivo:** `models/marts/fct_tecnicos_performance.sql`

Agrega por `tecnico_id` a partir de `int_ordens_servico_enriched`:
- `tecnico_id`, `nome_completo`, `especialidade`, `nivel_experiencia`
- `total_os_concluidas` — OS com `status = 'Finalizada'`
- `custo_mao_obra_total`
- `custo_mao_obra_medio`
- `tempo_medio_atendimento` — média de `horas_parada`

Materialização: `table`.

### Tarefa 3.4 — Documentação e testes dos Marts

Criar `models/marts/_marts__models.yml` com:
- `description` para cada modelo e coluna
- Testes `unique` + `not_null` nas PKs
- Teste `accepted_values` em `criticidade` (`A`, `B`, `C`)
- Teste `accepted_values` em `tipo_manutencao` (`Preventiva`, `Corretiva`, `Preditiva`)

---

## Fase 4 — Validação final

### Tarefa 4.1 — Executar `dbt build`

```bash
dbt build
```

Valida todos os modelos + testes em sequência. Corrigir qualquer falha antes de seguir.

### Tarefa 4.2 — Gerar e verificar lineage

```bash
dbt docs generate && dbt docs serve
```

Confirmar que o DAG mostra: `source → int → fct` sem dependências quebradas.

### Tarefa 4.3 — Validar KPIs no BigQuery

Executar queries diretas nos marts para confirmar que os KPIs definidos no PRD são calculáveis:
- MTTR por equipamento
- Custo total por setor/mês
- OS concluídas por técnico

---

## Ordem de execução

```
1.1 → 1.2 → 1.3
       ↓
2.1 → 2.2 → 2.3
       ↓
3.1 → 3.2 → 3.3 → 3.4
       ↓
4.1 → 4.2 → 4.3
```

---

## Referências

- [dbt-transformation-patterns SKILL](.claude/skill/dbt-transformation-patterns/)
- [PRD ManutBR](./2026-04-18-manutbr-prd.md)
- [Schema das fontes](../../files/gestao_manutencao_industrial_schema.yaml)
