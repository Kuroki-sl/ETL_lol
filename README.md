# Pipeline ETL de League of Legends (Esports Analytics)

**Asignatura:** INF-522 | **Evaluación 2 (35%)** — Universidad Católica del Maule  
**Stack:** Apache Airflow 3.3.2 (Docker), PostgreSQL, Python 3.x, Riot Games API (Account-V1, Summoner-V4, League-V4, Match-V5).

---

## Estructura del Proyecto

```text
proyecto_etl_lol/
├── dags/
│   ├── etl_lol_utils.py            # Módulos Python (Extract, Transform, Calidad, Load, Audit)
│   ├── dag_01_perfil_jugador.py    # DAG 1: Perfil y Clasificación de Jugadores
│   ├── dag_02_partidas_jugador.py  # DAG 2: Historial y Telemetría de Partidas
│   └── dag_03_calculo_kpis.py      # DAG 3: Cálculo SQL de Indicadores en capa mart
├── sql/
│   └── 01_init_db.sql              # DDL (Esquemas raw, staging, dw, mart y tabla etl_audit)
├── .env.example                    # Plantilla de variables (sin credenciales reales)
├── Dockerfile                      # Imagen Airflow extendida con librerías requeridas
├── docker-compose.yaml             # Definición de servicios para Airflow en Docker
└── README.md                       # Instrucciones de despliegue y reproducción
```

---

## Guía de Reproducción Paso a Paso

### 1. Inicializar la Base de Datos en PostgreSQL
1. Abre DBeaver o tu cliente PostgreSQL preferido conectado a `localhost:5432`.
2. Crea una base de datos llamada `gestion_lol` (o la que definas en tu archivo `.env`).
3. Abre una Query Tool sobre dicha base de datos y ejecuta el script completo:
   ```text
   sql/01_init_db.sql
   ```
4. Comprueba que se crearon los esquemas `raw`, `staging`, `dw`, `mart` y la tabla `public.etl_audit`.

### 2. Configurar Variables de Entorno
1. Copia el archivo `.env.example` y renómbralo a `.env`:
2. Edita `.env` con tus credenciales locales:
   - `PGHOST=host.docker.internal`
   - `PGPORT=5432`
   - `PGDATABASE=gestion_lol`
   - `PGUSER=postgres`
   - `PGPASSWORD=tu_contrasena`
   - `RIOT_API_KEY=RGAPI-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`

### 3. Levantar Apache Airflow con Docker
Desde la terminal PowerShell dentro de la carpeta `proyecto_etl_lol`:

```powershell
# 1. Construir la imagen con las dependencias Python
docker compose build

# 2. Inicializar la base de datos interna de Airflow y crear usuario admin
docker compose up airflow-init

# 3. Levantar los servicios en segundo plano
docker compose up -d

# 4. Verificar que los contenedores estén saludables ('healthy')
docker compose ps
```

Accede a la interfaz web de Airflow en:
`http://localhost:8080` (Usuario: `airflow` | Contraseña: `airflow`).

### 4. Configurar Variables en la UI de Airflow (Admin -> Variables)
Para cumplir con los estándares de seguridad y flexibilidad evaluados en la rúbrica:
- `riot_api_key`: Tu clave de desarrollo de Riot Games (`RGAPI-...`).
- `riot_target_players`: Lista JSON con los jugadores a monitorear:
  ```json
  [
    {"gameName": "Faker", "tagLine": "KR1"},
    {"gameName": "JugadorPrueba", "tagLine": "LAS"}
  ]
  ```
- `riot_api_base_americas`: `https://americas.api.riotgames.com`
- `riot_api_base_las`: `https://la2.api.riotgames.com`

---

## Arquitectura del Pipeline y Modelo Dimensional

- **Capa raw:** Ingesta fiel de los JSON de Riot Games con timestamp de extracción.
- **Capa staging:** Limpieza, tipado fuerte, filtrado de partidas *remake* (< 5 min) y normalización snake_case.
- **Capa dw:** Modelo dimensional estrella con `dw.dim_jugador`, `dw.dim_tiempo` y `dw.fact_partidas` con cargas idempotentes (`ON CONFLICT DO UPDATE`).
- **Capa mart:** 5 Indicadores de gestión y rendimiento competitivo calculados en SQL.
- **Tabla de auditoría:** `public.etl_audit` registra filas leídas, filas cargadas, porcentaje de nulos/errores, tiempo de ejecución y detalle de excepciones.
