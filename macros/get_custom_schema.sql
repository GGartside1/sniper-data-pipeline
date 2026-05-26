{% macro generate_schema_name(custom_schema_name, node) -%}
    {# Force everything to the target schema (RAW) regardless of environment configuration #}
    {{ target.schema | trim }}
{%- endmacro %}