with enriched as (
    select * from {{ ref('int_ordens_servico_enriched') }}
)

select
    tecnico_id,
    nome_completo,
    especialidade,
    nivel_experiencia,
    countif(status = 'Finalizada') as total_os_concluidas,
    sum(custo_mao_obra) as custo_mao_obra_total,
    avg(custo_mao_obra) as custo_mao_obra_medio,
    avg(horas_parada) as tempo_medio_atendimento

from enriched
group by tecnico_id, nome_completo, especialidade, nivel_experiencia
