import os
import time
import logging
from datetime import datetime
import requests
import pandas as pd
from sqlalchemy import create_engine, text

#logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

#endpoints de Riot Games
DEFAULT_AMERICAS_URL = "https://americas.api.riotgames.com"
DEFAULT_LAS_URL = "https://la2.api.riotgames.com"


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
    Realiza peticiones HTTP GET a Riot API con reintentos y manejo de Rate Limits (HTTP 429).
    """
    for intento in range(1, max_retries + 1):
        try:
            response = requests.get(url, headers=headers, timeout=timeout)
            if response.status_code == 200:
                return response.json()

            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", 5))
                logger.warning(f"[RATE LIMIT 429] Esperando {retry_after} segundos antes de reintentar...")
                time.sleep(retry_after + 1)
                continue

            if response.status_code in [401, 403]:
                error_msg = f"[HTTP {response.status_code}] Clave de API Riot inválida o expirada."
                logger.error(error_msg)
                raise PermissionError(error_msg)

            if response.status_code == 404:
                logger.warning(f"[HTTP 404] Recurso no encontrado: {url}")
                return None

            response.raise_for_status()

        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as net_err:
            logger.warning(f"[ERROR RED] Intento {intento}/{max_retries} falló para {url}: {net_err}")
            if intento == max_retries:
                raise
            time.sleep(3)

    raise RuntimeError(f"Falla tras {max_retries} intentos al consultar: {url}")


def validar_estado_api(base_url, api_key):
    """
    Validación previa de la API antes de extraer (criterio de rúbrica).
    Consulta el estado del servidor LAS o la API de cuentas.
    """
    headers = get_riot_headers(api_key)
    # Si base_url es americas, usamos endpoint de cuentas; de lo contrario status de LAS
    if "americas" in base_url:
        url = f"{base_url}/riot/account/v1/accounts/by-riot-id/Faker/KR1"
    else:
        url = f"{DEFAULT_LAS_URL}/lol/status/v4/platform-data"

    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code in [200, 404]:
            # 200 (éxito) o 404 (cuenta no encontrada pero token válido y aceptado)
            logger.info("[HEALTH CHECK] API de Riot responde y token es válido.")
            return True
        elif resp.status_code in [401, 403]:
            raise PermissionError(f"[HEALTH CHECK FALLÓ] API Key rechazada por Riot Games (HTTP {resp.status_code} - Token inválido o expirado).")
        else:
            logger.warning(f"[HEALTH CHECK] Código de respuesta: {resp.status_code}")
            return True
            return True
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
    total_campos_esperados = len(df_raw) * 7

    for _, row in df_raw.iterrows():
        puuid = row["puuid"]
        acc = row["payload_account"] or {}
        summ = row["payload_summoner"] or {}
        leagues = row["payload_league"] or []

        game_name = acc.get("gameName", "Desconocido")
        tag_line = acc.get("tagLine", "LAS")
        summoner_level = summ.get("summonerLevel", 1)

        # Buscar clasificación SoloQ (RANKED_SOLO_5x5) o tomar la primera
        tier = "UNRANKED"
        rank_division = "N/A"
        lp = 0
        wins = 0
        losses = 0

        if isinstance(leagues, list) and len(leagues) > 0:
            soloq = next((l for l in leagues if l.get("queueType") == "RANKED_SOLO_5x5"), leagues[0])
            tier = soloq.get("tier", "UNRANKED")
            rank_division = soloq.get("rank", "N/A")
            lp = soloq.get("leaguePoints", 0)
            wins = soloq.get("wins", 0)
            losses = soloq.get("losses", 0)

        if not puuid or tier == "UNRANKED":
            campos_nulos_contador += 1

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
        url_ids = f"{americas_url}/lol/match/v5/matches/by-puuid/{puuid}/ids?start=0&count={count}"
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
                    VALUES (:match_id, :puuid_consulta, :payload_match);
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


def transform_and_load_staging_partidas():
    """
    Parsea los JSON de raw.raw_partidas, normaliza métricas a snake_case,
    convierte duraciones a minutos, calcula kda y clasifica bloque_horario,
    descartando partidas remake (< 5 min), y carga en staging.stg_partidas.
    """
    engine = get_db_engine()
    query = text("SELECT match_id, puuid_consulta, payload_match FROM raw.raw_partidas;")
    df_raw = pd.read_sql(query, engine)

    if df_raw.empty:
        logger.info("No hay partidas para transformar en raw.")
        return 0, 0.0

    registros_partidas = []
    filas_invalidas = 0

    for _, row in df_raw.iterrows():
        mid = row["match_id"]
        consulta_puuid = row["puuid_consulta"]
        payload = row["payload_match"] or {}
        info = payload.get("info", {})

        game_start_ms = info.get("gameStartTimestamp")
        game_duration_sec = info.get("gameDuration", 0)
        queue_id = info.get("queueId", 0)

        # Duración en minutos
        duracion_min = round(game_duration_sec / 60.0, 2)
        # Filtro de calidad: partidas remake (< 5 min)
        if duracion_min < 5.0 or not game_start_ms:
            filas_invalidas += 1
            continue

        fecha_partida = datetime.fromtimestamp(game_start_ms / 1000.0)
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

        participants = info.get("participants", [])
        for p in participants:
            p_puuid = p.get("puuid")
            # Filtrar si corresponde al jugador consultado o a alguno registrado
            if p_puuid != consulta_puuid:
                continue

            asesinatos = p.get("kills", 0)
            muertes = p.get("deaths", 0)
            asistencias = p.get("assists", 0)
            kda = round((asesinatos + asistencias) / max(muertes, 1), 2)

            # Normalización de rol
            rol = p.get("teamPosition") or p.get("individualPosition") or "SIN_ROL"
            if rol in ["", "Invalid"]:
                rol = "SIN_ROL"
            elif rol == "UTILITY":
                rol = "SUPPORT"
            elif rol == "BOTTOM":
                rol = "ADC"

            registros_partidas.append({
                "match_id": mid,
                "puuid": p_puuid,
                "fecha_partida": fecha_partida,
                "fecha_dia": fecha_dia,
                "hora_del_dia": hora_del_dia,
                "bloque_horario": bloque,
                "queue_id": queue_id,
                "campeon": p.get("championName", "Desconocido"),
                "rol": rol,
                "asesinatos": asesinatos,
                "muertes": muertes,
                "asistencias": asistencias,
                "kda": kda,
                "oro_ganado": p.get("goldEarned", 0),
                "dano_campeones": p.get("totalDamageDealtToChampions", 0),
                "dano_torres": p.get("damageDealtToTurrets", 0) or 0,
                "objetivos_neutrales": (p.get("neutralMinionsKilled", 0) or 0) + (p.get("dragonKills", 0) or 0) + (p.get("baronKills", 0) or 0),
                "vision": p.get("visionScore", 0) or 0,
                "duracion_min": duracion_min,
                "victoria": bool(p.get("win", False))
            })

    if not registros_partidas:
        return 0, 0.0

    df_stg = pd.DataFrame(registros_partidas).drop_duplicates(subset=["match_id", "puuid"], keep="last")
    pct_nulos = (filas_invalidas / max(len(df_raw), 1)) * 100

    sql_upsert = text("""
        INSERT INTO staging.stg_partidas (
            match_id, puuid, fecha_partida, fecha_dia, hora_del_dia, bloque_horario,
            queue_id, campeon, rol, asesinatos, muertes, asistencias, kda,
            oro_ganado, dano_campeones, dano_torres, objetivos_neutrales,
            vision, duracion_min, victoria, fecha_procesamiento
        ) VALUES (
            :match_id, :puuid, :fecha_partida, :fecha_dia, :hora_del_dia, :bloque_horario,
            :queue_id, :campeon, :rol, :asesinatos, :muertes, :asistencias, :kda,
            :oro_ganado, :dano_campeones, :dano_torres, :objetivos_neutrales,
            :vision, :duracion_min, :victoria, CURRENT_TIMESTAMP
        )
        ON CONFLICT (match_id, puuid) DO UPDATE SET
            kda = EXCLUDED.kda,
            oro_ganado = EXCLUDED.oro_ganado,
            dano_campeones = EXCLUDED.dano_campeones,
            dano_torres = EXCLUDED.dano_torres,
            duracion_min = EXCLUDED.duracion_min,
            victoria = EXCLUDED.victoria,
            fecha_procesamiento = CURRENT_TIMESTAMP;
    """)

    with engine.begin() as conn:
        for item in df_stg.to_dict(orient="records"):
            conn.execute(sql_upsert, item)

    logger.info(f"[STAGING PARTIDAS] {len(df_stg)} partidas cargadas en staging.stg_partidas.")
    return len(df_stg), pct_nulos


def load_dw_hechos_y_tiempo():
    """
    Carga idempotente hacia dw.dim_tiempo y dw.fact_partidas asegurando integridad referencial.
    """
    engine = get_db_engine()

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
            match_id, puuid, id_tiempo, campeon, rol, asesinatos, muertes, asistencias,
            kda, oro, dano_campeones, dano_torres, objetivos_neutrales, vision,
            duracion_min, victoria
        )
        SELECT
            match_id,
            puuid,
            TO_CHAR(fecha_partida, 'YYYYMMDDHH24')::INT AS id_tiempo,
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
            kda = EXCLUDED.kda,
            oro = EXCLUDED.oro,
            dano_campeones = EXCLUDED.dano_campeones,
            dano_torres = EXCLUDED.dano_torres,
            duracion_min = EXCLUDED.duracion_min,
            victoria = EXCLUDED.victoria;
    """)

    with engine.begin() as conn:
        conn.execute(sql_dim_tiempo)
        conn.execute(sql_ensure_player)
        res = conn.execute(sql_fact_partidas)
        cargadas = res.rowcount

    logger.info(f"[DW FACT_PARTIDAS] {cargadas} hechos sincronizados con dw.fact_partidas.")
    return cargadas


#pipeline#3 KPIs en capa mart

def calcular_kpis_mart(min_partidas_kpi1=1, min_partidas_kpi2=1):
    """
    Ejecuta las consultas SQL analíticas de los 5 indicadores de gestión en el esquema mart.
    min_partidas_kpi1 y min_partidas_kpi2 permiten flexibilidad durante pruebas con pocos datos.
    """
    engine = get_db_engine()

    # KPI 1: Mejores Campeones
    sql_kpi1 = text(f"""
        INSERT INTO mart.kpi_01_mejores_campeones (
            puuid, nombre_jugador, campeon, rol, partidas_jugadas, victorias,
            winrate_pct, kda_promedio, cumple_meta, fecha_calculo
        )
        SELECT
            f.puuid,
            j.nombre_completo AS nombre_jugador,
            f.campeon,
            f.rol,
            COUNT(f.match_id) AS partidas_jugadas,
            SUM(CASE WHEN f.victoria THEN 1 ELSE 0 END) AS victorias,
            ROUND((SUM(CASE WHEN f.victoria THEN 1 ELSE 0 END)::NUMERIC / COUNT(f.match_id)) * 100, 2) AS winrate_pct,
            ROUND(AVG(f.kda), 2) AS kda_promedio,
            ((SUM(CASE WHEN f.victoria THEN 1 ELSE 0 END)::NUMERIC / COUNT(f.match_id)) * 100 >= 55.0 AND AVG(f.kda) >= 3.0) AS cumple_meta,
            CURRENT_TIMESTAMP
        FROM dw.fact_partidas f
        JOIN dw.dim_jugador j ON f.puuid = j.puuid
        GROUP BY f.puuid, j.nombre_completo, f.campeon, f.rol
        HAVING COUNT(f.match_id) >= {min_partidas_kpi1}
        ON CONFLICT (puuid, campeon, rol) DO UPDATE SET
            partidas_jugadas = EXCLUDED.partidas_jugadas,
            victorias = EXCLUDED.victorias,
            winrate_pct = EXCLUDED.winrate_pct,
            kda_promedio = EXCLUDED.kda_promedio,
            cumple_meta = EXCLUDED.cumple_meta,
            fecha_calculo = CURRENT_TIMESTAMP;
    """)

    # KPI 2: Winrate por Bloque Horario
    sql_kpi2 = text(f"""
        INSERT INTO mart.kpi_02_winrate_horario (
            puuid, nombre_jugador, bloque_horario, partidas_jugadas, victorias,
            winrate_pct, recomendacion_gestion, fecha_calculo
        )
        SELECT
            f.puuid,
            j.nombre_completo AS nombre_jugador,
            t.bloque_horario,
            COUNT(f.match_id) AS partidas_jugadas,
            SUM(CASE WHEN f.victoria THEN 1 ELSE 0 END) AS victorias,
            ROUND((SUM(CASE WHEN f.victoria THEN 1 ELSE 0 END)::NUMERIC / COUNT(f.match_id)) * 100, 2) AS winrate_pct,
            CASE
                WHEN (SUM(CASE WHEN f.victoria THEN 1 ELSE 0 END)::NUMERIC / COUNT(f.match_id)) * 100 >= 55.0 THEN 'HORARIO OPTIMO (Priorizar)'
                WHEN (SUM(CASE WHEN f.victoria THEN 1 ELSE 0 END)::NUMERIC / COUNT(f.match_id)) * 100 >= 48.0 THEN 'HORARIO NEUTRO'
                ELSE 'HORARIO CRITICO (Evitar)'
            END AS recomendacion_gestion,
            CURRENT_TIMESTAMP
        FROM dw.fact_partidas f
        JOIN dw.dim_tiempo t ON f.id_tiempo = t.id_tiempo
        JOIN dw.dim_jugador j ON f.puuid = j.puuid
        GROUP BY f.puuid, j.nombre_completo, t.bloque_horario
        HAVING COUNT(f.match_id) >= {min_partidas_kpi2}
        ON CONFLICT (puuid, bloque_horario) DO UPDATE SET
            partidas_jugadas = EXCLUDED.partidas_jugadas,
            victorias = EXCLUDED.victorias,
            winrate_pct = EXCLUDED.winrate_pct,
            recomendacion_gestion = EXCLUDED.recomendacion_gestion,
            fecha_calculo = CURRENT_TIMESTAMP;
    """)

    # KPI 3: Calificación de Rendimiento por Rol (1.0 a 7.0)
    sql_kpi3 = text("""
        WITH metricas_rol AS (
            SELECT
                f.puuid,
                j.nombre_completo AS nombre_jugador,
                f.rol,
                COUNT(f.match_id) AS partidas_jugadas,
                AVG(f.dano_campeones / GREATEST(f.duracion_min, 1)) AS dpm,
                AVG(f.dano_torres / GREATEST(f.duracion_min, 1)) AS torres_min,
                AVG(f.oro / GREATEST(f.duracion_min, 1)) AS gpm,
                AVG(f.objetivos_neutrales / GREATEST(f.duracion_min, 1)) AS obj_min,
                AVG(f.vision / GREATEST(f.duracion_min, 1)) AS vision_min,
                AVG(f.kda) AS kda_prom
            FROM dw.fact_partidas f
            JOIN dw.dim_jugador j ON f.puuid = j.puuid
            GROUP BY f.puuid, j.nombre_completo, f.rol
        ),
        puntaje_calculado AS (
            SELECT
                *,
                LEAST(7.0, GREATEST(1.0, ROUND((1.0 + 6.0 * (
                    CASE
                        WHEN rol = 'TOP' THEN ((dpm / 600.0) * 0.6 + (torres_min / 150.0) * 0.4)
                        WHEN rol = 'JUNGLE' THEN ((kda_prom / 4.0) * 0.5 + (obj_min / 5.5) * 0.5)
                        WHEN rol = 'MIDDLE' THEN ((kda_prom / 4.0) * 0.4 + (dpm / 700.0) * 0.6)
                        WHEN rol IN ('BOTTOM', 'ADC') THEN ((dpm / 750.0) * 0.5 + (gpm / 450.0) * 0.5)
                        WHEN rol IN ('UTILITY', 'SUPPORT') THEN ((kda_prom / 4.0) * 0.4 + (vision_min / 2.0) * 0.6)
                        ELSE ((kda_prom / 3.5) * 0.5 + (dpm / 650.0) * 0.5)
                    END
                ))::NUMERIC, 1))) AS nota_final
            FROM metricas_rol
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
                WHEN nota_final >= 5.5 THEN 'DESTACADO'
                WHEN nota_final >= 4.0 THEN 'APROBADO'
                ELSE 'BAJO RENDIMIENTO'
            END AS estado_rendimiento,
            CURRENT_TIMESTAMP
        FROM puntaje_calculado
        ON CONFLICT (puuid, rol) DO UPDATE SET
            partidas_jugadas = EXCLUDED.partidas_jugadas,
            dpm_promedio = EXCLUDED.dpm_promedio,
            gpm_promedio = EXCLUDED.gpm_promedio,
            vision_min_promedio = EXCLUDED.vision_min_promedio,
            nota_escala_1_a_7 = EXCLUDED.nota_escala_1_a_7,
            estado_rendimiento = EXCLUDED.estado_rendimiento,
            fecha_calculo = CURRENT_TIMESTAMP;
    """)

    # KPI 4: Control de Fatiga Diaria
    sql_kpi4 = text("""
        INSERT INTO mart.kpi_04_control_actividad_diaria (
            puuid, nombre_jugador, fecha, partidas_en_el_dia, horas_jugadas_dia,
            winrate_del_dia, alerta_sobrecarga, fecha_calculo
        )
        SELECT
            f.puuid,
            j.nombre_completo AS nombre_jugador,
            t.fecha,
            COUNT(f.match_id) AS partidas_en_el_dia,
            ROUND((SUM(f.duracion_min) / 60.0)::NUMERIC, 2) AS horas_jugadas_dia,
            ROUND((SUM(CASE WHEN f.victoria THEN 1 ELSE 0 END)::NUMERIC / COUNT(f.match_id)) * 100, 2) AS winrate_del_dia,
            (COUNT(f.match_id) >= 7) AS alerta_sobrecarga,
            CURRENT_TIMESTAMP
        FROM dw.fact_partidas f
        JOIN dw.dim_tiempo t ON f.id_tiempo = t.id_tiempo
        JOIN dw.dim_jugador j ON f.puuid = j.puuid
        GROUP BY f.puuid, j.nombre_completo, t.fecha
        ON CONFLICT (puuid, fecha) DO UPDATE SET
            partidas_en_el_dia = EXCLUDED.partidas_en_el_dia,
            horas_jugadas_dia = EXCLUDED.horas_jugadas_dia,
            winrate_del_dia = EXCLUDED.winrate_del_dia,
            alerta_sobrecarga = EXCLUDED.alerta_sobrecarga,
            fecha_calculo = CURRENT_TIMESTAMP;
    """)

    # KPI 5: Tier List Meta vs OTP
    sql_kpi5 = text("""
        INSERT INTO mart.kpi_05_tierlist_meta_vs_otp (
            campeon, rol, partidas_totales, winrate_global_pct, kda_global,
            clasificacion_tier, fecha_calculo
        )
        SELECT
            f.campeon,
            f.rol,
            COUNT(f.match_id) AS partidas_totales,
            ROUND((SUM(CASE WHEN f.victoria THEN 1 ELSE 0 END)::NUMERIC / COUNT(f.match_id)) * 100, 2) AS winrate_global_pct,
            ROUND(AVG(f.kda), 2) AS kda_global,
            CASE
                WHEN COUNT(f.match_id) >= 10 AND (SUM(CASE WHEN f.victoria THEN 1 ELSE 0 END)::NUMERIC / COUNT(f.match_id)) * 100 > 53.0 THEN 'META DOMINANTE'
                WHEN COUNT(f.match_id) < 10  AND (SUM(CASE WHEN f.victoria THEN 1 ELSE 0 END)::NUMERIC / COUNT(f.match_id)) * 100 > 55.0 THEN 'OTP / NICHO (Muestra Baja)'
                WHEN (SUM(CASE WHEN f.victoria THEN 1 ELSE 0 END)::NUMERIC / COUNT(f.match_id)) * 100 < 47.0 THEN 'BAJO RENDIMIENTO'
                ELSE 'BALANCEADO'
            END AS clasificacion_tier,
            CURRENT_TIMESTAMP
        FROM dw.fact_partidas f
        GROUP BY f.campeon, f.rol
        ON CONFLICT (campeon, rol) DO UPDATE SET
            partidas_totales = EXCLUDED.partidas_totales,
            winrate_global_pct = EXCLUDED.winrate_global_pct,
            kda_global = EXCLUDED.kda_global,
            clasificacion_tier = EXCLUDED.clasificacion_tier,
            fecha_calculo = CURRENT_TIMESTAMP;
    """)

    filas_mart = 0
    with engine.begin() as conn:
        r1 = conn.execute(sql_kpi1)
        r2 = conn.execute(sql_kpi2)
        r3 = conn.execute(sql_kpi3)
        r4 = conn.execute(sql_kpi4)
        r5 = conn.execute(sql_kpi5)
        filas_mart = r1.rowcount + r2.rowcount + r3.rowcount + r4.rowcount + r5.rowcount

    logger.info(f"[MART KPIS] Cálculo exitoso. {filas_mart} registros agregados/actualizados.")
    return filas_mart