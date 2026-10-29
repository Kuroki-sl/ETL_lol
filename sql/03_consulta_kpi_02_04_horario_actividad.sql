-- HU-02 / Sergio: Analizar horarios y actividad diaria
-- Indicadores: KPI 2 (Winrate por Bloque Horario) y KPI 4 (Control de Actividad)

-- Cambia 'Frikz#xoro' por el Riot ID del jugador que deseas consultar.

-- 1. CONSULTA KPI 2: Tasa de victorias por bloque horario y recomendación
WITH parametros AS (
    SELECT 'Frikz#xoro'::TEXT AS riot_id
),
winrate_global_jugador AS (
    SELECT
        f.puuid,
        j.nombre_completo,
        COUNT(*)::INT AS total_partidas_periodo,
        SUM(CASE WHEN f.victoria THEN 1 ELSE 0 END)::INT AS total_victorias_periodo,
        ROUND((SUM(CASE WHEN f.victoria THEN 1 ELSE 0 END)::NUMERIC / COUNT(*)) * 100, 2) AS winrate_global_pct
    FROM dw.fact_partidas f
    JOIN dw.dim_jugador j ON f.puuid = j.puuid
    CROSS JOIN parametros p
    WHERE LOWER(j.nombre_completo) = LOWER(p.riot_id)
      AND f.queue_id = 420
    GROUP BY f.puuid, j.nombre_completo
)
SELECT
    k.puuid,
    k.nombre_jugador,
    k.bloque_horario,
    CASE k.bloque_horario
        WHEN '00-03' THEN 'Madrugada (00:00 a 03:59)'
        WHEN '04-07' THEN 'Temprano (04:00 a 07:59)'
        WHEN '08-11' THEN 'Mañana (08:00 a 11:59)'
        WHEN '12-15' THEN 'Mediodía / Tarde temprana (12:00 a 15:59)'
        WHEN '16-19' THEN 'Tarde / Noche temprana (16:00 a 19:59)'
        WHEN '20-23' THEN 'Noche (20:00 a 23:59)'
        ELSE 'Otro'
    END AS descripcion_bloque,
    k.partidas_jugadas,
    k.victorias,
    (k.partidas_jugadas - k.victorias) AS derrotas,
    k.winrate_pct AS winrate_bloque_pct,
    g.winrate_global_pct,
    ROUND(k.winrate_pct - g.winrate_global_pct, 2) AS diferencia_vs_global_pct,
    k.recomendacion_gestion
FROM mart.kpi_02_winrate_horario k
JOIN winrate_global_jugador g ON k.puuid = g.puuid
CROSS JOIN parametros p
WHERE LOWER(k.nombre_jugador) = LOWER(p.riot_id)
ORDER BY
    -- Prioriza franjas favorables y con mayor volumen analítico
    CASE k.recomendacion_gestion
        WHEN 'FRANJA FAVORABLE EN MUESTRA' THEN 1
        WHEN 'SOBRE PROMEDIO PERSONAL' THEN 2
        WHEN 'SOBRE 50%, SIMILAR AL GLOBAL' THEN 3
        WHEN 'SIMILAR AL PROMEDIO GLOBAL' THEN 4
        WHEN 'BAJO PROMEDIO PERSONAL' THEN 5
        WHEN 'MUESTRA INSUFICIENTE' THEN 6
        ELSE 7
    END,
    k.partidas_jugadas DESC,
    k.winrate_pct DESC;


-- 2. CONSULTA KPI 4: Control de actividad diaria y detección de sobrecarga

-- Monitorea el volumen de partidas diarias y las horas estimadas de juego.

WITH parametros AS (
    SELECT 'Frikz#xoro'::TEXT AS riot_id
)
SELECT
    k.puuid,
    k.nombre_jugador,
    k.fecha,
    TO_CHAR(k.fecha, 'TMDay, DD "de" TMMonth "de" YYYY') AS fecha_formateada,
    k.partidas_en_el_dia,
    k.horas_jugadas_dia,
    COALESCE(TO_CHAR(k.winrate_del_dia, 'FM990.00') || '%', 'Muestra insuficiente (<5 part.)') AS winrate_del_dia,
    k.alerta_sobrecarga,
    CASE
        WHEN k.alerta_sobrecarga THEN 'ALERTA ACTIVIDAD ELEVADA (>= 7 partidas)'
        ELSE 'Actividad moderada (< 7 partidas)'
    END AS estado_actividad
FROM mart.kpi_04_control_actividad_diaria k
CROSS JOIN parametros p
WHERE LOWER(k.nombre_jugador) = LOWER(p.riot_id)
ORDER BY
    k.fecha DESC;


-- 3. TRAZABILIDAD: Verificación de zona horaria Chile y linaje RAW -> DW -> MART
-- Comprueba que:
-- 1. 'gameCreation' (epoch ms UTC en Match-V5) se transformó a 'America/Santiago'.
-- 2. La fecha y hora asignadas en 'dw.dim_tiempo' coinciden con el bloque horario.
-- 3. No se incluyen remakes (< 5 minutos) y solo se procesan clasificatorias (queue = 420).

WITH parametros AS (
    SELECT 'Frikz#xoro'::TEXT AS riot_id
),
jugador AS (
    SELECT puuid, nombre_completo
    FROM dw.dim_jugador
    CROSS JOIN parametros p
    WHERE LOWER(nombre_completo) = LOWER(p.riot_id)
)
SELECT
    f.match_id,
    j.nombre_completo AS riot_id,
    -- Timestamp bruto guardado en el JSON de RAW (milisegundos UTC)
    (r.payload_match #>> '{info,gameCreation}')::BIGINT AS game_creation_epoch_ms,
    -- Conversión esperada a UTC
    TO_TIMESTAMP((r.payload_match #>> '{info,gameCreation}')::DOUBLE PRECISION / 1000.0) AT TIME ZONE 'UTC' AS fecha_utc,
    -- Conversión local de Chile almacenada en Data Warehouse
    t.fecha AS fecha_chile,
    t.hora AS hora_inicio_chile,
    t.bloque_horario AS bloque_asignado,
    t.dia_semana,
    f.duracion_min,
    f.victoria,
    f.campeon,
    f.rol
FROM dw.fact_partidas f
JOIN jugador j ON f.puuid = j.puuid
JOIN dw.dim_tiempo t ON f.id_tiempo = t.id_tiempo
JOIN raw.raw_partidas r ON f.match_id = r.match_id
WHERE f.queue_id = 420
ORDER BY t.id_tiempo DESC
LIMIT 15;
