from datetime import datetime, timedelta
from airflow.decorators import dag
from airflow.operators.trigger_dagrun import TriggerDagRunOperator
from airflow.utils.trigger_rule import TriggerRule

default_args = {
    "owner": "equipo_lol_analytics",
    "retries": 1,
    "retry_delay": timedelta(seconds=15),
    "execution_timeout": timedelta(minutes=90),
}


@dag(
    dag_id="dag_00_pipeline_completo",
    description="DAG Maestro: Orquesta la ejecución secuencial ordenada (DAG 01 -> DAG 02 -> DAG 03) con tolerancia a fallas",
    schedule=None,  # Ejecución bajo demanda (Trigger manual) o programada según necesidad
    start_date=datetime(2026, 1, 1),
    catchup=False,
    default_args=default_args,
    tags=["lol", "master", "pipeline", "orquestador"]
)
def pipeline_completo_orquestador():

    #ejecutar Perfil y clasificacion de jugadores (Account-V1, Summoner-V4, League-V4)
    ejecutar_perfil = TriggerDagRunOperator(
        task_id="01_ejecutar_perfil_jugador",
        trigger_dag_id="dag_01_perfil_jugador",
        wait_for_completion=True,
        poke_interval=10,
        reset_dag_run=True
    )

    #ejecutar historial y Telemetria de partidas (Match-V5)
    #que continue incluso si la fuente de perfiles fallo,
    #garantizando el procesamiento de fuentes independientes sin detener el flujo global.
    ejecutar_partidas = TriggerDagRunOperator(
        task_id="02_ejecutar_partidas_jugador",
        trigger_dag_id="dag_02_partidas_jugador",
        conf={"skip_trigger_kpis": True},
        wait_for_completion=True,
        poke_interval=10,
        reset_dag_run=True,
        trigger_rule=TriggerRule.ALL_DONE
    )

    #ejecutar calculo analitico de los 5 KPIs en Mart
    ejecutar_kpis = TriggerDagRunOperator(
        task_id="03_ejecutar_calculo_kpis",
        trigger_dag_id="dag_03_calculo_kpis",
        wait_for_completion=True,
        poke_interval=10,
        reset_dag_run=True,
        trigger_rule=TriggerRule.ALL_DONE
    )

    #flujo de ejecucion tolerante a fallas entre fuentes independientes
    ejecutar_perfil >> ejecutar_partidas >> ejecutar_kpis


dag_instancia = pipeline_completo_orquestador()
