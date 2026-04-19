with ordens_servico as (
    select *
    from {{ source('staging', 'ordens_servico') }}
    qualify row_number() over (
        partition by id
        order by data_abertura desc, data_conclusao desc nulls last
    ) = 1
),

equipamentos as (
    select *
    from {{ source('staging', 'equipamentos') }}
    qualify row_number() over (
        partition by id
        order by data_instalacao desc nulls last
    ) = 1
),

tecnicos as (
    select *
    from {{ source('staging', 'tecnicos') }}
    qualify row_number() over (
        partition by id
        order by id
    ) = 1
)

select
    os.id,
    os.equipamento_id,
    os.tecnico_id,
    os.tipo_manutencao,
    os.prioridade,
    os.data_abertura,
    os.data_conclusao,
    os.horas_parada,
    os.custo_pecas,
    os.custo_mao_obra,
    os.descricao_servico,
    os.status,

    eq.nome_equipamento,
    eq.setor,
    eq.criticidade,
    eq.tag_ativo,

    tc.nome_completo,
    tc.especialidade,
    tc.nivel_experiencia

from ordens_servico as os
left join equipamentos as eq on os.equipamento_id = eq.id
left join tecnicos as tc on os.tecnico_id = tc.id
