with enriched as (
    select * from {{ ref('int_ordens_servico_enriched') }}
)

select
    setor,
    date_trunc(data_abertura, month) as ano_mes,
    tipo_manutencao,
    count(*) as total_os,
    sum(custo_pecas) as custo_pecas_total,
    sum(custo_mao_obra) as custo_mao_obra_total,
    sum(custo_pecas + custo_mao_obra) as custo_total,
    avg(custo_pecas + custo_mao_obra) as custo_medio_por_os

from enriched
group by setor, ano_mes, tipo_manutencao
