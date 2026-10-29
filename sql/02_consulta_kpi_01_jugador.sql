-- HU-01 / Joaquín: recomendación de campeones para un Riot ID y rol opcional.
-- Cambiar los valores de entrada. Dejar el rol vacío para incluir todos los roles.
WITH parametros AS (
    SELECT
        'Frikz#xoro'::TEXT AS riot_id,
        NULLIF(UPPER(BTRIM(''::TEXT)), '') AS rol_opcional,
        3::INT AS minimo_partidas
)
SELECT
    k.puuid,
    k.nombre_jugador,
    k.rol,
    k.campeon,
    k.partidas_jugadas,
    k.victorias,
    k.winrate_pct,
    k.kda_promedio,
    k.puntaje_compuesto,
    k.estado_muestra,
    k.cumple_meta
FROM mart.kpi_01_mejores_campeones AS k
CROSS JOIN parametros AS p
WHERE LOWER(k.nombre_jugador) = LOWER(p.riot_id)
  AND (p.rol_opcional IS NULL OR UPPER(k.rol) = p.rol_opcional)
  AND k.partidas_jugadas >= p.minimo_partidas
  AND k.puntaje_compuesto IS NOT NULL
ORDER BY
    k.puntaje_compuesto DESC,
    k.winrate_pct DESC,
    k.partidas_jugadas DESC,
    k.campeon;

-- Trazabilidad: confirma que el mismo PUUID del jugador aparece en las partidas
-- clasificatorias guardadas y dentro del payload Match-V5 en RAW.
WITH parametros AS (
    SELECT 'Frikz#xoro'::TEXT AS riot_id
),
jugador AS (
    SELECT j.puuid, j.nombre_completo
    FROM dw.dim_jugador AS j
    CROSS JOIN parametros AS p
    WHERE LOWER(j.nombre_completo) = LOWER(p.riot_id)
)
SELECT
    f.puuid,
    j.nombre_completo AS riot_id,
    f.match_id,
    f.id_tiempo,
    f.queue_id,
    f.campeon,
    f.rol,
    r.puuid_consulta,
    EXISTS (
        SELECT 1
        FROM jsonb_array_elements_text(
            r.payload_match #> '{metadata,participants}'
        ) AS participantes(puuid)
        WHERE participantes.puuid = f.puuid
    ) AS puuid_presente_en_payload
FROM dw.fact_partidas AS f
JOIN jugador AS j ON j.puuid = f.puuid
JOIN raw.raw_partidas AS r ON r.match_id = f.match_id
WHERE f.queue_id = 420
ORDER BY f.id_tiempo DESC, f.match_id
LIMIT 20;
