with enriched as (
    select * from {{ ref('int_ordens_servico_enriched') }}
)

select
    equipamento_id,
    count(*) as total_os,
    countif(tipo_manutencao = 'Corretiva') as total_os_corretivas,
    sum(horas_parada) as horas_parada_total,
    avg(case when status = 'Finalizada' then horas_parada end) as mttr,
    safe_divide(
        countif(tipo_manutencao = 'Corretiva'),
        count(*)
    ) as taxa_recorrencia

from enriched
group by equipamento_id
