import os
import time
import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import requests
import pandas as pd
from sqlalchemy import create_engine, text

#logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

#endpoints de Riot Games
DEFAULT_AMERICAS_URL = "https://americas.api.riotgames.com"
DEFAULT_LAS_URL = "https://la2.api.riotgames.com"
QUEUE_RANKED_SOLO_DUO = 420
CHILE_TIMEZONE = ZoneInfo("America/Santiago")


#conexion a DB y auditoria
def get_db_engine():
    """Retorna una conexión SQLAlchemy a PostgreSQL usando variables de entorno."""
    host = os.environ.get("PGHOST", "localhost")
    port = os.environ.get("PGPORT", "5432")
    database = os.environ.get("PGDATABASE", "gestion_lol")
    user = os.environ.get("PGUSER", "postgres")
    password = os.environ.get("PGPASSWORD", "")

    url = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{database}"
    return create_engine(url, pool_pre_ping=True)


def ensure_analytics_schema(engine=None):
    """Aplica cambios idempotentes requeridos por las correcciones analíticas."""
    engine = engine or get_db_engine()

    with engine.begin() as conn:
        conn.execute(text("SELECT pg_advisory_xact_lock(20261026);"))
        conn.execute(text("ALTER TABLE staging.stg_partidas ALTER COLUMN kda DROP NOT NULL;"))
        conn.execute(text("ALTER TABLE staging.stg_partidas ADD COLUMN IF NOT EXISTS parche VARCHAR(20);"))
        conn.execute(text("""
            UPDATE staging.stg_partidas s
            SET parche = CASE
                WHEN r.payload_match->'info'->>'gameVersion' ~ '^[0-9]+\\.[0-9]+'
                    THEN split_part(r.payload_match->'info'->>'gameVersion', '.', 1)
                         || '.' || split_part(r.payload_match->'info'->>'gameVersion', '.', 2)
                ELSE 'UNKNOWN'
            END
            FROM raw.raw_partidas r
            WHERE s.match_id = r.match_id AND s.parche IS NULL;
        """))
        conn.execute(text("UPDATE staging.stg_partidas SET parche = 'UNKNOWN' WHERE parche IS NULL;"))
        conn.execute(text("ALTER TABLE staging.stg_partidas ALTER COLUMN parche SET DEFAULT 'UNKNOWN';"))
        conn.execute(text("ALTER TABLE staging.stg_partidas ALTER COLUMN parche SET NOT NULL;"))
        conn.execute(text("ALTER TABLE dw.fact_partidas ADD COLUMN IF NOT EXISTS queue_id INT;"))
        conn.execute(text("ALTER TABLE dw.fact_partidas ADD COLUMN IF NOT EXISTS parche VARCHAR(20);"))
        conn.execute(text("""
            UPDATE dw.fact_partidas f
            SET queue_id = COALESCE(
                (
                    SELECT NULLIF(r.payload_match->'info'->>'queueId', '')::INT
                    FROM raw.raw_partidas r
                    WHERE r.match_id = f.match_id
                    ORDER BY r.fecha_extraccion DESC, r.id_raw DESC
                    LIMIT 1
                ),
                (
                    SELECT s.queue_id
                    FROM staging.stg_partidas s
                    WHERE s.match_id = f.match_id AND s.puuid = f.puuid
                    LIMIT 1
                ),
                0
            )
            WHERE f.queue_id IS NULL OR f.queue_id = 0;
        """))
        conn.execute(text("""
            UPDATE dw.fact_partidas f
            SET parche = COALESCE(
                (
                    SELECT CASE
                        WHEN r.payload_match->'info'->>'gameVersion' ~ '^[0-9]+\\.[0-9]+'
                            THEN split_part(r.payload_match->'info'->>'gameVersion', '.', 1)
                                 || '.' || split_part(r.payload_match->'info'->>'gameVersion', '.', 2)
                        ELSE 'UNKNOWN'
                    END
                    FROM raw.raw_partidas r
                    WHERE r.match_id = f.match_id
                    ORDER BY r.fecha_extraccion DESC, r.id_raw DESC
                    LIMIT 1
                ),
                (
                    SELECT s.parche
                    FROM staging.stg_partidas s
                    WHERE s.match_id = f.match_id AND s.puuid = f.puuid
                    LIMIT 1
                ),
                'UNKNOWN'
            )
            WHERE f.parche IS NULL;
        """))
        conn.execute(text("UPDATE dw.fact_partidas SET queue_id = 0 WHERE queue_id IS NULL;"))
        conn.execute(text("UPDATE dw.fact_partidas SET parche = 'UNKNOWN' WHERE parche IS NULL;"))
        conn.execute(text("ALTER TABLE dw.fact_partidas ALTER COLUMN queue_id SET DEFAULT 0;"))
        conn.execute(text("ALTER TABLE dw.fact_partidas ALTER COLUMN parche SET DEFAULT 'UNKNOWN';"))
        conn.execute(text("ALTER TABLE dw.fact_partidas ALTER COLUMN queue_id SET NOT NULL;"))
        conn.execute(text("ALTER TABLE dw.fact_partidas ALTER COLUMN parche SET NOT NULL;"))
        conn.execute(text("ALTER TABLE dw.fact_partidas ALTER COLUMN kda DROP NOT NULL;"))

        conn.execute(text("ALTER TABLE mart.kpi_01_mejores_campeones ADD COLUMN IF NOT EXISTS puntaje_compuesto NUMERIC(5,2);"))
        conn.execute(text("""
            ALTER TABLE mart.kpi_01_mejores_campeones
            ADD COLUMN IF NOT EXISTS estado_muestra VARCHAR(30) NOT NULL DEFAULT 'MUESTRA INSUFICIENTE';
        """))
        conn.execute(text("ALTER TABLE mart.kpi_01_mejores_campeones ALTER COLUMN kda_promedio DROP NOT NULL;"))
        conn.execute(text("ALTER TABLE mart.kpi_01_mejores_campeones ALTER COLUMN cumple_meta DROP NOT NULL;"))
        conn.execute(text("ALTER TABLE mart.kpi_03_calificacion_rol ALTER COLUMN nota_escala_1_a_7 DROP NOT NULL;"))
        conn.execute(text("ALTER TABLE mart.kpi_04_control_actividad_diaria ALTER COLUMN winrate_del_dia DROP NOT NULL;"))
        conn.execute(text("ALTER TABLE mart.kpi_05_tierlist_meta_vs_otp ALTER COLUMN kda_global DROP NOT NULL;"))
        conn.execute(text("""
            ALTER TABLE mart.kpi_05_tierlist_meta_vs_otp
            ADD COLUMN IF NOT EXISTS parche VARCHAR(20) NOT NULL DEFAULT 'UNKNOWN';
        """))
        kpi5_pk_definition = conn.execute(text("""
            SELECT pg_get_constraintdef(oid)
            FROM pg_constraint
            WHERE conrelid = 'mart.kpi_05_tierlist_meta_vs_otp'::regclass
              AND contype = 'p';
        """)).scalar()
        if kpi5_pk_definition != "PRIMARY KEY (campeon, rol, parche)":
            conn.execute(text("DELETE FROM mart.kpi_05_tierlist_meta_vs_otp;"))
            conn.execute(text("""
                ALTER TABLE mart.kpi_05_tierlist_meta_vs_otp
                DROP CONSTRAINT IF EXISTS kpi_05_tierlist_meta_vs_otp_pkey;
            """))
            conn.execute(text("""
                ALTER TABLE mart.kpi_05_tierlist_meta_vs_otp
                ADD CONSTRAINT kpi_05_tierlist_meta_vs_otp_pkey
                PRIMARY KEY (campeon, rol, parche);
            """))

        raw_index_exists = conn.execute(
            text("SELECT to_regclass('raw.uq_raw_partidas_match_id');")
        ).scalar()
        if raw_index_exists is None:
            conn.execute(text("""
                DELETE FROM raw.raw_partidas repetida
                USING raw.raw_partidas conservada
                WHERE repetida.match_id = conservada.match_id
                  AND repetida.id_raw < conservada.id_raw;
            """))
            conn.execute(text("""
                CREATE UNIQUE INDEX uq_raw_partidas_match_id
                ON raw.raw_partidas (match_id);
            """))


def registrar_auditoria(dag_name, run_id, filas_leidas=0, filas_cargadas=0,
                        porcentaje_nulos=0.0, duracion_seg=0.0, estado="SUCCESS",
                        mensaje_error=None):
    """
    Inserta un registro de trazabilidad en la tabla public.etl_audit.
    Cumple con el criterio de auditoría completa de la rúbrica (Ítem 5).
    """
    engine = get_db_engine()
    sql = text("""
        INSERT INTO public.etl_audit (
            dag_name, run_id, fecha_ejecucion, filas_leidas, filas_cargadas,
            porcentaje_nulos, duracion_seg, estado, mensaje_error
        ) VALUES (
            :dag_name, :run_id, CURRENT_TIMESTAMP, :filas_leidas, :filas_cargadas,
            :porcentaje_nulos, :duracion_seg, :estado, :mensaje_error
        );
    """)

    try:
        with engine.begin() as conn:
            conn.execute(sql, {
                "dag_name": str(dag_name)[:100],
                "run_id": str(run_id)[:150],
                "filas_leidas": int(filas_leidas),
                "filas_cargadas": int(filas_cargadas),
                "porcentaje_nulos": float(round(porcentaje_nulos, 2)),
                "duracion_seg": float(round(duracion_seg, 2)),
                "estado": str(estado)[:30],
                "mensaje_error": str(mensaje_error) if mensaje_error else None
            })
        logger.info(f"[AUDIT] Registro guardado con éxito: {dag_name} | {estado} | Cargadas: {filas_cargadas}")
    except Exception as e:
        logger.error(f"[AUDIT ERROR] No se pudo guardar auditoría en BD: {e}")


def on_dag_failure_callback(context):
    """Callback invocado automáticamente por Airflow cuando una tarea o DAG falla."""
    dag_id = context.get("dag").dag_id if context.get("dag") else "dag_desconocido"
    run_id = context.get("run_id", "run_id_desconocido")
    exception = str(context.get("exception", "Error no especificado"))
    logger.error(f"[CALLBACK FALLA] DAG: {dag_id} falló en run: {run_id}. Detalle: {exception}")
    registrar_auditoria(
        dag_name=dag_id,
        run_id=run_id,
        estado="FAILED",
        mensaje_error=exception
    )


#HTTP tolerante a fallas

def get_riot_headers(api_key=None):
    """Retorna las cabeceras requeridas con la API Key."""
    key = api_key or os.environ.get("RIOT_API_KEY", "")
    if not key:
        raise ValueError("No se ha configurado RIOT_API_KEY en las variables de entorno o Airflow Variables.")
    return {"X-Riot-Token": key}


def request_riot_api(url, headers, timeout=15, max_retries=3):
    """
    Realiza peticiones HTTP GET a Riot API con reintentos, manejo de Rate Limits (HTTP 429)
    y reintentos ante errores temporales de servidor (HTTP 5xx) y fallas de red.
    """
    ultimo_error = None
    for intento in range(1, max_retries + 1):
        try:
            response = requests.get(url, headers=headers, timeout=timeout)
            if response.status_code == 200:
                return response.json()

            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", 5))
                ultimo_error = f"HTTP 429 Rate Limit en {url}"
                logger.warning(
                    f"[RATE LIMIT 429] Intento {intento}/{max_retries} en {url}. "
                    f"Esperando {retry_after} segundos antes de reintentar..."
                )
                if intento == max_retries:
                    raise RuntimeError(f"[HTTP 429] Límite de consultas excedido tras {max_retries} intentos: {url}")
                time.sleep(retry_after + 1)
                continue

            if response.status_code in [401, 403]:
                error_msg = f"[HTTP {response.status_code}] Clave de API Riot inválida o expirada al consultar: {url}"
                logger.error(error_msg)
                raise PermissionError(error_msg)

            if response.status_code == 404:
                logger.warning(f"[HTTP 404] Recurso no encontrado: {url}")
                return None

            if 500 <= response.status_code < 600:
                espera = 3 * intento
                ultimo_error = f"HTTP {response.status_code} Error de servidor en {url}"
                logger.warning(
                    f"[ERROR SERVIDOR 5xx] HTTP {response.status_code} en intento {intento}/{max_retries} "
                    f"para {url}. Reintentando en {espera} segundos..."
                )
                if intento == max_retries:
                    response.raise_for_status()
                time.sleep(espera)
                continue

            logger.error(f"[HTTP {response.status_code}] Error HTTP no recuperable al consultar: {url}")
            response.raise_for_status()

        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as net_err:
            tipo_err = type(net_err).__name__
            ultimo_error = f"{tipo_err}: {net_err}"
            logger.warning(f"[ERROR RED - {tipo_err}] Intento {intento}/{max_retries} falló para {url}: {net_err}")
            if intento == max_retries:
                raise
            time.sleep(3 * intento)

    raise RuntimeError(f"Falla tras {max_retries} intentos al consultar: {url}. Último error: {ultimo_error}")


def validar_estado_api(base_url, api_key):
    """
    Validación previa de la API antes de extraer (criterio de rúbrica).
    Consulta el estado del servidor LAS o la API de cuentas y falla explícitamente
    ante errores 401/403, 429, 5xx o códigos HTTP inesperados.
    """
    headers = get_riot_headers(api_key)
    base_clean = (base_url or DEFAULT_AMERICAS_URL).rstrip("/")
    # Si base_url es americas, usamos endpoint de cuentas; de lo contrario status de la plataforma indicada
    if "americas" in base_clean:
        url = f"{base_clean}/riot/account/v1/accounts/by-riot-id/Faker/KR1"
        codigos_validos = (200, 404)
    else:
        url = f"{base_clean}/lol/status/v4/platform-data"
        codigos_validos = (200,)

    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code in codigos_validos:
            logger.info(f"[HEALTH CHECK] API de Riot disponible (HTTP {resp.status_code}) y token válido.")
            return True
        if resp.status_code in [401, 403]:
            raise PermissionError(
                f"[HEALTH CHECK FALLÓ] API Key rechazada por Riot Games "
                f"(HTTP {resp.status_code} - Token inválido o expirado)."
            )
        if resp.status_code == 429:
            raise RuntimeError(
                f"[HEALTH CHECK FALLÓ] Rate limit activo en Riot Games (HTTP 429) al validar: {url}"
            )
        if 500 <= resp.status_code < 600:
            raise RuntimeError(
                f"[HEALTH CHECK FALLÓ] Error de servidor en Riot Games (HTTP {resp.status_code}) al validar: {url}"
            )
        raise RuntimeError(
            f"[HEALTH CHECK FALLÓ] Código de respuesta inesperado (HTTP {resp.status_code}) al validar: {url}"
        )
    except Exception as e:
        logger.error(f"[HEALTH CHECK EXCEPCIÓN] {e}")
        raise


#pipeline#1 perfil y clasificacion de jugadores

def extract_perfiles_riot(target_players, api_key, americas_url=DEFAULT_AMERICAS_URL, las_url=DEFAULT_LAS_URL):
    """
    Extrae perfiles desde Account-V1, Summoner-V4 y League-V4 y los persiste en raw.raw_perfil_jugador.
    """
    headers = get_riot_headers(api_key)
    engine = get_db_engine()
    registros_guardados = 0

    for jugador in target_players:
        game_name = jugador["gameName"]
        tag_line = jugador["tagLine"]
        riot_id = f"{game_name}#{tag_line}"

        # 1. Account-V1 (americas)
        url_account = f"{americas_url}/riot/account/v1/accounts/by-riot-id/{game_name}/{tag_line}"
        account_data = request_riot_api(url_account, headers)
        if not account_data or "puuid" not in account_data:
            logger.warning(f"No se pudo obtener cuenta para {riot_id}")
            continue

        puuid = account_data["puuid"]

        # 2. Summoner-V4 (las / la2)
        url_summoner = f"{las_url}/lol/summoner/v4/summoners/by-puuid/{puuid}"
        summoner_data = request_riot_api(url_summoner, headers)

        # 3. League-V4 (las / la2 por puuid o summoner_id)
        league_data = []
        url_league_puuid = f"{las_url}/lol/league/v4/entries/by-puuid/{puuid}"
        try:
            league_data = request_riot_api(url_league_puuid, headers)
        except Exception:
            league_data = []

        if not league_data and summoner_data and "id" in summoner_data:
            summoner_id = summoner_data["id"]
            url_league = f"{las_url}/lol/league/v4/entries/by-summoner/{summoner_id}"
            league_data = request_riot_api(url_league, headers) or []

        # Inserción en raw.raw_perfil_jugador
        import json
        sql_insert = text("""
            INSERT INTO raw.raw_perfil_jugador (riot_id, puuid, payload_account, payload_summoner, payload_league)
            VALUES (:riot_id, :puuid, :payload_account, :payload_summoner, :payload_league);
        """)

        with engine.begin() as conn:
            conn.execute(sql_insert, {
                "riot_id": riot_id,
                "puuid": puuid,
                "payload_account": json.dumps(account_data),
                "payload_summoner": json.dumps(summoner_data) if summoner_data else None,
                "payload_league": json.dumps(league_data) if league_data else None
            })
        registros_guardados += 1

    return registros_guardados


def transform_and_load_staging_jugador():
    """
    Lee de raw.raw_perfil_jugador, limpia y normaliza hacia staging.stg_jugador.
    """
    engine = get_db_engine()
    query = text("""
        SELECT DISTINCT ON (puuid)
            puuid,
            riot_id,
            payload_account,
            payload_summoner,
            payload_league,
            fecha_extraccion
        FROM raw.raw_perfil_jugador
        WHERE puuid IS NOT NULL
        ORDER BY puuid, fecha_extraccion DESC;
    """)

    df_raw = pd.read_sql(query, engine)
    if df_raw.empty:
        logger.info("No hay perfiles para transformar en raw.")
        return 0, 0.0

    registros = []
    campos_nulos_contador = 0
    # 7 campos esperados por jugador entre las 3 APIs (Account-V1, Summoner-V4 y League-V4):
    # puuid, gameName, tagLine, summonerLevel, tier, rank y leaguePoints.
    total_campos_esperados = len(df_raw) * 7

    for _, row in df_raw.iterrows():
        puuid = row["puuid"]
        acc = row["payload_account"] if isinstance(row["payload_account"], dict) else {}
        summ = row["payload_summoner"] if isinstance(row["payload_summoner"], dict) else {}
        raw_leagues = row["payload_league"]
        leagues = raw_leagues if isinstance(raw_leagues, list) else []

        raw_game_name = acc.get("gameName")
        raw_tag_line = acc.get("tagLine")
        raw_summoner_level = summ.get("summonerLevel")

        game_name = raw_game_name if raw_game_name not in (None, "") else "Desconocido"
        tag_line = raw_tag_line if raw_tag_line not in (None, "") else "LAS"
        summoner_level = raw_summoner_level if raw_summoner_level is not None else 1

        # Buscar clasificación SoloQ (RANKED_SOLO_5x5) o tomar la primera
        tier = "UNRANKED"
        rank_division = "N/A"
        lp = 0
        wins = 0
        losses = 0

        if len(leagues) > 0:
            soloq = next((l for l in leagues if isinstance(l, dict) and l.get("queueType") == "RANKED_SOLO_5x5"), leagues[0])
            raw_tier = soloq.get("tier")
            raw_rank = soloq.get("rank")
            raw_lp = soloq.get("leaguePoints")
            tier = raw_tier if raw_tier not in (None, "") else "UNRANKED"
            rank_division = raw_rank if raw_rank not in (None, "") else "N/A"
            lp = raw_lp if raw_lp is not None else 0
            wins = soloq.get("wins", 0) if soloq.get("wins") is not None else 0
            losses = soloq.get("losses", 0) if soloq.get("losses") is not None else 0
            liga_valida_tier = raw_tier not in (None, "")
            liga_valida_rank = raw_rank not in (None, "")
            liga_valida_lp = raw_lp is not None
        else:
            # Si League-V4 respondió una lista vacía [], el estado UNRANKED es válido del dominio
            # y no un dato nulo; solo es nulo si payload_league vino NULL (fallo/ausencia de respuesta).
            league_respondio = isinstance(raw_leagues, list)
            liga_valida_tier = league_respondio
            liga_valida_rank = league_respondio
            liga_valida_lp = league_respondio

        campos_presentes = [
            puuid not in (None, ""),
            raw_game_name not in (None, ""),
            raw_tag_line not in (None, ""),
            raw_summoner_level is not None,
            liga_valida_tier,
            liga_valida_rank,
            liga_valida_lp,
        ]
        campos_nulos_contador += sum(1 for presente in campos_presentes if not presente)

        registros.append({
            "puuid": puuid,
            "game_name": game_name,
            "tag_line": tag_line,
            "summoner_level": summoner_level,
            "tier": tier,
            "rank_division": rank_division,
            "league_points": lp,
            "wins_temporada": wins,
            "losses_temporada": losses
        })

    df_stg = pd.DataFrame(registros).drop_duplicates(subset=["puuid"], keep="last")
    pct_nulos = (campos_nulos_contador / max(total_campos_esperados, 1)) * 100

    # Inserción en staging.stg_jugador con ON CONFLICT DO UPDATE
    sql_upsert = text("""
        INSERT INTO staging.stg_jugador (
            puuid, game_name, tag_line, summoner_level, tier, rank_division,
            league_points, wins_temporada, losses_temporada, fecha_actualizacion
        ) VALUES (
            :puuid, :game_name, :tag_line, :summoner_level, :tier, :rank_division,
            :league_points, :wins_temporada, :losses_temporada, CURRENT_TIMESTAMP
        )
        ON CONFLICT (puuid) DO UPDATE SET
            game_name = EXCLUDED.game_name,
            tag_line = EXCLUDED.tag_line,
            summoner_level = EXCLUDED.summoner_level,
            tier = EXCLUDED.tier,
            rank_division = EXCLUDED.rank_division,
            league_points = EXCLUDED.league_points,
            wins_temporada = EXCLUDED.wins_temporada,
            losses_temporada = EXCLUDED.losses_temporada,
            fecha_actualizacion = CURRENT_TIMESTAMP;
    """)

    with engine.begin() as conn:
        for item in df_stg.to_dict(orient="records"):
            conn.execute(sql_upsert, item)

    logger.info(f"[STAGING JUGADOR] {len(df_stg)} perfiles cargados en staging.stg_jugador.")
    return len(df_stg), pct_nulos


def load_dw_dim_jugador():
    """
    Carga idempotente desde staging.stg_jugador hacia dw.dim_jugador.
    """
    engine = get_db_engine()
    sql_load = text("""
        INSERT INTO dw.dim_jugador (puuid, nombre_completo, liga, nivel, lp_actuales, fecha_actualizacion)
        SELECT
            puuid,
            game_name || '#' || tag_line AS nombre_completo,
            tier || ' ' || rank_division AS liga,
            summoner_level,
            league_points,
            CURRENT_TIMESTAMP
        FROM staging.stg_jugador
        ON CONFLICT (puuid) DO UPDATE SET
            nombre_completo = EXCLUDED.nombre_completo,
            liga = EXCLUDED.liga,
            nivel = EXCLUDED.nivel,
            lp_actuales = EXCLUDED.lp_actuales,
            fecha_actualizacion = CURRENT_TIMESTAMP;
    """)

    with engine.begin() as conn:
        result = conn.execute(sql_load)
        cargadas = result.rowcount

    logger.info(f"[DW DIM_JUGADOR] {cargadas} registros actualizados en dw.dim_jugador.")
    return cargadas


#pipeline#2 historial de partidas (Match-V5)

def extraer_partidas_riot(api_key, puuids=None, count=20, start_time=None, end_time=None,
                          americas_url=DEFAULT_AMERICAS_URL):
    """
    Obtiene IDs de partidas para los PUUIDs indicados (o los presentes en dw.dim_jugador),
    verifica cuáles ya existen en raw.raw_partidas para no repetir peticiones innecesarias,
    descarga el detalle JSON e inserta en raw.raw_partidas.
    """
    headers = get_riot_headers(api_key)
    engine = get_db_engine()
    ensure_analytics_schema(engine)

    # Si no vienen PUUIDs, buscar en dw.dim_jugador o en staging.stg_jugador
    if not puuids:
        with engine.connect() as conn:
            res = conn.execute(text("SELECT puuid FROM dw.dim_jugador UNION SELECT puuid FROM staging.stg_jugador;"))
            puuids = [r[0] for r in res.fetchall()]

    if not puuids:
        logger.warning("No hay PUUIDs para consultar partidas.")
        return 0

    # Partidas ya existentes en raw para evitar consultas redundantes
    with engine.connect() as conn:
        res = conn.execute(text("SELECT match_id FROM raw.raw_partidas;"))
        partidas_existentes = set(r[0] for r in res.fetchall())

    partidas_nuevas_insertadas = 0
    import json

    for puuid in puuids:
        url_ids = (
            f"{americas_url}/lol/match/v5/matches/by-puuid/{puuid}/ids"
            f"?start=0&count={count}&queue={QUEUE_RANKED_SOLO_DUO}"
        )
        if start_time:
            url_ids += f"&startTime={start_time}"
        if end_time:
            url_ids += f"&endTime={end_time}"

        match_ids = request_riot_api(url_ids, headers) or []
        logger.info(f"PUUID {puuid[:12]}... devolvió {len(match_ids)} IDs de partidas.")

        for mid in match_ids:
            if mid in partidas_existentes:
                continue

            # Obtener detalle de partida
            url_detail = f"{americas_url}/lol/match/v5/matches/{mid}"
            detail_json = request_riot_api(url_detail, headers)

            if detail_json and "info" in detail_json:
                sql_insert = text("""
                    INSERT INTO raw.raw_partidas (match_id, puuid_consulta, payload_match)
                    VALUES (:match_id, :puuid_consulta, :payload_match)
                    ON CONFLICT (match_id) DO NOTHING;
                """)
                with engine.begin() as conn:
                    conn.execute(sql_insert, {
                        "match_id": mid,
                        "puuid_consulta": puuid,
                        "payload_match": json.dumps(detail_json)
                    })
                partidas_existentes.add(mid)
                partidas_nuevas_insertadas += 1

    return partidas_nuevas_insertadas


def contar_participaciones_raw_partidas(engine=None):
    """
    Cuenta el total de participaciones en partidas clasificatorias Solo/Duo (queue_id=420)
    almacenadas en raw.raw_partidas para reportar filas_leidas en la misma unidad que dw.fact_partidas.
    """
    engine = engine or get_db_engine()
    sql = text("""
        WITH partidas_unicas AS (
            SELECT DISTINCT ON (match_id) match_id, payload_match
            FROM raw.raw_partidas
            ORDER BY match_id, fecha_extraccion DESC, id_raw DESC
        )
        SELECT COALESCE(
            SUM(
                GREATEST(
                    COALESCE(jsonb_array_length(payload_match->'info'->'participants'), 0),
                    10
                )
            ),
            0
        )::INT
        FROM partidas_unicas
        WHERE NULLIF(payload_match->'info'->>'queueId', '')::INT = :queue_id;
    """)
    with engine.connect() as conn:
        return int(conn.execute(sql, {"queue_id": QUEUE_RANKED_SOLO_DUO}).scalar() or 0)


def transform_and_load_staging_partidas():
    """
    Parsea los JSON de raw.raw_partidas, normaliza métricas a snake_case,
    conserva todas las participaciones de cada partida Solo/Duo, convierte la
    hora a America/Santiago y descarta remakes (< 5 min).
    Calcula porcentaje_nulos sobre los 10 campos esperados por participación Solo/Duo.
    """
    engine = get_db_engine()
    ensure_analytics_schema(engine)
    query = text("""
        SELECT DISTINCT ON (match_id) match_id, payload_match
        FROM raw.raw_partidas
        ORDER BY match_id, fecha_extraccion DESC, id_raw DESC;
    """)
    df_raw = pd.read_sql(query, engine)

    if df_raw.empty:
        logger.warning("RAW no contiene partidas; se conserva STAGING para evitar borrar hechos previamente cargados.")
        return 0, 0.0

    registros_partidas = []
    filas_invalidas = 0
    partidas_otra_cola = 0
    # 10 campos esperados por participación Solo/Duo:
    # puuid, fecha_y_duracion_valida, parche, campeon, rol, asesinatos, muertes, asistencias, oro_dano, victoria
    CAMPOS_POR_PARTICIPACION = 10
    total_campos_esperados = 0
    campos_nulos_o_invalidos = 0

    for _, row in df_raw.iterrows():
        mid = row["match_id"]
        payload = row["payload_match"] or {}
        info = payload.get("info", {})

        game_start_ms = info.get("gameStartTimestamp") or info.get("gameCreation")
        game_duration_sec = info.get("gameDuration", 0)
        queue_id = info.get("queueId", 0)
        game_version = str(info.get("gameVersion") or "")
        version_parts = game_version.split(".")
        parche = ".".join(version_parts[:2]) if len(version_parts) >= 2 else "UNKNOWN"

        if queue_id != QUEUE_RANKED_SOLO_DUO:
            partidas_otra_cola += 1
            continue

        participants = info.get("participants", [])
        num_participantes_partida = max(len(participants), 10)
        total_campos_esperados += num_participantes_partida * CAMPOS_POR_PARTICIPACION

        # Duración en minutos
        duracion_min = round(game_duration_sec / 60.0, 2)
        # Filtro de calidad: partidas remake (< 5 min) o sin fecha de inicio válida
        if duracion_min < 5.0 or not game_start_ms:
            filas_invalidas += 1
            campos_nulos_o_invalidos += num_participantes_partida * CAMPOS_POR_PARTICIPACION
            continue

        fecha_partida = datetime.fromtimestamp(
            game_start_ms / 1000.0,
            tz=timezone.utc
        ).astimezone(CHILE_TIMEZONE).replace(tzinfo=None)
        fecha_dia = fecha_partida.date()
        hora_del_dia = fecha_partida.hour

        # Bloque horario
        if 0 <= hora_del_dia <= 3:
            bloque = "00-03"
        elif 4 <= hora_del_dia <= 7:
            bloque = "04-07"
        elif 8 <= hora_del_dia <= 11:
            bloque = "08-11"
        elif 12 <= hora_del_dia <= 15:
            bloque = "12-15"
        elif 16 <= hora_del_dia <= 19:
            bloque = "16-19"
        else:
            bloque = "20-23"

        if len(participants) < 10:
            campos_nulos_o_invalidos += (10 - len(participants)) * CAMPOS_POR_PARTICIPACION

        for p in participants:
            p_puuid = p.get("puuid")
            if not p_puuid:
                campos_nulos_o_invalidos += CAMPOS_POR_PARTICIPACION
                continue

            raw_champ = p.get("championName")
            raw_kills = p.get("kills")
            raw_deaths = p.get("deaths")
            raw_assists = p.get("assists")
            raw_gold = p.get("goldEarned")
            raw_dmg_champ = p.get("totalDamageDealtToChampions")
            raw_win = p.get("win")

            asesinatos = int(raw_kills or 0)
            muertes = int(raw_deaths or 0)
            asistencias = int(raw_assists or 0)
            # Si no hay muertes, se usa 1 como divisor para no penalizar un KDA perfecto.
            kda = round((asesinatos + asistencias) / max(muertes, 1), 2)

            # Normalización de rol
            rol = p.get("teamPosition") or p.get("individualPosition") or "SIN_ROL"
            if rol in ["", "Invalid"]:
                rol = "SIN_ROL"
            elif rol == "UTILITY":
                rol = "SUPPORT"
            elif rol == "BOTTOM":
                rol = "ADC"

            campos_validos_participante = [
                True,  # puuid presente
                True,  # fecha_partida y duracion_min >= 5.0 válidas
                parche != "UNKNOWN",
                raw_champ not in (None, ""),
                rol != "SIN_ROL",
                raw_kills is not None,
                raw_deaths is not None,
                raw_assists is not None,
                (raw_gold is not None and raw_dmg_champ is not None),
                raw_win is not None,
            ]
            campos_nulos_o_invalidos += sum(1 for valido in campos_validos_participante if not valido)

            registros_partidas.append({
                "match_id": mid,
                "puuid": p_puuid,
                "fecha_partida": fecha_partida,
                "fecha_dia": fecha_dia,
                "hora_del_dia": hora_del_dia,
                "bloque_horario": bloque,
                "queue_id": queue_id,
                "parche": parche,
                "campeon": raw_champ if raw_champ not in (None, "") else "Desconocido",
                "rol": rol,
                "asesinatos": asesinatos,
                "muertes": muertes,
                "asistencias": asistencias,
                "kda": kda,
                "oro_ganado": raw_gold if raw_gold is not None else 0,
                "dano_campeones": raw_dmg_champ if raw_dmg_champ is not None else 0,
                "dano_torres": p.get("damageDealtToTurrets", 0) or 0,
                # Aproximación individual para JG: dragones/barones asegurados;
                # no se suman súbditos neutrales como si fueran objetivos épicos.
                "objetivos_neutrales": (p.get("dragonKills", 0) or 0) + (p.get("baronKills", 0) or 0),
                "vision": p.get("visionScore", 0) or 0,
                "duracion_min": duracion_min,
                "victoria": bool(raw_win if raw_win is not None else False)
            })

    if not registros_partidas:
        raise ValueError(
            f"RAW contiene {len(df_raw)} partidas, pero ninguna produjo participaciones Solo/Duo válidas; "
            "se conserva STAGING y no se continúa a la sincronización del DW."
        )

    df_stg = pd.DataFrame(registros_partidas).drop_duplicates(subset=["match_id", "puuid"], keep="last")
    pct_nulos = (campos_nulos_o_invalidos / max(total_campos_esperados, 1)) * 100

    sql_upsert = text("""
        INSERT INTO staging.stg_partidas (
            match_id, puuid, fecha_partida, fecha_dia, hora_del_dia, bloque_horario,
            queue_id, parche, campeon, rol, asesinatos, muertes, asistencias, kda,
            oro_ganado, dano_campeones, dano_torres, objetivos_neutrales,
            vision, duracion_min, victoria, fecha_procesamiento
        ) VALUES (
            :match_id, :puuid, :fecha_partida, :fecha_dia, :hora_del_dia, :bloque_horario,
            :queue_id, :parche, :campeon, :rol, :asesinatos, :muertes, :asistencias, :kda,
            :oro_ganado, :dano_campeones, :dano_torres, :objetivos_neutrales,
            :vision, :duracion_min, :victoria, CURRENT_TIMESTAMP
        )
        ON CONFLICT (match_id, puuid) DO UPDATE SET
            fecha_partida = EXCLUDED.fecha_partida,
            fecha_dia = EXCLUDED.fecha_dia,
            hora_del_dia = EXCLUDED.hora_del_dia,
            bloque_horario = EXCLUDED.bloque_horario,
            queue_id = EXCLUDED.queue_id,
            parche = EXCLUDED.parche,
            campeon = EXCLUDED.campeon,
            rol = EXCLUDED.rol,
            asesinatos = EXCLUDED.asesinatos,
            muertes = EXCLUDED.muertes,
            asistencias = EXCLUDED.asistencias,
            kda = EXCLUDED.kda,
            oro_ganado = EXCLUDED.oro_ganado,
            dano_campeones = EXCLUDED.dano_campeones,
            dano_torres = EXCLUDED.dano_torres,
            objetivos_neutrales = EXCLUDED.objetivos_neutrales,
            vision = EXCLUDED.vision,
            duracion_min = EXCLUDED.duracion_min,
            victoria = EXCLUDED.victoria,
            fecha_procesamiento = CURRENT_TIMESTAMP;
    """)

    with engine.begin() as conn:
        # Reconstruir STAGING dentro de la misma transacción que la carga evita
        # dejarla vacía si ocurre un error durante el procesamiento.
        conn.execute(text("DELETE FROM staging.stg_partidas;"))
        for item in df_stg.to_dict(orient="records"):
            conn.execute(sql_upsert, item)

    logger.info(
        f"[STAGING PARTIDAS] {len(df_stg)} participaciones Solo/Duo cargadas; "
        f"{partidas_otra_cola} partidas descartadas por queue_id y {filas_invalidas} por calidad."
    )
    return len(df_stg), pct_nulos


def load_dw_hechos_y_tiempo():
    """
    Carga idempotente hacia dw.dim_tiempo y dw.fact_partidas asegurando integridad referencial.
    """
    engine = get_db_engine()
    ensure_analytics_schema(engine)

    with engine.connect() as conn:
        filas_staging = conn.execute(text("SELECT COUNT(*) FROM staging.stg_partidas;")).scalar() or 0
        filas_dw = conn.execute(text("SELECT COUNT(*) FROM dw.fact_partidas;")).scalar() or 0
    if filas_staging == 0 and filas_dw > 0:
        raise ValueError(
            "STAGING está vacío pero DW conserva partidas; se cancela la sincronización "
            "para evitar borrar los hechos existentes."
        )

    # 1. Asegurar dimensión de tiempo
    sql_dim_tiempo = text("""
        INSERT INTO dw.dim_tiempo (id_tiempo, fecha, anio, mes, dia, dia_semana, hora, bloque_horario)
        SELECT DISTINCT
            TO_CHAR(fecha_partida, 'YYYYMMDDHH24')::INT AS id_tiempo,
            fecha_dia,
            EXTRACT(YEAR FROM fecha_partida)::INT AS anio,
            EXTRACT(MONTH FROM fecha_partida)::INT AS mes,
            EXTRACT(DAY FROM fecha_partida)::INT AS dia,
            TO_CHAR(fecha_partida, 'Day') AS dia_semana,
            hora_del_dia,
            bloque_horario
        FROM staging.stg_partidas
        ON CONFLICT (id_tiempo) DO NOTHING;
    """)

    # 2. Asegurar que los jugadores existan en dw.dim_jugador para no romper Foreign Key
    sql_ensure_player = text("""
        INSERT INTO dw.dim_jugador (puuid, nombre_completo, liga, nivel, lp_actuales)
        SELECT DISTINCT
            s.puuid,
            'Jugador_' || SUBSTRING(s.puuid, 1, 6) AS nombre_completo,
            'UNRANKED' AS liga,
            1 AS nivel,
            0 AS lp_actuales
        FROM staging.stg_partidas s
        WHERE NOT EXISTS (SELECT 1 FROM dw.dim_jugador j WHERE j.puuid = s.puuid)
        ON CONFLICT (puuid) DO NOTHING;
    """)

    # 3. Cargar tabla de hechos dw.fact_partidas
    sql_fact_partidas = text("""
        INSERT INTO dw.fact_partidas (
            match_id, puuid, id_tiempo, queue_id, parche, campeon, rol, asesinatos, muertes, asistencias,
            kda, oro, dano_campeones, dano_torres, objetivos_neutrales, vision,
            duracion_min, victoria
        )
        SELECT
            match_id,
            puuid,
            TO_CHAR(fecha_partida, 'YYYYMMDDHH24')::INT AS id_tiempo,
            queue_id,
            parche,
            campeon,
            rol,
            asesinatos,
            muertes,
            asistencias,
            kda,
            oro_ganado AS oro,
            dano_campeones,
            dano_torres,
            objetivos_neutrales,
            vision,
            duracion_min,
            victoria
        FROM staging.stg_partidas
        ON CONFLICT (match_id, puuid) DO UPDATE SET
            id_tiempo = EXCLUDED.id_tiempo,
            queue_id = EXCLUDED.queue_id,
            parche = EXCLUDED.parche,
            campeon = EXCLUDED.campeon,
            rol = EXCLUDED.rol,
            asesinatos = EXCLUDED.asesinatos,
            muertes = EXCLUDED.muertes,
            asistencias = EXCLUDED.asistencias,
            kda = EXCLUDED.kda,
            oro = EXCLUDED.oro,
            dano_campeones = EXCLUDED.dano_campeones,
            dano_torres = EXCLUDED.dano_torres,
            objetivos_neutrales = EXCLUDED.objetivos_neutrales,
            vision = EXCLUDED.vision,
            duracion_min = EXCLUDED.duracion_min,
            victoria = EXCLUDED.victoria;
    """)

    with engine.begin() as conn:
        conn.execute(sql_dim_tiempo)
        conn.execute(sql_ensure_player)
        conn.execute(text("""
            DELETE FROM dw.fact_partidas f
            WHERE NOT EXISTS (
                SELECT 1
                FROM staging.stg_partidas s
                WHERE s.match_id = f.match_id AND s.puuid = f.puuid
            );
        """))
        res = conn.execute(sql_fact_partidas)
        cargadas = res.rowcount

    logger.info(f"[DW FACT_PARTIDAS] {cargadas} hechos sincronizados con dw.fact_partidas.")
    return cargadas


#pipeline#3 KPIs en capa mart

def calcular_kpis_mart(min_partidas_kpi1=10, min_partidas_kpi2=10,
                       min_partidas_kpi3=10, min_partidas_kpi5=10):
    """Recalcula los cinco KPI solo con ranked Solo/Duo y muestra visible."""
    engine = get_db_engine()
    ensure_analytics_schema(engine)

    # KPI 1: KDA agregado con sumas y divisor mínimo 1; no se promedian KDA por partida.
    # El puntaje combina winrate (60%), KDA normalizado (25%) y volumen hasta 50
    # partidas (15%). El puntaje y el cumplimiento quedan nulos bajo el mínimo.
    sql_kpi1 = text("""
        WITH agregados AS (
            SELECT
                f.puuid,
                j.nombre_completo AS nombre_jugador,
                f.campeon,
                f.rol,
                COUNT(*)::INT AS partidas_jugadas,
                SUM(CASE WHEN f.victoria THEN 1 ELSE 0 END)::INT AS victorias,
                SUM(f.asesinatos)::BIGINT AS asesinatos,
                SUM(f.muertes)::BIGINT AS muertes,
                SUM(f.asistencias)::BIGINT AS asistencias
            FROM dw.fact_partidas f
            JOIN dw.dim_jugador j ON f.puuid = j.puuid
            WHERE f.queue_id = 420
            GROUP BY f.puuid, j.nombre_completo, f.campeon, f.rol
        ),
        indicadores AS (
            SELECT
                *,
                ROUND((victorias::NUMERIC / partidas_jugadas) * 100, 2) AS winrate_pct,
                ROUND(((asesinatos + asistencias)::NUMERIC / GREATEST(muertes, 1)), 2) AS kda_periodo
            FROM agregados
        )
        INSERT INTO mart.kpi_01_mejores_campeones (
            puuid, nombre_jugador, campeon, rol, partidas_jugadas, victorias,
            winrate_pct, kda_promedio, puntaje_compuesto, estado_muestra,
            cumple_meta, fecha_calculo
        )
        SELECT
            puuid,
            nombre_jugador,
            campeon,
            rol,
            partidas_jugadas,
            victorias,
            winrate_pct,
            kda_periodo,
            CASE
                WHEN partidas_jugadas >= :min_partidas_kpi1 THEN
                    ROUND((0.60 * winrate_pct
                         + 0.25 * LEAST(100.0, kda_periodo * 20.0)
                         + 0.15 * LEAST(100.0, partidas_jugadas * 2.0))::NUMERIC, 2)
                ELSE NULL
            END AS puntaje_compuesto,
            CASE
                WHEN partidas_jugadas < :min_partidas_kpi1 THEN 'MUESTRA INSUFICIENTE'
                ELSE 'MINIMO DE MUESTRA ALCANZADO'
            END AS estado_muestra,
            CASE
                WHEN partidas_jugadas < :min_partidas_kpi1 THEN NULL
                ELSE winrate_pct > 55.0
            END AS cumple_meta,
            CURRENT_TIMESTAMP
        FROM indicadores;
    """)

    # KPI 2: una fila por bloque de 4 horas local de Chile; las muestras pequeñas no reciben
    # recomendación y el winrate horario se compara con el global del jugador.
    sql_kpi2 = text("""
        WITH winrate_global AS (
            SELECT
                puuid,
                (SUM(CASE WHEN victoria THEN 1 ELSE 0 END)::NUMERIC / COUNT(*)) * 100 AS winrate_global_pct
            FROM dw.fact_partidas
            WHERE queue_id = 420
            GROUP BY puuid
        ),
        por_bloque AS (
            SELECT
                f.puuid,
                j.nombre_completo AS nombre_jugador,
                t.bloque_horario,
                COUNT(*)::INT AS partidas_jugadas,
                SUM(CASE WHEN f.victoria THEN 1 ELSE 0 END)::INT AS victorias,
                (SUM(CASE WHEN f.victoria THEN 1 ELSE 0 END)::NUMERIC / COUNT(*)) * 100 AS winrate_pct
            FROM dw.fact_partidas f
            JOIN dw.dim_tiempo t ON f.id_tiempo = t.id_tiempo
            JOIN dw.dim_jugador j ON f.puuid = j.puuid
            WHERE f.queue_id = 420
            GROUP BY f.puuid, j.nombre_completo, t.bloque_horario
        )
        INSERT INTO mart.kpi_02_winrate_horario (
            puuid, nombre_jugador, bloque_horario, partidas_jugadas, victorias,
            winrate_pct, recomendacion_gestion, fecha_calculo
        )
        SELECT
            h.puuid,
            h.nombre_jugador,
            h.bloque_horario,
            h.partidas_jugadas,
            h.victorias,
            ROUND(h.winrate_pct, 2),
            CASE
                WHEN h.partidas_jugadas < :min_partidas_kpi2 THEN 'MUESTRA INSUFICIENTE'
                WHEN h.winrate_pct > 50.0 AND h.winrate_pct > g.winrate_global_pct THEN 'FRANJA FAVORABLE EN MUESTRA'
                WHEN h.winrate_pct > g.winrate_global_pct THEN 'SOBRE PROMEDIO PERSONAL'
                WHEN h.winrate_pct < g.winrate_global_pct THEN 'BAJO PROMEDIO PERSONAL'
                WHEN h.winrate_pct > 50.0 THEN 'SOBRE 50%, SIMILAR AL GLOBAL'
                ELSE 'SIMILAR AL PROMEDIO GLOBAL'
            END,
            CURRENT_TIMESTAMP
        FROM por_bloque h
        JOIN winrate_global g ON h.puuid = g.puuid;
    """)

    # KPI 3: factores por minuto donde corresponde, KDA agregado por rol y
    # normalización individual de cada factor a [0,1] antes de la nota 1–7.
    # JG usa dragones/barones asegurados por partida como aproximación individual.
    sql_kpi3 = text("""
        WITH metricas_rol AS (
            SELECT
                f.puuid,
                j.nombre_completo AS nombre_jugador,
                f.rol,
                COUNT(*)::INT AS partidas_jugadas,
                AVG(f.dano_campeones::NUMERIC / NULLIF(f.duracion_min, 0)) AS dpm,
                AVG(f.dano_torres::NUMERIC / NULLIF(f.duracion_min, 0)) AS torres_min,
                AVG(f.oro::NUMERIC / NULLIF(f.duracion_min, 0)) AS gpm,
                AVG(f.objetivos_neutrales::NUMERIC) AS objetivos_epicos_por_partida,
                AVG(f.vision::NUMERIC / NULLIF(f.duracion_min, 0)) AS vision_min,
                (SUM(f.asesinatos + f.asistencias)::NUMERIC / GREATEST(SUM(f.muertes), 1)) AS kda_periodo
            FROM dw.fact_partidas f
            JOIN dw.dim_jugador j ON f.puuid = j.puuid
            WHERE f.queue_id = 420
            GROUP BY f.puuid, j.nombre_completo, f.rol
        ),
        factores AS (
            SELECT
                *,
                CASE
                    WHEN rol = 'TOP' THEN LEAST(1.0, GREATEST(0.0, dpm / 600.0))
                    WHEN rol = 'JUNGLE' THEN CASE WHEN kda_periodo IS NULL THEN NULL ELSE LEAST(1.0, GREATEST(0.0, kda_periodo / 4.0)) END
                    WHEN rol = 'MIDDLE' THEN CASE WHEN kda_periodo IS NULL THEN NULL ELSE LEAST(1.0, GREATEST(0.0, kda_periodo / 4.0)) END
                    WHEN rol IN ('BOTTOM', 'ADC') THEN LEAST(1.0, GREATEST(0.0, dpm / 750.0))
                    WHEN rol IN ('UTILITY', 'SUPPORT') THEN CASE WHEN kda_periodo IS NULL THEN NULL ELSE LEAST(1.0, GREATEST(0.0, kda_periodo / 4.0)) END
                    ELSE CASE WHEN kda_periodo IS NULL THEN NULL ELSE LEAST(1.0, GREATEST(0.0, kda_periodo / 3.5)) END
                END AS factor_1,
                CASE
                    WHEN rol = 'TOP' THEN LEAST(1.0, GREATEST(0.0, torres_min / 150.0))
                    WHEN rol = 'JUNGLE' THEN LEAST(1.0, GREATEST(0.0, objetivos_epicos_por_partida / 1.0))
                    WHEN rol = 'MIDDLE' THEN LEAST(1.0, GREATEST(0.0, dpm / 700.0))
                    WHEN rol IN ('BOTTOM', 'ADC') THEN LEAST(1.0, GREATEST(0.0, gpm / 450.0))
                    WHEN rol IN ('UTILITY', 'SUPPORT') THEN LEAST(1.0, GREATEST(0.0, vision_min / 2.0))
                    ELSE LEAST(1.0, GREATEST(0.0, dpm / 650.0))
                END AS factor_2
            FROM metricas_rol
        ),
        puntaje_calculado AS (
            SELECT
                *,
                CASE
                    WHEN partidas_jugadas < :min_partidas_kpi3 OR factor_1 IS NULL OR factor_2 IS NULL THEN NULL
                    ELSE ROUND((1.0 + 6.0 * ((factor_1 + factor_2) / 2.0))::NUMERIC, 1)
                END AS nota_final
            FROM factores
        )
        INSERT INTO mart.kpi_03_calificacion_rol (
            puuid, nombre_jugador, rol, partidas_jugadas, dpm_promedio, gpm_promedio,
            vision_min_promedio, nota_escala_1_a_7, estado_rendimiento, fecha_calculo
        )
        SELECT
            puuid,
            nombre_jugador,
            rol,
            partidas_jugadas,
            ROUND(dpm::NUMERIC, 2),
            ROUND(gpm::NUMERIC, 2),
            ROUND(vision_min::NUMERIC, 2),
            nota_final,
            CASE
                WHEN partidas_jugadas < :min_partidas_kpi3 THEN 'MUESTRA INSUFICIENTE'
                WHEN nota_final IS NULL THEN 'METRICAS INSUFICIENTES'
                WHEN nota_final > 5.0 THEN 'SUPERA META'
                ELSE 'NO SUPERA META'
            END,
            CURRENT_TIMESTAMP
        FROM puntaje_calculado;
    """)

    # KPI 4: actividad por fecha local, sin interpretar la alerta como diagnóstico.
    sql_kpi4 = text("""
        INSERT INTO mart.kpi_04_control_actividad_diaria (
            puuid, nombre_jugador, fecha, partidas_en_el_dia, horas_jugadas_dia,
            winrate_del_dia, alerta_sobrecarga, fecha_calculo
        )
        SELECT
            f.puuid,
            j.nombre_completo AS nombre_jugador,
            t.fecha,
            COUNT(*)::INT AS partidas_en_el_dia,
            ROUND((SUM(f.duracion_min) / 60.0)::NUMERIC, 2) AS horas_jugadas_dia,
            CASE
                WHEN COUNT(*) >= 10 THEN
                    ROUND((SUM(CASE WHEN f.victoria THEN 1 ELSE 0 END)::NUMERIC / COUNT(*)) * 100, 2)
                ELSE NULL
            END AS winrate_del_dia,
            (COUNT(*) >= 7) AS alerta_sobrecarga,
            CURRENT_TIMESTAMP
        FROM dw.fact_partidas f
        JOIN dw.dim_tiempo t ON f.id_tiempo = t.id_tiempo
        JOIN dw.dim_jugador j ON f.puuid = j.puuid
        WHERE f.queue_id = 420
        GROUP BY f.puuid, j.nombre_completo, t.fecha;
    """)

    # KPI 5: meta observado en la muestra; bajo 10 apariciones no se etiqueta
    # el resultado ni como dominante ni como bajo rendimiento/OTP.
    sql_kpi5 = text("""
        WITH agregados AS (
            SELECT
                f.campeon,
                f.rol,
                f.parche,
                COUNT(*)::INT AS partidas_totales,
                SUM(CASE WHEN f.victoria THEN 1 ELSE 0 END)::INT AS victorias,
                SUM(f.asesinatos)::BIGINT AS asesinatos,
                SUM(f.muertes)::BIGINT AS muertes,
                SUM(f.asistencias)::BIGINT AS asistencias
            FROM dw.fact_partidas f
            WHERE f.queue_id = 420
            GROUP BY f.campeon, f.rol, f.parche
        ),
        indicadores AS (
            SELECT
                *,
                ROUND((victorias::NUMERIC / partidas_totales) * 100, 2) AS winrate_global_pct,
                ROUND(((asesinatos + asistencias)::NUMERIC / GREATEST(muertes, 1)), 2) AS kda_global
            FROM agregados
        )
        INSERT INTO mart.kpi_05_tierlist_meta_vs_otp (
            campeon, rol, parche, partidas_totales, winrate_global_pct, kda_global,
            clasificacion_tier, fecha_calculo
        )
        SELECT
            campeon,
            rol,
            parche,
            partidas_totales,
            winrate_global_pct,
            kda_global,
            CASE
                WHEN partidas_totales < :min_partidas_kpi5 THEN 'MUESTRA INSUFICIENTE'
                WHEN winrate_global_pct > 52.0 THEN 'DESTACADO EN LA MUESTRA'
                ELSE 'NO SUPERA UMBRAL'
            END,
            CURRENT_TIMESTAMP
        FROM indicadores;
    """)

    # Los marts son resultados derivados: reconstruirlos evita conservar filas
    # antiguas que ya no cumplen los mínimos o que venían de otras colas.
    with engine.begin() as conn:
        for tabla in (
            "mart.kpi_01_mejores_campeones",
            "mart.kpi_02_winrate_horario",
            "mart.kpi_03_calificacion_rol",
            "mart.kpi_04_control_actividad_diaria",
            "mart.kpi_05_tierlist_meta_vs_otp",
        ):
            conn.execute(text(f"DELETE FROM {tabla};"))

        resultados = [
            conn.execute(sql_kpi1, {"min_partidas_kpi1": min_partidas_kpi1}),
            conn.execute(sql_kpi2, {"min_partidas_kpi2": min_partidas_kpi2}),
            conn.execute(sql_kpi3, {"min_partidas_kpi3": min_partidas_kpi3}),
            conn.execute(sql_kpi4),
            conn.execute(sql_kpi5, {"min_partidas_kpi5": min_partidas_kpi5}),
        ]
        filas_mart = sum(resultado.rowcount for resultado in resultados)

    logger.info(f"[MART KPIS] Recalculados los cinco indicadores. Filas: {filas_mart}.")
    return filas_mart


def calcular_porcentaje_nulos_mart(engine=None):
    """
    Calcula el porcentaje de filas en las 5 tablas de mart cuyos campos analíticos
    principales quedaron en NULL (por ejemplo, al no alcanzar el mínimo de muestra).
    Permite auditar dag_03_calculo_kpis con una fórmula verificable desde SQL.
    """
    engine = engine or get_db_engine()
    sql = text("""
        WITH resumen AS (
            SELECT
                COUNT(*)::INT AS total_filas,
                COUNT(*) FILTER (
                    WHERE puntaje_compuesto IS NULL OR cumple_meta IS NULL OR kda_promedio IS NULL
                )::INT AS filas_con_nulos
            FROM mart.kpi_01_mejores_campeones
            UNION ALL
            SELECT
                COUNT(*)::INT AS total_filas,
                0::INT AS filas_con_nulos
            FROM mart.kpi_02_winrate_horario
            UNION ALL
            SELECT
                COUNT(*)::INT AS total_filas,
                COUNT(*) FILTER (WHERE nota_escala_1_a_7 IS NULL)::INT AS filas_con_nulos
            FROM mart.kpi_03_calificacion_rol
            UNION ALL
            SELECT
                COUNT(*)::INT AS total_filas,
                COUNT(*) FILTER (WHERE winrate_del_dia IS NULL)::INT AS filas_con_nulos
            FROM mart.kpi_04_control_actividad_diaria
            UNION ALL
            SELECT
                COUNT(*)::INT AS total_filas,
                COUNT(*) FILTER (WHERE kda_global IS NULL)::INT AS filas_con_nulos
            FROM mart.kpi_05_tierlist_meta_vs_otp
        )
        SELECT
            CASE
                WHEN COALESCE(SUM(total_filas), 0) = 0 THEN 0.0
                ELSE ROUND((SUM(filas_con_nulos)::NUMERIC / SUM(total_filas)) * 100, 2)
            END AS pct_nulos
        FROM resumen;
    """)
    with engine.connect() as conn:
        return float(conn.execute(sql).scalar() or 0.0)
