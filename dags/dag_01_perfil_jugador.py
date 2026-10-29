import time
import json
from datetime import datetime, timedelta
from airflow.decorators import dag, task
from airflow.models import Variable

from etl_lol_utils import (
    DEFAULT_AMERICAS_URL,
    DEFAULT_LAS_URL,
    validar_estado_api,
    extract_perfiles_riot,
    transform_and_load_staging_jugador,
    load_dw_dim_jugador,
    registrar_auditoria,
    on_dag_failure_callback
)

default_args = {
    "owner": "equipo_lol_analytics",
    "retries": 3,
    "retry_delay": timedelta(seconds=20),
    "execution_timeout": timedelta(minutes=10),
    "on_failure_callback": on_dag_failure_callback,
}

#jugadores por defecto si no estan definidos en Airflow Variables (Challengers activos LAS)
DEFAULT_TARGET_PLAYERS = [
    {"gameName": "Agusbob55555", "tagLine": "Yuyos"},
    {"gameName": "Tonoto", "tagLine": "AXEL"},
    {"gameName": "Unforgiven Teemo", "tagLine": "3243"}
]


@dag(
    dag_id="dag_01_perfil_jugador",
    description="ETL para extraer perfil y liga de jugadores competitivos y cargar en dw.dim_jugador",
    schedule="0 6 * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    default_args=default_args,
    tags=["lol", "perfil", "esports"]
)
def perfil_jugador_etl():

    @task
    def validar_api_riot():
        """Valida conectividad y clave de Riot antes de proceder (Health Check)."""
        americas_url = Variable.get("riot_api_base_americas", default_var=DEFAULT_AMERICAS_URL)
        api_key = Variable.get("riot_api_key", default_var=None)
        validar_estado_api(americas_url, api_key)
        return True

    @task
    def extraer_perfiles_raw(valido: bool):
        """Consume Account-V1, Summoner-V4 y League-V4 e inserta en raw.raw_perfil_jugador."""
        americas_url = Variable.get("riot_api_base_americas", default_var=DEFAULT_AMERICAS_URL)
        las_url = Variable.get("riot_api_base_las", default_var=DEFAULT_LAS_URL)
        api_key = Variable.get("riot_api_key", default_var=None)

        players_json = Variable.get("riot_target_players", default_var=None)
        if players_json:
            target_players = json.loads(players_json)
        else:
            target_players = DEFAULT_TARGET_PLAYERS

        t_inicio = time.time()
        cargadas = extract_perfiles_riot(
            target_players=target_players,
            api_key=api_key,
            americas_url=americas_url,
            las_url=las_url
        )
        return {"filas_raw": cargadas, "t_inicio": t_inicio, "total_esperados": len(target_players)}

    @task
    def transformar_staging_jugador(info_extract: dict):
        """Limpia y normaliza datos crudos hacia staging.stg_jugador."""
        stg_count, pct_nulos = transform_and_load_staging_jugador()
        return {
            "filas_staging": stg_count,
            "pct_nulos": pct_nulos,
            "t_inicio": info_extract["t_inicio"],
            "filas_raw": info_extract["filas_raw"],
            "total_esperados": info_extract["total_esperados"]
        }

    @task
    def validar_calidad_jugador(info_stg: dict):
        """Verifica que el porcentaje de nulos no supere el umbral admisible (Rúbrica)."""
        pct_nulos = info_stg.get("pct_nulos", 0.0)
        if pct_nulos > 40.0:
            raise ValueError(f"Falla de calidad: {pct_nulos}% de nulos en campos de jugador excede umbral (40%).")
        return info_stg

    @task
    def cargar_dw_dim_jugador_task(info_calidad: dict):
        """Carga idempotente en dw.dim_jugador."""
        dw_filas = load_dw_dim_jugador()
        info_calidad["dw_filas"] = dw_filas
        return info_calidad

    @task
    def registrar_auditoria_task(info_final: dict, **context):
        """Registra métricas en public.etl_audit."""
        duracion = time.time() - info_final.get("t_inicio", time.time())
        filas_leidas = max(
            info_final.get("filas_staging", 0),
            info_final.get("filas_raw", 0)
        )
        registrar_auditoria(
            dag_name=context["dag"].dag_id,
            run_id=context["run_id"],
            filas_leidas=filas_leidas,
            filas_cargadas=info_final.get("dw_filas", 0),
            porcentaje_nulos=info_final.get("pct_nulos", 0.0),
            duracion_seg=duracion,
            estado="SUCCESS"
        )
        return True

    #definicion del grafo aciclico dirigido
    val = validar_api_riot()
    ext = extraer_perfiles_raw(val)
    stg = transformar_staging_jugador(ext)
    cal = validar_calidad_jugador(stg)
    dw_load = cargar_dw_dim_jugador_task(cal)
    registrar_auditoria_task(dw_load)


dag_instancia = perfil_jugador_etl()
