-- HU-03 / Juan: Evaluar desempeño por rol y meta observado
-- Indicadores: KPI 3 (Calificación por Rol en Escala 1 a 7) y KPI 5 (Tierlist Meta Observado vs Especialización)

-- ============================================================================
-- 1. CONSULTA KPI 3: Calificación de desempeño por rol (Escala 1,0 a 7,0)
-- ============================================================================
-- Evalúa las métricas clave de cada rol normalizadas frente a los umbrales
-- definitivos de ALTA EXIGENCIA acordados por el equipo para el proyecto:
--   * TOP:     Daño/min (650) y Daño a torres/min (200)
--   * JUNGLE:  KDA agregado (4.5) y Dragones+Barones por partida (3.0)
--   * MIDDLE:  KDA agregado (4.5) y Daño/min (700)
--   * BOTTOM:  Daño/min (750) y Oro/min (500)
--   * UTILITY: KDA agregado (4.0) y Visión/min (2.0)
-- Fórmula: Nota = 1.0 + 6.0 * ((Factor_1 + Factor_2) / 2.0), acotados en [0, 1].
-- Meta: Nota >= 5.5 clasifica como 'Logra la meta'.

WITH parametros AS (
    SELECT 
        'Frikz#xoro'::TEXT AS riot_id,
        NULLIF(UPPER(BTRIM(''::TEXT)), '') AS rol_opcional  -- Ej: 'MIDDLE', 'JUNGLE', o vacío para todos
)
SELECT
    k.puuid,
    k.nombre_jugador,
    k.rol,
    k.partidas_jugadas,
    k.kda_promedio,
    k.dpm_promedio,
    k.gpm_promedio,
    k.vision_min_promedio,
    k.torres_min_promedio,
    k.objetivos_jg_promedio,
    k.nota_escala_1_a_7,
    k.estado_rendimiento,
    CASE k.rol
        WHEN 'TOP' THEN 'Factores definitivos: DPM (' || COALESCE(k.dpm_promedio::TEXT, '0') || '/650) y Torres/min (' || COALESCE(k.torres_min_promedio::TEXT, '0') || '/200)'
        WHEN 'JUNGLE' THEN 'Factores definitivos: KDA (' || COALESCE(k.kda_promedio::TEXT, '0') || '/4.5) y Obj JG/partida (' || COALESCE(k.objetivos_jg_promedio::TEXT, '0') || '/3.0)'
        WHEN 'MIDDLE' THEN 'Factores definitivos: KDA (' || COALESCE(k.kda_promedio::TEXT, '0') || '/4.5) y DPM (' || COALESCE(k.dpm_promedio::TEXT, '0') || '/700)'
        WHEN 'BOTTOM' THEN 'Factores definitivos: DPM (' || COALESCE(k.dpm_promedio::TEXT, '0') || '/750) y GPM (' || COALESCE(k.gpm_promedio::TEXT, '0') || '/500)'
        WHEN 'UTILITY' THEN 'Factores definitivos: KDA (' || COALESCE(k.kda_promedio::TEXT, '0') || '/4.0) y Visión/min (' || COALESCE(k.vision_min_promedio::TEXT, '0') || '/2.0)'
        ELSE 'Rol genérico'
    END AS detalle_evaluacion
FROM mart.kpi_03_calificacion_rol k
CROSS JOIN parametros p
WHERE (
    LOWER(k.nombre_jugador) = LOWER(p.riot_id)
    OR LOWER(k.nombre_jugador) = LOWER(SPLIT_PART(p.riot_id, '#', 1))
)
  AND (p.rol_opcional IS NULL OR UPPER(k.rol) = p.rol_opcional)
ORDER BY
    k.nota_escala_1_a_7 DESC,
    k.partidas_jugadas DESC;


-- ============================================================================
-- 2. CONSULTA KPI 5: Meta observado de campeones por rol y parche
-- ============================================================================
-- Agrupa a los diez participantes de cada partida recolectada.
-- Mínimo de muestra: 10 partidas para clasificar.
--   * Winrate > 52%: 'Destacado en la muestra'
--   * Winrate <= 52%: 'No supera el umbral'
--   * Menos de 10 partidas: 'Muestra insuficiente' (evita sesgo por casos atípicos)

WITH parametros AS (
    SELECT 
        NULLIF(BTRIM(''::TEXT), '') AS parche_opcional,       -- Ej: '16.18' o dejar vacío
        NULLIF(UPPER(BTRIM(''::TEXT)), '') AS rol_opcional   -- Ej: 'BOTTOM', 'UTILITY', o vacío
)
SELECT
    k.campeon,
    k.rol,
    k.parche,
    k.partidas_totales,
    k.winrate_global_pct,
    k.kda_global,
    k.clasificacion_tier
FROM mart.kpi_05_tierlist_meta_vs_otp k
CROSS JOIN parametros p
WHERE (p.parche_opcional IS NULL OR k.parche LIKE p.parche_opcional || '%')
  AND (p.rol_opcional IS NULL OR UPPER(k.rol) = p.rol_opcional)
ORDER BY
    CASE k.clasificacion_tier
        WHEN 'Destacado en la muestra' THEN 1
        WHEN 'No supera el umbral' THEN 2
        ELSE 3
    END,
    k.partidas_totales DESC,
    k.winrate_global_pct DESC,
    k.campeon
LIMIT 30;


-- ============================================================================
-- 3. TRAZABILIDAD: Verificación de punta a punta (RAW -> DW -> MART)
-- ============================================================================

-- A. Trazabilidad de KPI 3: Métricas individuales y de partida para un jugador
-- Verifica el cálculo de DPM, GPM, Visión/min, Torres/min y Objetivos JG
-- directamente desde los hechos registrados en el Data Warehouse.
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
    f.rol,
    f.campeon,
    f.duracion_min,
    f.asesinatos,
    f.muertes,
    f.asistencias,
    ROUND(((f.asesinatos + f.asistencias)::NUMERIC / GREATEST(f.muertes, 1)), 2) AS kda_partida,
    ROUND((f.dano_campeones::NUMERIC / NULLIF(f.duracion_min, 0)), 2) AS dpm_calculado,
    ROUND((f.oro::NUMERIC / NULLIF(f.duracion_min, 0)), 2) AS gpm_calculado,
    ROUND((f.vision::NUMERIC / NULLIF(f.duracion_min, 0)), 2) AS vision_min_calculada,
    ROUND((f.dano_torres::NUMERIC / NULLIF(f.duracion_min, 0)), 2) AS torres_min_calculado,
    f.objetivos_neutrales AS objetivos_jg_asegurados
FROM dw.fact_partidas f
JOIN jugador j ON f.puuid = j.puuid
WHERE f.queue_id = 420
ORDER BY f.id_tiempo DESC
LIMIT 10;


-- B. Trazabilidad de KPI 5: Confirmación de recuento único por partida y parche
-- Comprueba que cada fila de fact_partidas corresponde a una participación
-- individual y no genera duplicados en la suma de partidas_totales del meta.
SELECT 
    SPLIT_PART(f.parche, '.', 1) || '.' || SPLIT_PART(f.parche, '.', 2) AS parche_principal,
    f.campeon,
    f.rol,
    COUNT(DISTINCT f.match_id) AS partidas_distintas,
    COUNT(*) AS participaciones_totales,
    SUM(CASE WHEN f.victoria THEN 1 ELSE 0 END) AS victorias_reales,
    ROUND((SUM(CASE WHEN f.victoria THEN 1 ELSE 0 END)::NUMERIC / COUNT(*)) * 100, 2) AS winrate_dw_pct
FROM dw.fact_partidas f
WHERE f.queue_id = 420
  AND f.parche LIKE '16.18%'
  AND f.campeon IN ('Caitlyn', 'LeeSin', 'Lulu')
GROUP BY 
    SPLIT_PART(f.parche, '.', 1) || '.' || SPLIT_PART(f.parche, '.', 2), 
    f.campeon, 
    f.rol
ORDER BY participaciones_totales DESC;
