import time
from datetime import datetime, timedelta
from airflow.decorators import dag, task
from sqlalchemy import text

from etl_lol_utils import (
    get_db_engine,
    calcular_kpis_mart,
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


@dag(
    dag_id="dag_03_calculo_kpis",
    description="Cálculo SQL de los 5 Indicadores de Gestión en el esquema mart",
    schedule=None,  # Disparado por dag_01 o dag_02 mediante TriggerDagRunOperator
    start_date=datetime(2026, 1, 1),
    catchup=False,
    default_args=default_args,
    tags=["lol", "mart", "kpis", "analytics"]
)
def calculo_kpis_etl():

    @task
    def verificar_datos_dw():
        """Verifica la cantidad de hechos en dw.fact_partidas antes de calcular indicadores."""
        engine = get_db_engine()
        with engine.connect() as conn:
            res = conn.execute(text("SELECT COUNT(*) FROM dw.fact_partidas;"))
            total_hechos = res.scalar() or 0

        return int(total_hechos)

    @task
    def calcular_kpis_mart_task(total_hechos: int):
        """Reconstruye los 5 KPIs a partir de los hechos válidos del DW."""
        t_inicio = time.time()
        if total_hechos == 0:
            return {
                "total_hechos": 0,
                "filas_kpis": 0,
                "t_inicio": t_inicio
            }
        filas_actualizadas = calcular_kpis_mart(
            min_partidas_kpi1=3,
            min_partidas_kpi1_adecuada=5,
            min_partidas_kpi2=10,
            min_partidas_kpi3=10,
            min_partidas_kpi5=10,
        )
        return {
            "total_hechos": total_hechos,
            "filas_kpis": filas_actualizadas,
            "t_inicio": t_inicio
        }

    @task
    def registrar_auditoria_task(info_kpis: dict, **context):
        """Registra la auditoría del cálculo en public.etl_audit."""
        duracion = time.time() - info_kpis.get("t_inicio", time.time())
        registrar_auditoria(
            dag_name=context["dag"].dag_id,
            run_id=context["run_id"],
            filas_leidas=info_kpis.get("total_hechos", 0),
            filas_cargadas=info_kpis.get("filas_kpis", 0),
            porcentaje_nulos=0.0,
            duracion_seg=duracion,
            estado="SUCCESS"
        )
        return True

    # Grafo
    verif = verificar_datos_dw()
    calc = calcular_kpis_mart_task(verif)
    registrar_auditoria_task(calc)


dag_instancia = calculo_kpis_etl()
