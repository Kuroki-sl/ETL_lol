# Avance HU-01: recomendación de campeones

## Regla acordada

- La configuración actual de Match-V5 consulta hasta 100 partidas Solo/Duo por Riot ID, en páginas de 20. La evidencia histórica de esta sección se generó con el límite anterior de 50.
- Desde 3 partidas se calcula un puntaje exploratorio. Con 3–4 partidas, el estado es `MUESTRA CORTA` y `cumple_meta` queda sin evaluar.
- Desde 5 partidas se evalúa `cumple_meta`: el winrate debe superar 55%. El umbral es una regla operativa del proyecto, no una garantía de significancia estadística.
- El puntaje compuesto pondera winrate (60%), KDA normalizado (25%) y volumen hasta 50 partidas (15%), aunque la extracción ahora admite hasta 100.

## Ampliación de la muestra

- Se conservó la cohorte existente de cinco jugadores en `riot_target_players` y se agregaron `Sajor#FGC`, `Michael Kaiser#10皇帝`, `Janemba#0001`, `Gordo Y Cabezon#Tomm` y `Clarissaa#LAS1`.
- La variable activa de Airflow contiene diez Riot ID. El DAG de partidas resuelve sus PUUID desde `raw.raw_perfil_jugador` y deja fuera perfiles antiguos que no estén en la cohorte.
- Cada partida nueva sigue incorporando a sus participantes a los KPI agregados; el historial se consulta únicamente para los Riot ID de la variable.
- Se amplió el tiempo máximo de extracción y del DAG maestro para permitir la muestra de 100 partidas.
- La ejecución manual del DAG maestro del 28-10-2026 (hora de Chile) terminó correctamente. Match-V5 guardó 588 partidas nuevas; `raw.raw_partidas` quedó en 970 y `dw.fact_partidas` en 9.070 filas. Los cinco marts se recalcularon: KPI 1: 7.910 filas; KPI 2: 7.256; KPI 3: 6.979; KPI 4: 8.029; KPI 5: 3.994.
- League-V4 confirmó que los cinco Riot ID agregados están en Diamante I o II de LAS. El número de partidas Solo/Duo disponibles en el DW fue:

| Riot ID | Liga | Partidas Solo/Duo |
|---|---|---:|
| Sajor#FGC | Diamante I | 98 |
| Michael Kaiser#10皇帝 | Diamante I | 97 |
| Janemba#0001 | Diamante II | 2 |
| Gordo Y Cabezon#Tomm | Diamante I | 99 |
| Clarissaa#LAS1 | Diamante II | 98 |

Janemba#0001 solo tenía dos partidas Solo/Duo disponibles en Match-V5, por lo que la configuración de 100 representa un máximo y no una cantidad garantizada. Riot aplicó límites `429` durante la extracción; el DAG respetó `Retry-After` y terminó sin fallas.

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
