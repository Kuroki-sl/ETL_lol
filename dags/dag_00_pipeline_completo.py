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

    # 1. Ejecutar Perfil y Clasificación de Jugadores (Account-V1, Summoner-V4, League-V4)
    ejecutar_perfil = TriggerDagRunOperator(
        task_id="01_ejecutar_perfil_jugador",
        trigger_dag_id="dag_01_perfil_jugador",
        wait_for_completion=True,
        poke_interval=10,
        reset_dag_run=True
    )

    # 2. Ejecutar Historial y Telemetría de Partidas (Match-V5)
    # Aislamiento de fuentes (Pauta / Rúbrica): trigger_rule=ALL_DONE permite que la extracción
    # de partidas continúe incluso si la fuente de perfiles falló (ej. error 403 o rate limit en Account/League),
    # garantizando el procesamiento de fuentes independientes sin detener el flujo global.
    # conf={"skip_trigger_kpis": True} evita disparos duplicados hacia dag_03, ya que dag_00 gestiona la tarea 03.
    ejecutar_partidas = TriggerDagRunOperator(
        task_id="02_ejecutar_partidas_jugador",
        trigger_dag_id="dag_02_partidas_jugador",
        conf={"skip_trigger_kpis": True},
        wait_for_completion=True,
        poke_interval=10,
        reset_dag_run=True,
        trigger_rule=TriggerRule.ALL_DONE
    )

    # 3. Ejecutar Cálculo Analítico de los 5 KPIs en Mart
    # trigger_rule=ALL_DONE asegura que los indicadores se recalculen con los hechos consolidados en el Data Warehouse.
    ejecutar_kpis = TriggerDagRunOperator(
        task_id="03_ejecutar_calculo_kpis",
        trigger_dag_id="dag_03_calculo_kpis",
        wait_for_completion=True,
        poke_interval=10,
        reset_dag_run=True,
        trigger_rule=TriggerRule.ALL_DONE
    )

    # Flujo de ejecución tolerante a fallas entre fuentes independientes
    ejecutar_perfil >> ejecutar_partidas >> ejecutar_kpis


dag_instancia = pipeline_completo_orquestador()
