select *
from {{ source('staging', 'tipo_manutencao') }}
