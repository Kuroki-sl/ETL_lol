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
│   ├── 01_init_db.sql              # DDL (Esquemas raw, staging, dw, mart y tabla public.etl_audit)
│   └── 02_consulta_kpi_01_jugador.sql # Consulta de recomendación y trazabilidad para HU-01
├── scripts/
│   ├── Backup-GestionLol.ps1        # Exporta solo la base de datos del ETL
│   └── Restore-GestionLol.ps1       # Restaura un respaldo compartido
├── .env.example                    # Plantilla de variables de entorno (sin secretos)
├── .gitignore                      # Exclusión de archivos sensibles (.env), logs y caché
├── Dockerfile                      # Imagen Airflow extendida con librerías Python requeridas
├── docker-compose.yaml             # Definición del clúster de servicios para Airflow en Docker
└── README.md                       # Documentación técnica y guía de reproducción
```

---

## Guía de Reproducción Paso a Paso

### 1. Configurar Variables de Entorno
1. Copia el archivo `.env.example` y renómbralo a `.env`.
2. Cambia `PGPASSWORD` y `RIOT_API_KEY` en `.env`. PostgreSQL se ejecutará en un contenedor propio; no necesitas instalar PostgreSQL ni DBeaver en Windows.
3. Genera una clave Fernet para Airflow en PowerShell, desde la carpeta del proyecto, y guárdala en `.env`:
   ```powershell
   $bytes = [byte[]]::new(32)
   [System.Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
   $key = [Convert]::ToBase64String($bytes).Replace('+','-').Replace('/','_')
   $envPath = (Resolve-Path .env).Path
   $envText = [System.IO.File]::ReadAllText($envPath)
   $envText = [regex]::Replace($envText, '(?m)^FERNET_KEY=.*$', "FERNET_KEY=$key")
   [System.IO.File]::WriteAllText($envPath, $envText, [System.Text.UTF8Encoding]::new($false))
   ```

La configuración esperada queda así:
   ```env
   AIRFLOW_UID=50000
   PGHOST=lol-postgres
   PGPORT=5432
   PGDATABASE=gestion_lol
   PGUSER=postgres
   PGPASSWORD=una_contrasena_local
   FERNET_KEY=clave_generada_en_el_paso_anterior
   RIOT_API_KEY=RGAPI-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
   RIOT_API_BASE_AMERICAS=https://americas.api.riotgames.com
   RIOT_API_BASE_LAS=https://la2.api.riotgames.com
   ```

Al iniciar por primera vez, el contenedor `lol-postgres` crea `gestion_lol` y ejecuta `sql/01_init_db.sql` automáticamente.

### 2. Levantar Apache Airflow con Docker
Desde PowerShell en la carpeta del proyecto:

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

Para abrir una consola SQL dentro de PostgreSQL:
```powershell
docker compose exec lol-postgres psql -U postgres -d gestion_lol
```

Detén los servicios conservando los datos con `docker compose down`. Para borrar también las bases de datos almacenadas por Docker, usa `docker compose down -v`.

### Compartir la base de datos entre integrantes

El volumen de Docker vive en un solo computador y no se sincroniza con Git. Para trabajar los tres con la misma captura usando **Google Drive desde la web**, una persona ejecuta el ETL y sube un respaldo de `gestion_lol`; cada integrante descarga ese archivo y lo restaura en su propio contenedor `lol-postgres`. No hace falta instalar Drive para escritorio.

1. En el computador que tiene los datos, levanta PostgreSQL si no está activo y crea el respaldo:
   ```powershell
   docker compose up -d lol-postgres
   .\scripts\Backup-GestionLol.ps1
   ```
   El script imprime la ruta de un archivo fechado, por ejemplo `backups\gestion_lol_20261027_153000_123.dump`. Ese archivo `.dump` contiene la estructura y los datos de `gestion_lol`.
2. Abre [Google Drive](https://drive.google.com) en el navegador, entra en la carpeta compartida, selecciona **Nuevo → Subir archivo** y elige el `.dump` creado. Espera a que termine la carga y comparte el archivo/carpeta con los otros integrantes. No subas `.env` ni claves de Riot.
3. Cada compañero descarga ese `.dump` desde Drive web a su computador. Debe tener el repositorio actualizado (`git pull`, si ya lo clonó) y Docker Desktop iniciado. Desde la carpeta del proyecto ejecuta:
   ```powershell
   docker compose up -d lol-postgres
   .\scripts\Restore-GestionLol.ps1 -DumpPath "C:\ruta\local\gestion_lol_20261027_153000_123.dump"
   ```
   Cambia el ejemplo por la ruta y el nombre exactos del archivo descargado. El script pide escribir `REEMPLAZAR` porque la restauración sustituye la base local `gestion_lol` por la del respaldo. No ejecutar mientras haya un DAG cargando datos.
4. El compañero ya puede consultar la captura y seguir trabajando con esos datos. Si ejecuta nuevos DAGs y agrega partidas, genera otro respaldo con `Backup-GestionLol.ps1` y lo sube a Drive web. Los demás descargan ese nuevo archivo y repiten la restauración para actualizar su copia.

Conviene que una persona sea responsable de publicar el respaldo vigente. Cada `.dump` es una copia completa: no se combinan dos respaldos y restaurar uno reemplaza la base local de quien lo restaura. Así se evita que el equipo trabaje sobre copias distintas y después intente fusionarlas.

El respaldo contiene solo `gestion_lol` (estructura y datos). No incluye la base interna de Airflow ni sus variables. Cada integrante mantiene su propio `.env` y su propia clave de Riot; quien solo vaya a consultar los datos no necesita una clave. No subas archivos `.dump` ni `.env` al repositorio.

Este método comparte capturas de la base, no una base sincronizada en vivo: los cambios de un integrante no aparecen en las copias de los demás hasta que publica y distribuye un respaldo nuevo.

### 3. Configurar Variables en la UI de Airflow (Admin -> Variables)
Para cumplir con los estándares de seguridad y flexibilidad de la rúbrica:
* `riot_api_key`: Tu clave activa de Riot Games (`RGAPI-...`).
* `riot_api_base_americas`: `https://americas.api.riotgames.com`
* `riot_api_base_las`: `https://la2.api.riotgames.com`
* *(Opcional)* `riot_target_players`: Lista JSON personalizada de jugadores a monitorear:
  ```json
  [
    {"gameName": "Frikz", "tagLine": "xoro"},
    {"gameName": "Doctor Congo", "tagLine": "SNBK"},
    {"gameName": "The UnfallenHero", "tagLine": "SNBK"},
    {"gameName": "DOCTOR SOLIDO", "tagLine": "SNBK"},
    {"gameName": "Tomoko Kuroki", "tagLine": "Kuro"},
    {"gameName": "Sajor", "tagLine": "FGC"},
    {"gameName": "Michael Kaiser", "tagLine": "10皇帝"},
    {"gameName": "Janemba", "tagLine": "0001"},
    {"gameName": "Gordo Y Cabezon", "tagLine": "Tomm"},
    {"gameName": "Clarissaa", "tagLine": "LAS1"}
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

### Muestra y consulta de campeones por jugador (HU-01)

La variable `riot_target_players` admite hasta 50 jugadores y define la cohorte tanto para el DAG de perfiles como para el DAG de partidas. En cada ejecución, el DAG de partidas consulta hasta 100 IDs Solo/Duo (`queue_id=420`) por PUUID, en páginas de 20 y avanzando `start` hasta completar la muestra o agotar el historial. Para una ejecución manual se puede limitar la cantidad con la configuración del DAG Run, por ejemplo `{"max_partidas_por_jugador": 20}`; el valor permitido es de 1 a 100. `count` sigue disponible como alias para configuraciones antiguas. El límite se aplica a cada ejecución; las partidas únicas ya cargadas se conservan en la base. Cada detalle de partida aporta sus participantes a los KPI agregados, aunque solo se consulta el historial de los Riot ID incluidos en la cohorte.

Para consultar campeones, el archivo `sql/02_consulta_kpi_01_jugador.sql` viene configurado para `Frikz#xoro`; edita el Riot ID si quieres consultar otro jugador y el rol opcional si quieres filtrar. Dejar el rol vacío para incluir todos, o indicar `TOP`, `JUNGLE`, `MIDDLE`, `BOTTOM` o `UTILITY`. Desde 3 partidas la consulta muestra candidatos exploratorios y los ordena por puntaje compuesto; con 3 o 4 quedan como `MUESTRA CORTA` y `cumple_meta` es nulo. Desde 5 partidas se evalúa si el winrate supera el 55%. Ejecutarla después de calcular los KPI:

```powershell
Get-Content .\sql\02_consulta_kpi_01_jugador.sql -Raw |
  docker compose exec -T lol-postgres psql -U postgres -d gestion_lol
```

El mismo archivo incluye una consulta de trazabilidad que devuelve el PUUID junto a sus partidas del DW y comprueba su presencia en el payload Match-V5 guardado en RAW.

El avance y la evidencia validada para HU-01 están resumidos en [`docs/avance_hu01.md`](docs/avance_hu01.md).

---

## Arquitectura del Pipeline y Capas de Datos

* **Capa `raw`:** Ingesta fiel de los payloads JSON de Riot Games junto con timestamp de extracción (`raw_perfil_jugador`, `raw_partidas`).
* **Capa `staging`:** Limpieza, tipado fuerte, filtro de clasificatorias Solo/Duo (`queue_id=420`), descarte de *remakes* (< 5 min), hora local `America/Santiago`, parche del juego y una fila por participante (`match_id`, `puuid`).
* **Capa `dw` (Modelo Estrella):** 
  * Dimensiones: `dw.dim_jugador`, `dw.dim_tiempo` (fecha y hora local de Chile).
  * Tabla de Hechos: `dw.fact_partidas`, con una fila por jugador y partida, incluyendo cola y parche. El payload de cada partida se guarda una vez; la carga deduplica por `(match_id, puuid)`.
* **Capa `mart` (Indicadores de Gestión / KPIs):**
  1. `mart.kpi_01_mejores_campeones`: winrate, KDA agregado y puntaje compuesto por jugador/campeón/rol. Desde 3 partidas puntúa de forma exploratoria; de 3 a 4 se marca `MUESTRA CORTA`, y `cumple_meta` solo se evalúa desde 5. El puntaje pondera winrate (60%), KDA normalizado (25%) y volumen hasta 50 partidas (15%).
  2. `mart.kpi_02_winrate_horario`: winrate por bloque local de 4 horas, comparado con el winrate global del jugador. Con menos de 10 partidas por bloque se muestra como muestra insuficiente y no se recomienda esa franja.
  3. `mart.kpi_03_calificacion_rol`: desde 10 partidas, calcula dos factores según el rol, limita cada factor al rango 0–1 y promedia ambos para obtener `1 + 6 × promedio` (escala 1,0–7,0). TOP usa daño/minuto (600) y daño a torres/minuto (150); JUNGLE usa KDA agregado (4) y dragones/barones del jugador por partida (1); MIDDLE usa KDA (4) y daño/minuto (700); ADC usa daño/minuto (750) y oro/minuto (450); SUPPORT usa KDA (4) y visión/minuto (2). `SUPERA META` significa nota mayor que 5,0. Son referencias definidas para este proyecto, no benchmarks oficiales de Riot.
  4. `mart.kpi_04_control_actividad_diaria`: partidas y horas jugadas por fecha local; alerta desde 7 partidas. El winrate diario solo se muestra desde 10 partidas y la alerta no diagnostica fatiga.
  5. `mart.kpi_05_tierlist_meta_vs_otp`: meta observado por campeón/rol/parche en las partidas recolectadas, considerando a todos sus participantes. Requiere 10 participaciones para clasificar; no identifica OTP ni representa automáticamente todo LAS.

El KDA por partida se calcula como `(asesinatos + asistencias) / MAX(muertes, 1)`, por lo que una partida sin muertes usa 1 como divisor y no recibe una penalización. Para comparar un período se usa `(suma de asesinatos + suma de asistencias) / MAX(suma de muertes, 1)`, sin promediar los KDA individuales. KPI 2, 3 y 5 mantienen mínimos operativos de 10 partidas; KPI 1 muestra puntajes exploratorios desde 3 y solo evalúa la meta desde 5. Estos límites no equivalen a una prueba de significancia estadística. En KPI 3, la métrica de jungla usa dragones/barones asegurados por partida como aproximación individual, no los súbditos neutrales ni todos los objetivos del equipo.
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
