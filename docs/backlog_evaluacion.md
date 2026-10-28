# Backlog de la Evaluación 2 — ETL de League of Legends

**Estado revisado:** 28-10-2026. Basado en el repositorio actual y en la pauta E2-INF-522.

**Entrega indicada en la pauta:** informe y solución ETL el 01-11-2026; presentación el 05-11-2026.

## Cómo leerlo

- **P0:** resolver antes de cerrar la entrega o puede afectar un requisito de la pauta.
- **P1:** importante para defender los resultados y demostrar que el sistema funciona.
- **P2:** orden y coordinación del equipo; útil, pero no bloquea por sí solo la entrega.
- Las asignaciones son roles provisionales porque aquí no están los nombres de los integrantes.

## Estado actual del proyecto

### Ya está implementado en el repositorio

- PostgreSQL y Airflow levantados con Docker Compose; DDL con capas `raw`, `staging`, `dw` y `mart`.
- DAG de perfiles (`Account-V1`, `Summoner-V4`, `League-V4`), DAG de partidas (`Match-V5`), DAG de KPI y DAG maestro.
- Validación previa de API, reintentos básicos, registro de auditoría, carga idempotente y cinco tablas KPI.
- Filtro Solo/Duo, conversión horaria a Chile, KDA con divisor mínimo 1, controles de muestra y respaldo/restauración de PostgreSQL.
- Flujo de respaldo por Drive web documentado en el README.

### Falta terminar, validar o entregar

- La extracción de partidas usa `count=20` y `start=0`; aún no recorre páginas para recuperar más historial.
- El DAG maestro encadena las etapas estrictamente: si un DAG hijo falla, las etapas siguientes no avanzan. Además, el DAG de KPI no se dispara desde el DAG de partidas programado.
- El pre-chequeo de API acepta como válido cualquier estado distinto de 401/403, incluidos errores de servidor; la métrica `porcentaje_nulos` tampoco cuenta nulos de manera consistente.
- No aparecen todavía en el repositorio el informe PDF, la presentación ni el ZIP final con evidencias.

## Backlog priorizado

### HU-01 — Recolectar una muestra suficiente y reproducible

**Historia:** Como analista, quiero contar con suficientes partidas clasificatorias para que los indicadores por jugador, campeón y rol no dependan de unos pocos casos.

**Responsables sugeridos:** Integrante A.

- [ ] **P0** Definir con el equipo el tamaño final de la muestra. Propuesta para discutir: alrededor de 50 jugadores y hasta 50 partidas Solo/Duo por jugador, según límites y tiempo.
- [ ] **P0** Implementar paginación con `start`/`count`; hoy se solicita una sola página de 20 IDs por jugador.
- [ ] **P0** Aplicar límites de consulta y reintentos sin repetir descargas de `match_id` ya guardados.
- [ ] **P1** Hacer una carga de muestra y registrar jugadores objetivo, fechas, partidas únicas y participaciones cargadas.
- [ ] **P1** Confirmar que una partida compartida por varios jugadores objetivo aparece una vez en RAW y cada participante una vez en DW.

**Criterio de término:** la cantidad recolectada coincide con el objetivo acordado, el rango de fechas queda documentado y no hay duplicados de partidas/participaciones.

### HU-02 — Aislar fallas y completar la orquestación

**Historia:** Como operador, quiero que la falla de una fuente no impida ejecutar las otras para que el pipeline tolere problemas temporales de Riot.

**Responsables sugeridos:** Integrante C.

- [ ] **P0** Rediseñar `dag_00_pipeline_completo`: actualmente espera éxito de cada hijo antes de iniciar el siguiente.
- [ ] **P0** Decidir y documentar cuándo calcular KPI si un ETL de fuente falla; no ocultar una carga parcial como si fuera completa.
- [ ] **P1** Disparar automáticamente `dag_03_calculo_kpis` después de una carga exitosa de partidas. Hoy el DAG 03 queda manual salvo que se use el maestro.
- [ ] **P1** Justificar los schedules actuales (perfil diario y partidas cada 6 horas) y definir cómo se ejecuta un backfill por rango.
- [ ] **P0** Preparar una falla controlada para la presentación y capturar reintentos, logs, auditoría y resultado de las demás etapas.

**Criterio de término:** una falla simulada queda registrada y no bloquea la ejecución de la fuente independiente; los KPI solo reflejan los datos que sí se cargaron.

### HU-03 — Hacer confiables el chequeo y las métricas de calidad

**Historia:** Como responsable de datos, quiero que los controles y la auditoría reflejen errores reales para poder explicar la calidad de la carga.

**Responsables sugeridos:** Integrante B.

- [ ] **P0** Corregir `validar_estado_api` para que errores 5xx y estados inesperados fallen el chequeo, en vez de aceptarse como API disponible.
- [ ] **P1** Completar el manejo de errores HTTP y registrar el tipo de fallo; el helper actual ya maneja red y 429, pero no reintenta todos los errores 5xx.
- [ ] **P0** Definir qué significa `porcentaje_nulos` por DAG y calcularlo sobre los campos esperados. El DAG de KPI hoy registra 0% fijo y el DAG de perfil usa un contador de `UNRANKED` como aproximación de nulos.
- [ ] **P1** Completar una tabla/resumen de auditoría con filas leídas y cargadas, inválidos/nulos, duración y estado por ejecución.
- [ ] **P1** Preparar consultas SQL para mostrar filas por tabla, partidas únicas, participaciones, distribución de colas y resultados KPI.

**Criterio de término:** cada porcentaje tiene una fórmula definida y los datos de `etl_audit` se pueden defender con consultas a las tablas fuente.

### HU-04 — Cerrar y mostrar los cinco indicadores

**Historia:** Como integrante del equipo, quiero explicar qué mide cada KPI y consultar resultados por jugador para responder preguntas de gestión.

**Responsables sugeridos:** Integrante B + equipo.

- [ ] **P0** Acordar que el KPI 2 se presentará por bloques de cuatro horas (como está codificado) o cambiarlo a hora individual (como dice la especificación conceptual); dejar una sola definición en código, README e informe.
- [ ] **P0** Aprobar los pesos del puntaje compuesto de KPI 1 y las referencias del KPI 3; actualmente son parámetros del proyecto, no referencias oficiales de Riot.
- [ ] **P1** Añadir al README consultas SQL para buscar un jugador por `nombre_jugador`, filtrar un rol opcional y ordenar sus campeones por `puntaje_compuesto`, mostrando también partidas y estado de muestra.
- [ ] **P1** Revisar manualmente resultados conocidos y verificar que `cumple_meta`, mínimos de muestra, KDA sin muertes y parche se interpreten como está documentado.
- [ ] **P1** Escribir para cada KPI: nombre, objetivo, fórmula, fuente, periodicidad, umbral y limitación de interpretación.

**Criterio de término:** se puede responder una consulta de jugador/campeón/rol con su tamaño de muestra y explicar la fórmula sin contradicciones entre código y documentos.

### HU-05 — Preparar informe, evidencia y presentación

**Historia:** Como equipo, queremos entregar un paquete reproducible y una exposición clara que demuestren el trabajo realizado.

**Responsables sugeridos:** Integrante C coordina; A redacta fuentes/extracción; B modelo/calidad/KPI; todos revisan.

- [ ] **P0** Crear el informe PDF con portada, fuentes y justificación, pasos ETL, modelo, diseño de DAGs, indicadores, estrategia de datos y conclusiones.
- [ ] **P0** Incluir las 2–3 páginas de estrategia de datos requeridas: decisiones, calidad, origen/transformaciones, frecuencia, riesgos y escalabilidad.
- [ ] **P0** Adjuntar evidencia real: capturas de ejecuciones exitosas y fallidas en Airflow, logs, consultas SQL y resultados de auditoría.
- [ ] **P0** Crear la presentación de 8–12 láminas y planificar la exposición de 8 minutos.
- [ ] **P0** Preparar el ZIP final con DAGs, utilidades, DDL y README. Excluir `.env`, claves Riot y respaldos `.dump` salvo que la profesora los pida expresamente.
- [ ] **P1** Repartir preguntas de dominio entre los tres y hacer un ensayo cronometrado.

**Criterio de término:** un integrante que no preparó una sección puede reproducir el proyecto siguiendo el README y cada integrante puede explicar el flujo y sus límites.

### HU-06 — Compartir una captura común con Drive web

**Historia:** Como equipo de tres, queremos partir desde la misma captura de PostgreSQL sin confundirla con una base sincronizada en vivo.

**Responsables sugeridos:** Integrante A publica el respaldo; B y C restauran; todos verifican.

- [ ] **P1** Elegir quién publica el respaldo vigente y acordar cuándo se actualiza.
- [ ] **P1** Subir el primer `gestion_lol_*.dump` a la carpeta compartida de Drive web después de la carga acordada.
- [ ] **P1** Cada integrante descarga y restaura esa captura con `Restore-GestionLol.ps1` en su PostgreSQL local.
- [ ] **P1** Comparar conteos de filas en cada computador para confirmar que restauraron el mismo respaldo.

**Criterio de término:** los tres tienen la misma captura local; todo respaldo posterior sustituye la captura anterior y no se intenta fusionar dumps.

## Reparto sugerido entre tres

| Integrante | Foco principal | Entregables que lidera |
|---|---|---|
| A | Recolección de datos | HU-01 y publicación de respaldo de HU-06 |
| B | Calidad, base y KPI | HU-03, HU-04 y sección técnica del informe |
| C | Airflow y entregables | HU-02, coordinación de HU-05 y presentación |
| Todos | Decisiones y evaluación | Revisar resultados, restaurar respaldo, ensayo y preguntas |

## Orden recomendado para avanzar

1. **Primero:** acordar el tamaño de muestra y arrancar la recolección paginada de HU-01.
2. **En paralelo:** A implementa la paginación; B corrige métricas de calidad y valida KPI; C arregla la tolerancia a fallas y el disparo de KPI.
3. **Después de una carga válida:** generar datos de evidencia, consultas y respaldo compartido.
4. **Cierre:** informe, presentación, ZIP, revisión de secretos y ensayo grupal.

> No se propone construir un dashboard: la pauta dice que no es requisito.
