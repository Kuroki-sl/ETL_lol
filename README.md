 Apache Airflow 3.3.2 (Docker), PostgreSQL, Python 3.x, Riot Games API (Account-V1, Summoner-V4, League-V4, Match-V5).

---

## Estructura del Proyecto

```text
proyecto_etl_lol/
├── dags/
│   ├── etl_lol_utils.py            # Módulos Python reutilizables (Extract, Transform, Calidad, Load, Audit)
│   ├── dag_00_pipeline_completo.py # DAG Maestro: Orquesta la ejecución secuencial ordenada (01 -> 02 -> 03)
│   ├── dag_01_perfil_jugador.py    # DAG 1: Perfil y Clasificación de Jugadores (Account-V1, Summoner-V4, League-V4)
│   ├── dag_02_partidas_jugador.py  # DAG 2: Historial y Telemetría de Partidas (Match-V5)
│   └── dag_03_calculo_kpis.py      # DAG 3: Cálculo SQL de los 5 Indicadores en capa mart
├── sql/
│   └── 01_init_db.sql              # DDL (Esquemas raw, staging, dw, mart y tabla public.etl_audit)
├── .env.example                    # Plantilla de variables de entorno (sin secretos)
├── .gitignore                      # Exclusión de archivos sensibles (.env), logs y caché
├── Dockerfile                      # Imagen Airflow extendida con librerías Python requeridas
├── docker-compose.yaml             # Definición del clúster de servicios para Airflow en Docker
└── README.md                       # Documentación técnica y guía de reproducción
```

---

## Guía de Reproducción Paso a Paso

### 1. Inicializar la Base de Datos en PostgreSQL
1. Abre DBeaver, pgAdmin o tu cliente PostgreSQL conectado a `localhost:5432`.
2. Crea una base de datos llamada `gestion_lol` (o la que configures en tu archivo `.env`).
3. Ejecuta el script DDL completo:
   ```text
   sql/01_init_db.sql
   ```
4. Comprueba que se crearon los esquemas `raw`, `staging`, `dw`, `mart` y la tabla `public.etl_audit`.

### 2. Configurar Variables de Entorno
1. Copia el archivo `.env.example` y renómbralo a `.env`:
2. Completa `.env` con tus credenciales locales:
   ```env
   AIRFLOW_UID=50000
   PGHOST=host.docker.internal
   PGPORT=5432
   PGDATABASE=gestion_lol
   PGUSER=postgres
   PGPASSWORD=tu_contrasena_postgres
   RIOT_API_KEY=RGAPI-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
   RIOT_API_BASE_AMERICAS=https://americas.api.riotgames.com
   RIOT_API_BASE_LAS=https://la2.api.riotgames.com
   ```

### 3. Levantar Apache Airflow con Docker
Desde una terminal PowerShell en la carpeta `proyecto_etl_lol`:

```powershell
# 1. Construir la imagen con las dependencias Python
docker compose build

# 2. Inicializar la base de datos interna de Airflow y crear usuario admin
docker compose up airflow-init

# 3. Levantar los servicios en segundo plano
docker compose up -d

# 4. Verificar que todos los contenedores estén saludables ('healthy')
docker compose ps
```

Accede a la interfaz web de Airflow:  
**URL:** [http://localhost:8080](http://localhost:8080)  
**Usuario:** `airflow` | **Contraseña:** `airflow`

### 4. Configurar Variables en la UI de Airflow (Admin -> Variables)
Para cumplir con los estándares de seguridad y flexibilidad de la rúbrica:
* `riot_api_key`: Tu clave activa de Riot Games (`RGAPI-...`).
* `riot_api_base_americas`: `https://americas.api.riotgames.com`
* `riot_api_base_las`: `https://la2.api.riotgames.com`
* *(Opcional)* `riot_target_players`: Lista JSON personalizada de jugadores a monitorear:
  ```json
  [
    {"gameName": "Agusbob55555", "tagLine": "Yuyos"},
    {"gameName": "Tonoto", "tagLine": "AXEL"},
    {"gameName": "Unforgiven Teemo", "tagLine": "3243"}
  ]
  ```

---

## Ejecución de los Pipelines ETL

Los DAGs pueden ejecutarse de dos maneras:

### A. Ejecución Completa y Ordenada (Recomendada)
Dispara el **DAG Maestro**:
* **`dag_00_pipeline_completo`**: Ejecuta secuencialmente con un solo clic:
  1. `dag_01_perfil_jugador` (espera a que termine exitosamente).
  2. `dag_02_partidas_jugador` (espera a que termine exitosamente).
  3. `dag_03_calculo_kpis` (calcula y actualiza los 5 KPIs en `mart`).

### B. Ejecución Individual de DAGs
Cada DAG mantiene total independencia y tolerancia a fallas:
* **`dag_01_perfil_jugador`**: Sincroniza cuentas y ligas hacia `dw.dim_jugador` (Schedule diario: `0 6 * * *`).
* **`dag_02_partidas_jugador`**: Descarga partidas nuevas, filtra remakes y sincroniza `dw.fact_partidas` y `dw.dim_tiempo` (Schedule cada 6h: `0 */6 * * *`).
* **`dag_03_calculo_kpis`**: Ejecuta el cómputo analítico SQL sobre `mart`.

---

## Arquitectura del Pipeline y Capas de Datos

* **Capa `raw`:** Ingesta fiel de los payloads JSON de Riot Games junto con timestamp de extracción (`raw_perfil_jugador`, `raw_partidas`).
* **Capa `staging`:** Limpieza, tipado fuerte, filtrado de partidas *remake* (< 5 min), cálculo de métricas básicas y normalización *snake_case* (`stg_jugador`, `stg_partidas`).
* **Capa `dw` (Modelo Estrella):** 
  * Dimensiones: `dw.dim_jugador`, `dw.dim_tiempo` (bloques horarios de 4 horas).
  * Tabla de Hechos: `dw.fact_partidas` (idempotencia garantizada con `ON CONFLICT DO UPDATE`).
* **Capa `mart` (Indicadores de Gestión / KPIs):**
  1. `mart.kpi_01_mejores_campeones`: Winrate y KDA por jugador, campeón y rol (meta competitiva).
  2. `mart.kpi_02_winrate_horario`: Eficiencia competitiva por bloque horario y recomendación de gestión.
  3. `mart.kpi_03_calificacion_rol`: Nota ponderada en escala chilena (1.0 a 7.0) por rol.
  4. `mart.kpi_04_control_actividad_diaria`: Volumen diario de horas/partidas y alerta de fatiga/sobrecarga ($\ge 7$ partidas).
  5. `mart.kpi_05_tierlist_meta_vs_otp`: Clasificación de campeones (*Meta Dominante* vs. *OTP / Nicho*).
* **Trazabilidad y Auditoría:** `public.etl_audit` registra DAG, run_id, fecha, filas leídas, filas cargadas, porcentaje de nulos/inválidos, duración y detalle de excepciones (`on_failure_callback`).

---

## Consultas de Verificación en PostgreSQL

```sql
-- 1. Registro de trazabilidad y auditoría
SELECT * FROM public.etl_audit ORDER BY id_ejecucion DESC LIMIT 10;

-- 2. Conteo de hechos en el Data Warehouse
SELECT COUNT(*) AS total_partidas FROM dw.fact_partidas;

-- 3. Consulta de los 5 Indicadores
SELECT * FROM mart.kpi_01_mejores_campeones;
SELECT * FROM mart.kpi_02_winrate_horario;
SELECT * FROM mart.kpi_03_calificacion_rol;
SELECT * FROM mart.kpi_04_control_actividad_diaria;
SELECT * FROM mart.kpi_05_tierlist_meta_vs_otp;
```