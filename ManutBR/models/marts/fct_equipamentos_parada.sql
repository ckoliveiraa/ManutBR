with parada as (
    select * from {{ ref('int_equipamentos_parada') }}
),

attrs as (
    select distinct
        equipamento_id,
        tag_ativo,
        nome_equipamento,
        setor,
        criticidade
    from {{ ref('int_ordens_servico_enriched') }}
)

select
    p.equipamento_id,
    a.tag_ativo,
    a.nome_equipamento,
    a.setor,
    a.criticidade,
    p.total_os,
    p.total_os_corretivas,
    p.horas_parada_total,
    p.mttr,
    p.taxa_recorrencia

from parada as p
left join attrs as a on p.equipamento_id = a.equipamento_id
order by p.horas_parada_total desc
