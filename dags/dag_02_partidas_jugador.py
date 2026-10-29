import time
import json
from datetime import datetime, timedelta
from airflow.decorators import dag, task
from airflow.models import Variable

from etl_lol_utils import (
    DEFAULT_AMERICAS_URL,
    DEFAULT_TARGET_PLAYERS,
    validar_estado_api,
    extraer_partidas_riot,
    contar_participaciones_raw_partidas,
    transform_and_load_staging_partidas,
    load_dw_hechos_y_tiempo,
    registrar_auditoria,
    on_dag_failure_callback
)

default_args = {
    "owner": "equipo_lol_analytics",
    "retries": 3,
    "retry_delay": timedelta(seconds=20),
    "execution_timeout": timedelta(minutes=60),
    "on_failure_callback": on_dag_failure_callback,
}


@dag(
    dag_id="dag_02_partidas_jugador",
    description="ETL para extraer historial y telemetría Match-V5 y cargar en dw.dim_tiempo y dw.fact_partidas",
    schedule="0 */6 * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    default_args=default_args,
    tags=["lol", "partidas", "telemetria"]
)
def partidas_jugador_etl():

    @task
    def validar_api_match():
        """Valida que la API de partidas y la clave estén activas."""
        americas_url = Variable.get("riot_api_base_americas", default_var=DEFAULT_AMERICAS_URL)
        api_key = Variable.get("riot_api_key", default_var=None)
        validar_estado_api(americas_url, api_key)
        return True

    @task
    def extraer_partidas_raw(valido: bool, **context):
        """
        Descarga los IDs de partidas para los jugadores registrados y sus detalles JSON.
        Permite acotar la muestra y hacer backfill con max_partidas_por_jugador,
        start_time y end_time.
        """
        americas_url = Variable.get("riot_api_base_americas", default_var=DEFAULT_AMERICAS_URL)
        api_key = Variable.get("riot_api_key", default_var=None)
        players_json = Variable.get("riot_target_players", default_var=None)
        target_players = json.loads(players_json) if players_json else DEFAULT_TARGET_PLAYERS
        target_riot_ids = [
            f"{player['gameName']}#{player['tagLine']}"
            for player in target_players
        ]

        # Parámetros pasados en DAG Run (ej. backfill)
        dag_run_conf = context.get("dag_run").conf or {} if context.get("dag_run") else {}
        # count se conserva como alias para DAG Runs creados con la configuración anterior.
        max_partidas_por_jugador = dag_run_conf.get(
            "max_partidas_por_jugador",
            dag_run_conf.get("count", 100)
        )
        start_time = dag_run_conf.get("start_time", None)
        end_time = dag_run_conf.get("end_time", None)

        t_inicio = time.time()
        nuevas_cargadas = extraer_partidas_riot(
            api_key=api_key,
            max_partidas_por_jugador=max_partidas_por_jugador,
            start_time=start_time,
            end_time=end_time,
            americas_url=americas_url,
            riot_ids=target_riot_ids,
        )

        return {"partidas_nuevas": nuevas_cargadas, "t_inicio": t_inicio}

    @task
    def transformar_staging_partidas(info_extract: dict):
        """Parsea JSONs de raw, descarta remakes (< 5m), tipifica y normaliza métricas."""
        stg_count, pct_invalidas = transform_and_load_staging_partidas()
        participaciones_leidas = max(contar_participaciones_raw_partidas(), stg_count)
        return {
            "filas_staging": stg_count,
            "participaciones_leidas": participaciones_leidas,
            "pct_nulos": pct_invalidas,
            "t_inicio": info_extract["t_inicio"],
            "partidas_nuevas": info_extract["partidas_nuevas"]
        }

    @task
    def validar_calidad_partidas(info_stg: dict):
        """Comprueba umbral de calidad antes de sincronizar con el DW."""
        pct = info_stg.get("pct_nulos", 0.0)
        if pct > 50.0:
            raise ValueError(f"Falla de calidad: {pct}% de partidas corruptas o inválidas excede umbral (50%).")
        return info_stg

    @task
    def cargar_dw_hechos_y_tiempo_task(info_cal: dict):
        """Carga idempotente en dw.dim_tiempo y dw.fact_partidas."""
        dw_filas = load_dw_hechos_y_tiempo()
        info_cal["dw_filas"] = dw_filas
        return info_cal

    @task
    def registrar_auditoria_task(info_final: dict, **context):
        """Registra auditoría en public.etl_audit."""
        duracion = time.time() - info_final.get("t_inicio", time.time())
        registrar_auditoria(
            dag_name=context["dag"].dag_id,
            run_id=context["run_id"],
            filas_leidas=info_final.get("participaciones_leidas", info_final.get("partidas_nuevas", 0)),
            filas_cargadas=info_final.get("dw_filas", 0),
            porcentaje_nulos=info_final.get("pct_nulos", 0.0),
            duracion_seg=duracion,
            estado="SUCCESS"
        )
        return True

    # Grafo
    val = validar_api_match()
    ext = extraer_partidas_raw(val)
    stg = transformar_staging_partidas(ext)
    cal = validar_calidad_partidas(stg)
    dw_load = cargar_dw_hechos_y_tiempo_task(cal)
    registrar_auditoria_task(dw_load)


dag_instancia = partidas_jugador_etl()
