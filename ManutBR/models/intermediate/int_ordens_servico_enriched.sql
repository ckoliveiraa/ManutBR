with ordens_servico as (
    select * from {{ source('staging', 'ordens_servico') }}
),

equipamentos as (
    select * from {{ source('staging', 'equipamentos') }}
),

tecnicos as (
    select * from {{ source('staging', 'tecnicos') }}

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
