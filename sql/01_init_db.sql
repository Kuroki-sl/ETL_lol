
-- creacion esquemas raw, staging, dw, mart
CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS dw;
CREATE SCHEMA IF NOT EXISTS mart;

--tabla de auditoria y fallas
CREATE TABLE IF NOT EXISTS public.etl_audit (
    id_ejecucion SERIAL PRIMARY KEY,
    dag_name VARCHAR(100) NOT NULL,
    run_id VARCHAR(150) NOT NULL,
    fecha_ejecucion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    filas_leidas INT NOT NULL DEFAULT 0,
    filas_cargadas INT NOT NULL DEFAULT 0,
    porcentaje_nulos NUMERIC(5,2) NOT NULL DEFAULT 0.00,
    duracion_seg NUMERIC(10,2) NOT NULL DEFAULT 0.00,
    estado VARCHAR(30) NOT NULL,          -- 'SUCCESS' o 'FAILED'
    mensaje_error TEXT
);

--RAW
CREATE TABLE IF NOT EXISTS raw.raw_perfil_jugador (
    id_raw SERIAL PRIMARY KEY,
    riot_id VARCHAR(100) NOT NULL,
    puuid VARCHAR(100),
    payload_account JSONB NOT NULL,
    payload_summoner JSONB,
    payload_league JSONB,
    fecha_extraccion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS raw.raw_partidas (
    id_raw SERIAL PRIMARY KEY,
    match_id VARCHAR(50) NOT NULL,
    puuid_consulta VARCHAR(100) NOT NULL,
    payload_match JSONB NOT NULL,
    fecha_extraccion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
DELETE FROM raw.raw_partidas repetida
USING raw.raw_partidas conservada
WHERE repetida.match_id = conservada.match_id
  AND repetida.id_raw < conservada.id_raw;
CREATE UNIQUE INDEX IF NOT EXISTS uq_raw_partidas_match_id
    ON raw.raw_partidas (match_id);

--STAGING
CREATE TABLE IF NOT EXISTS staging.stg_jugador (
    puuid VARCHAR(100) PRIMARY KEY,
    game_name VARCHAR(60) NOT NULL,
    tag_line VARCHAR(20) NOT NULL,
    summoner_level INT NOT NULL,
    tier VARCHAR(30) NOT NULL,            -- IRON, BRONZE, SILVER, GOLD, PLATINUM, EMERALD, DIAMOND, MASTER, etc.
    rank_division VARCHAR(10) NOT NULL,   -- I, II, III, IV, N/A
    league_points INT NOT NULL DEFAULT 0,
    wins_temporada INT NOT NULL DEFAULT 0,
    losses_temporada INT NOT NULL DEFAULT 0,
    fecha_actualizacion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS staging.stg_partidas (
    match_id VARCHAR(50) NOT NULL,
    puuid VARCHAR(100) NOT NULL,
    fecha_partida TIMESTAMP NOT NULL,
    fecha_dia DATE NOT NULL,
    hora_del_dia INT NOT NULL,
    bloque_horario VARCHAR(20) NOT NULL,
    queue_id INT NOT NULL,
    parche VARCHAR(20) NOT NULL,
    campeon VARCHAR(50) NOT NULL,
    rol VARCHAR(20) NOT NULL,             -- TOP, JUNGLE, MIDDLE, BOTTOM, UTILITY
    asesinatos INT NOT NULL,
    muertes INT NOT NULL,
    asistencias INT NOT NULL,
    kda NUMERIC(6,2),
    oro_ganado INT NOT NULL,
    dano_campeones INT NOT NULL,
    dano_torres INT NOT NULL,
    objetivos_neutrales INT NOT NULL,       -- dragones/barones asegurados por el jugador
    vision INT NOT NULL,
    duracion_min NUMERIC(6,2) NOT NULL,
    victoria BOOLEAN NOT NULL,
    fecha_procesamiento TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (match_id, puuid)
);

--capa DW
CREATE TABLE IF NOT EXISTS dw.dim_tiempo (
    id_tiempo INT PRIMARY KEY,            -- Formato YYYYMMDDHH
    fecha DATE NOT NULL,
    anio INT NOT NULL,
    mes INT NOT NULL,
    dia INT NOT NULL,
    dia_semana VARCHAR(15) NOT NULL,
    hora INT NOT NULL,
    bloque_horario VARCHAR(20) NOT NULL   -- '00-03', '04-07', '08-11', '12-15', '16-19', '20-23'
);

CREATE TABLE IF NOT EXISTS dw.dim_jugador (
    puuid VARCHAR(100) PRIMARY KEY,
    nombre_completo VARCHAR(85) NOT NULL, -- gameName#tagLine
    liga VARCHAR(50) NOT NULL,            -- 'GOLD II' o 'UNRANKED'
    nivel INT NOT NULL,
    lp_actuales INT NOT NULL DEFAULT 0,
    fecha_actualizacion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS dw.fact_partidas (
    match_id VARCHAR(50) NOT NULL,
    puuid VARCHAR(100) NOT NULL REFERENCES dw.dim_jugador(puuid),
    id_tiempo INT NOT NULL REFERENCES dw.dim_tiempo(id_tiempo),
    queue_id INT NOT NULL,                 -- 420 = Ranked Solo/Duo
    parche VARCHAR(20) NOT NULL,
    campeon VARCHAR(50) NOT NULL,
    rol VARCHAR(20) NOT NULL,
    asesinatos INT NOT NULL,
    muertes INT NOT NULL,
    asistencias INT NOT NULL,
    kda NUMERIC(6,2),
    oro INT NOT NULL,
    dano_campeones INT NOT NULL,
    dano_torres INT NOT NULL,
    objetivos_neutrales INT NOT NULL,       -- dragones/barones asegurados por el jugador
    vision INT NOT NULL,
    duracion_min NUMERIC(6,2) NOT NULL,
    victoria BOOLEAN NOT NULL,
    PRIMARY KEY (match_id, puuid)
);

--capa MART (KPIs)
CREATE TABLE IF NOT EXISTS mart.kpi_01_mejores_campeones (
    puuid VARCHAR(100) NOT NULL,
    nombre_jugador VARCHAR(85) NOT NULL,
    campeon VARCHAR(50) NOT NULL,
    rol VARCHAR(20) NOT NULL,
    partidas_jugadas INT NOT NULL,
    victorias INT NOT NULL,
    winrate_pct NUMERIC(5,2) NOT NULL,
    kda_promedio NUMERIC(6,2),
    puntaje_compuesto NUMERIC(5,2),
    estado_muestra VARCHAR(30) NOT NULL DEFAULT 'MUESTRA INSUFICIENTE',
    cumple_meta BOOLEAN,
    fecha_calculo TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (puuid, campeon, rol)
);

CREATE TABLE IF NOT EXISTS mart.kpi_02_winrate_horario (
    puuid VARCHAR(100) NOT NULL,
    nombre_jugador VARCHAR(85) NOT NULL,
    bloque_horario VARCHAR(20) NOT NULL,
    partidas_jugadas INT NOT NULL,
    victorias INT NOT NULL,
    winrate_pct NUMERIC(5,2) NOT NULL,
    recomendacion_gestion VARCHAR(50) NOT NULL,
    fecha_calculo TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (puuid, bloque_horario)
);

CREATE TABLE IF NOT EXISTS mart.kpi_03_calificacion_rol (
    puuid VARCHAR(100) NOT NULL,
    nombre_jugador VARCHAR(85) NOT NULL,
    rol VARCHAR(20) NOT NULL,
    partidas_jugadas INT NOT NULL,
    dpm_promedio NUMERIC(8,2) NOT NULL,
    gpm_promedio NUMERIC(8,2) NOT NULL,
    vision_min_promedio NUMERIC(6,2) NOT NULL,
    nota_escala_1_a_7 NUMERIC(3,1),
    estado_rendimiento VARCHAR(30) NOT NULL,
    fecha_calculo TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (puuid, rol)
);

CREATE TABLE IF NOT EXISTS mart.kpi_04_control_actividad_diaria (
    puuid VARCHAR(100) NOT NULL,
    nombre_jugador VARCHAR(85) NOT NULL,
    fecha DATE NOT NULL,
    partidas_en_el_dia INT NOT NULL,
    horas_jugadas_dia NUMERIC(5,2) NOT NULL,
    winrate_del_dia NUMERIC(5,2),
    alerta_sobrecarga BOOLEAN NOT NULL,
    fecha_calculo TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (puuid, fecha)
);

CREATE TABLE IF NOT EXISTS mart.kpi_05_tierlist_meta_vs_otp (
    campeon VARCHAR(50) NOT NULL,
    rol VARCHAR(20) NOT NULL,
    parche VARCHAR(20) NOT NULL,
    partidas_totales INT NOT NULL,
    winrate_global_pct NUMERIC(5,2) NOT NULL,
    kda_global NUMERIC(6,2),
    clasificacion_tier VARCHAR(40) NOT NULL,
    fecha_calculo TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (campeon, rol, parche)
);
