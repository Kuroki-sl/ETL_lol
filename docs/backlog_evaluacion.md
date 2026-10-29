# Backlog de la Evaluación 2 — ETL de League of Legends

**Revisado:** 28-10-2026. Basado en el repositorio y en la pauta E2-INF-522.

**Entrega:** informe y solución ETL el 01-11-2026; presentación el 05-11-2026.

## Forma de trabajo: integración vertical

Cada historia entrega una función completa que atraviesa el flujo **Riot API → `raw` → `staging` → `dw` → `mart` → consulta SQL → evidencia**. La persona responsable integra su indicador de punta a punta; las otras dos revisan el resultado. No se divide al equipo en responsables permanentes de API, base de datos o Airflow.

Las prioridades indican urgencia: **P0** bloquea la entrega o un requisito de pauta; **P1** mejora la demostración y la reproducibilidad.

## Estado actual

### Ya está implementado

- Docker Compose con Airflow y PostgreSQL; DDL con capas `raw`, `staging`, `dw` y `mart`.
- DAG de perfiles (Account-V1, Summoner-V4 y League-V4), DAG de partidas (Match-V5), DAG de KPI y DAG maestro.
- Cinco KPI, filtro Solo/Duo, conversión horaria a Chile, KDA con divisor mínimo 1, umbrales de muestra y tablas de auditoría.
- HU-01 implementada y validada en Docker: extracción paginada de hasta 50 partidas por jugador, consulta por Riot ID/rol y umbrales del KPI 1 acordados en 3 y 5 partidas.
- Scripts para respaldar/restaurar PostgreSQL y flujo de Drive web documentado.

### Pendientes confirmados al revisar el repo

- Falta ratificar con el equipo el límite operativo de hasta 50 jugadores y 50 IDs Solo/Duo por PUUID en cada ejecución; la retención en la base sigue siendo acumulativa.
- El DAG maestro es secuencial: si falla un DAG hijo, no continúa a la siguiente etapa. El DAG programado de partidas tampoco dispara automáticamente el DAG de KPI.
- El pre-chequeo de API puede aceptar errores 5xx; `porcentaje_nulos` no mide nulos de forma consistente.
- Aún faltan en el repo el informe PDF, la presentación y el ZIP final con evidencias.

## Historias de usuario

### HU-01 — Recomendar campeones para un jugador y rol

**Historia:** Como jugador, quiero buscar mi nombre y opcionalmente un rol para ver mis mejores campeones, con sus partidas, winrate, KDA y puntaje.

**Responsable vertical sugerido:** Joaquín (integrante A). Sergio y Juan revisan la integración completa.

- [ ] **P0** Ratificar con el equipo el tamaño configurado como máximo operativo: hasta 50 jugadores y 50 partidas Solo/Duo por PUUID en cada ejecución, sujeto a los límites de Riot y al tiempo disponible.
- [x] **P0** Completar la paginación `start`/`count`; consulta páginas de 20 hasta un máximo de 50 partidas por jugador en cada ejecución.
- [x] **P1** Seguir un PUUID de Riot desde la extracción hasta una fila del KPI 1 en `mart`; 20 partidas de trazabilidad confirmaron el mismo PUUID en el payload RAW.
- [x] **P1** Preparar la consulta SQL que recibe el nombre del jugador y un rol opcional, excluye muestras bajo el mínimo y ordena por `puntaje_compuesto`.
- [x] **P1** Acordar y documentar los umbrales del KPI 1: puntaje exploratorio desde 3 partidas, `MUESTRA CORTA` entre 3 y 4, y evaluación de `cumple_meta` desde 5.
- [x] **P1** Guardar evidencia del resultado: jugador, rol, partidas consideradas, campeón recomendado y fórmula aplicada.

#### Evidencia del avance

La consulta de HU-01 para `Frikz#xoro` devuelve, entre otros, estos resultados:

| Campeón | Rol | Partidas | Winrate | Estado de muestra | `cumple_meta` |
|---|---|---:|---:|---|---|
| Ekko | JUNGLE | 3 | 100,00% | `MUESTRA CORTA` | Sin evaluar |
| Syndra | MIDDLE | 4 | 75,00% | `MUESTRA CORTA` | Sin evaluar |
| Locke | MIDDLE | 5 | 60,00% | `MINIMO DE MUESTRA ALCANZADO` | Sí |

La consulta de trazabilidad listó 20 partidas y confirmó `puuid_presente_en_payload = true` para cada una. El recálculo produjo 13.167 filas en los cinco marts; Airflow no reportó errores de importación y los servicios de Docker Compose quedaron saludables. La fórmula del puntaje (winrate 60%, KDA 25% y volumen 15%) y los umbrales están en [la definición de indicadores](indicadores_etl_riot_games.md) y [la consulta HU-01](../sql/02_consulta_kpi_01_jugador.sql).

**Criterio de término:** una persona puede consultar el KPI 1 con nombre/rol y rastrear el resultado hasta las partidas guardadas, sin duplicar participaciones.

### HU-02 — Analizar horarios y actividad diaria

**Historia:** Como jugador, quiero comparar mis resultados por horario y revisar cuántas partidas juego al día para organizar mis sesiones.

**Responsable vertical sugerido:** Sergio (integrante B). Joaquín y Juan revisan la integración completa.

- [ ] **P0** Resolver la diferencia de definición del KPI 2: el código agrupa en bloques de cuatro horas y la propuesta conceptual habla de horas individuales. Alinear SQL, README e informe.
- [ ] **P1** Seguir `gameCreation` desde Match-V5 a hora/fecha de Chile en `dw.dim_tiempo` y comprobar la agrupación seleccionada.
- [ ] **P1** Verificar que el KPI 2 compare el winrate de la franja con el winrate global del mismo jugador y no recomiende muestras bajo el mínimo de 10 partidas.
- [ ] **P1** Verificar el KPI 4 de punta a punta: actividad diaria, alerta desde 7 partidas y winrate diario solo desde 10.
- [ ] **P1** Preparar consultas SQL y capturas de resultados para ambos KPI.

**Criterio de término:** horario y fecha usan la zona `America/Santiago`; las consultas muestran partidas y tamaño de muestra, y el informe explica la interpretación sin afirmar causalidad.

### HU-03 — Evaluar desempeño por rol y meta observado

**Historia:** Como analista, quiero comparar el desempeño por rol y los resultados de campeones en la muestra recolectada, separados por parche.

**Responsable vertical sugerido:** Juan (integrante C). Joaquín y Sergio revisan la integración completa.

- [ ] **P0** Acordar y documentar las referencias de KPI 3 por rol. Las actuales son parámetros del proyecto, no benchmarks oficiales de Riot.
- [ ] **P1** Seguir estadísticas de Match-V5 por participante desde `raw` hasta la calificación por rol y validar daño/oro/visión por minuto.
- [ ] **P1** Confirmar y documentar la aproximación de JG: `dragonKills + baronKills` del jugador por partida, no todos los objetivos del equipo.
- [ ] **P1** Verificar que KPI 5 agrupe por campeón, rol y parche, cuente cada participación una sola vez y no clasifique muestras menores de 10 como dominantes.
- [ ] **P1** Preparar consultas SQL y evidencia de una calificación por rol y de un resultado de meta observado.

**Criterio de término:** cada valor se puede seguir desde la participación del jugador hasta el resultado en `mart`; las limitaciones de muestra/parche quedan explicadas.

### HU-04 — Hacer confiable la ejecución completa

**Historia:** Como operador, quiero que los errores de una fuente queden registrados y no impidan procesar las fuentes independientes.

**Responsable de coordinación sugerido:** rotativo entre Joaquín, Sergio y Juan; los tres integran y revisan el cambio porque afecta las tres historias.

- [ ] **P0** Corregir el chequeo de API para que estados 5xx/inesperados fallen en vez de marcar la API como disponible.
- [ ] **P1** Completar reintentos y registro de errores HTTP; el código ya contempla red y 429, pero no reintenta todos los errores 5xx.
- [ ] **P0** Cambiar la orquestación: hoy `dag_00_pipeline_completo` espera éxito de cada hijo; definir cómo sigue la otra fuente y cuándo se permite calcular KPI con carga parcial.
- [ ] **P1** Disparar el cálculo de KPI después de una carga programada exitosa de partidas y aclarar los schedules/backfill.
- [ ] **P0** Calcular correctamente los nulos/errores por DAG; el KPI registra 0% fijo y el perfil cuenta `UNRANKED` como aproximación de nulos.
- [ ] **P0** Demostrar una falla controlada en Airflow: capturar retries, logs, auditoría y ejecución de la fuente independiente.

**Criterio de término:** una falla controlada queda visible en Airflow/auditoría, la fuente independiente continúa y los KPI indican qué datos fueron procesados.

### HU-05 — Entregar y reproducir el proyecto en equipo

**Historia:** Como equipo, queremos demostrar que otra persona puede reproducir el ETL y entender los cinco indicadores.

**Responsabilidad:** todos aportan evidencia de su historia vertical; una persona integra el informe y otra la presentación.

- [ ] **P0** Crear el informe PDF con fuentes y justificación, flujo ETL, modelo, DAGs, KPI, estrategia de datos y conclusiones.
- [ ] **P0** Escribir las 2–3 páginas de estrategia de datos: decisiones, calidad, origen/transformación, frecuencia, riesgos y escalabilidad.
- [ ] **P0** Adjuntar evidencia real: DAG exitoso y fallido, logs, consultas SQL, resultados y auditoría.
- [ ] **P0** Preparar la presentación de 8–12 láminas y organizar la exposición de 8 minutos.
- [ ] **P0** Crear el ZIP con DAGs, utilidades, DDL y README; excluir `.env`, claves y respaldos `.dump` salvo que la profesora los pida.
- [ ] **P1** Publicar el respaldo acordado en la carpeta Drive web; cada integrante lo descarga/restaura y comparan conteos para comprobar que trabajan con la misma captura.
- [ ] **P1** Ensayar preguntas: cada integrante explica su historia vertical y puede describir el flujo de punta a punta.

**Criterio de término:** el ZIP se reproduce siguiendo el README, el informe contiene evidencia de ejecuciones reales y los tres pueden explicar el proyecto completo.

## Reparto vertical sugerido

| Integrante | Historia principal | Resultado que entrega de punta a punta |
|---|---|---|
| Joaquín (A) | HU-01: campeón por jugador/rol | Consulta de jugador → KPI 1 en `mart` → recomendación con muestra y evidencia |
| Sergio (B) | HU-02: horario/actividad | Hora local → KPI 2 y KPI 4 → consultas y capturas |
| Juan (C) | HU-03: rol/meta | Estadísticas por participante/parche → KPI 3 y KPI 5 → consultas y capturas |
| Los tres | HU-04 y HU-05 | Orquestación confiable, informe, presentación, ZIP y revisión cruzada |

## Orden recomendado

1. Acordar el objetivo de muestra y la definición final del KPI 2.
2. Cada integrante cierra su historia desde la extracción existente hasta su consulta SQL y evidencia; en paralelo, el equipo integra HU-04.
3. Ejecutar una carga común y revisar los resultados de las tres historias sobre la misma base.
4. Cerrar informe, ZIP, presentación y ensayo.

> La pauta no exige un dashboard; no se incluye como tarea.
