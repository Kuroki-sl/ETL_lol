from datetime import datetime, timedelta
from airflow.decorators import dag
from airflow.operators.trigger_dagrun import TriggerDagRunOperator

default_args = {
    "owner": "equipo_lol_analytics",
    "retries": 1,
    "retry_delay": timedelta(seconds=15),
    "execution_timeout": timedelta(minutes=30),
}


@dag(
    dag_id="dag_00_pipeline_completo",
    description="DAG Maestro: Orquesta la ejecución secuencial ordenada (DAG 01 -> DAG 02 -> DAG 03)",
    schedule=None,  # Ejecución bajo demanda (Trigger manual) o programada según necesidad
    start_date=datetime(2026, 1, 1),
    catchup=False,
    default_args=default_args,
    tags=["lol", "master", "pipeline", "orquestador"]
)
def pipeline_completo_orquestador():

    # 1. Ejecutar Perfil y Clasificación de Jugadores (espera hasta finalizar con éxito)
    ejecutar_perfil = TriggerDagRunOperator(
        task_id="01_ejecutar_perfil_jugador",
        trigger_dag_id="dag_01_perfil_jugador",
        wait_for_completion=True,
        poke_interval=10,
        reset_dag_run=True
    )

    # 2. Ejecutar Historial y Telemetría de Partidas (espera hasta finalizar con éxito)
    ejecutar_partidas = TriggerDagRunOperator(
        task_id="02_ejecutar_partidas_jugador",
        trigger_dag_id="dag_02_partidas_jugador",
        wait_for_completion=True,
        poke_interval=10,
        reset_dag_run=True
    )

    # 3. Ejecutar Cálculo Analítico de los 5 KPIs en Mart (espera hasta finalizar con éxito)
    ejecutar_kpis = TriggerDagRunOperator(
        task_id="03_ejecutar_calculo_kpis",
        trigger_dag_id="dag_03_calculo_kpis",
        wait_for_completion=True,
        poke_interval=10,
        reset_dag_run=True
    )

    # Flujo de ejecución estrictamente secuencial y ordenado
    ejecutar_perfil >> ejecutar_partidas >> ejecutar_kpis


dag_instancia = pipeline_completo_orquestador()
