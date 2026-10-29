# Avance HU-01: recomendación de campeones

## Regla acordada

- Match-V5 consulta hasta 50 partidas Solo/Duo por jugador en páginas de 20.
- Desde 3 partidas se calcula un puntaje exploratorio. Con 3–4 partidas, el estado es `MUESTRA CORTA` y `cumple_meta` queda sin evaluar.
- Desde 5 partidas se evalúa `cumple_meta`: el winrate debe superar 55%. El umbral es una regla operativa del proyecto, no una garantía de significancia estadística.
- El puntaje compuesto pondera winrate (60%), KDA normalizado (25%) y volumen hasta 50 partidas (15%).

## Evidencia de Frikz#xoro

| Campeón | Rol | Partidas | Victorias | Winrate | Puntaje | Estado | `cumple_meta` |
|---|---|---:|---:|---:|---:|---|---|
| Ekko | JUNGLE | 3 | 3 | 100,00% | 81,30 | `MUESTRA CORTA` | Sin evaluar |
| Syndra | MIDDLE | 4 | 3 | 75,00% | 60,90 | `MUESTRA CORTA` | Sin evaluar |
| Locke | MIDDLE | 5 | 3 | 60,00% | 50,35 | `MINIMO DE MUESTRA ALCANZADO` | Sí |

Ekko ilustra por qué una tasa de 100% con tres partidas aparece como candidato, pero no se declara que cumple la meta. La consulta de trazabilidad listó 20 partidas y confirmó que el PUUID del jugador estaba presente en cada payload Match-V5.

## Validación en Docker

- `calcular_kpis_mart` recalculó 13.167 filas entre los cinco marts con los umbrales 3/5.
- `airflow dags list-import-errors` devolvió `No data found`.
- `docker compose ps` mostró los servicios saludables.
- `python -m py_compile` para `etl_lol_utils.py` y `dag_03_calculo_kpis.py`, y `git diff --check`, terminaron sin errores.

La consulta ejecutable está en [`02_consulta_kpi_01_jugador.sql`](../sql/02_consulta_kpi_01_jugador.sql).
