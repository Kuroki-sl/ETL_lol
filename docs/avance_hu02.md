# Avance HU-02: análisis de horarios y control de actividad diaria

## Reglas acordadas

### 1. KPI 2 — Tasa de victorias por bloque horario
- **Zona horaria local:** `gameCreation` (epoch en milisegundos UTC provisto por Match-V5) se transforma a la zona horaria oficial `America/Santiago` antes de extraer la fecha y la hora local.
- **Agrupación en 6 bloques de 4 horas:**
  - `00-03`: Madrugada (00:00 a 03:59)
  - `04-07`: Temprano (04:00 a 07:59)
  - `08-11`: Mañana (08:00 a 11:59)
  - `12-15`: Mediodía / Tarde temprana (12:00 a 15:59)
  - `16-19`: Tarde / Noche temprana (16:00 a 19:59)
  - `20-23`: Noche (20:00 a 23:59)
- **Umbral de muestra mínima:** Se requieren **al menos 10 partidas en el bloque** para generar una recomendación analítica. Con menos de 10 partidas, el estado se clasifica estrictamente como `MUESTRA INSUFICIENTE`.
- **Recomendación frente al promedio personal:** El winrate de la franja se compara contra el winrate global ponderado del propio jugador en clasificatorias Solo/Duo:
  - Winrate > 50% y Winrate > Winrate Global: `FRANJA FAVORABLE EN MUESTRA`
  - Winrate > Winrate Global (Winrate ≤ 50%): `SOBRE PROMEDIO PERSONAL`
  - Winrate < Winrate Global: `BAJO PROMEDIO PERSONAL`
  - Winrate > 50% (Winrate ≤ Winrate Global): `SOBRE 50%, SIMILAR AL GLOBAL`
  - Otros casos: `SIMILAR AL PROMEDIO GLOBAL`
- **Interpretación:** El indicador describe una **asociación histórica observada** en la muestra disponible; no pretende afirmar causalidad ni asegurar que jugar en cierto horario garantice ganar.

---

### 2. KPI 4 — Control de actividad diaria y sobrecarga
- **Fórmula:** Recuento de partidas clasificatorias Solo/Duo iniciadas en cada fecha calendario (hora local de Chile) y suma de `duracion_min` convertida a horas (`horas_jugadas_dia`).
- **Alerta de actividad elevada:** Si el jugador disputa **7 o más partidas en el mismo día**, se activa la bandera `alerta_sobrecarga = true`.
- **Winrate diario:** Se calcula y muestra si el jugador disputó **5 o más partidas en el día**. Con menos de 5 partidas diarias queda en `NULL` para evitar que rachas cortas de 1–4 partidas sesguen la lectura con porcentajes extremos.
- **Alcance:** La alerta opera como recordatorio de gestión del descanso y organización de sesiones; no constituye un diagnóstico médico de fatiga.

---

## Evidencia Validada en Base de Datos Real

### A. Resultados de KPI 2 para `Frikz#xoro` (Winrate global: 53,45%)

| Bloque Horario | Franja Local Chile | Partidas | Victorias | Derrotas | Winrate Bloque | Dif. vs Global | Clasificación / Recomendación |
| :---: | :--- | :---:| :---:| :---:| :---:| :---:| :--- |
| **`16-19`** | Tarde / Noche temprana (16:00 a 19:59) | 18 | 11 | 7 | **61,11%** | +7,66% | `FRANJA FAVORABLE EN MUESTRA` |
| **`00-03`** | Madrugada (00:00 a 03:59) | 14 | 9 | 5 | **64,29%** | +10,84% | `FRANJA FAVORABLE EN MUESTRA` |
| **`20-23`** | Noche (20:00 a 23:59) | 81 | 41 | 40 | **50,62%** | -2,83% | `BAJO PROMEDIO PERSONAL` |
| **`12-15`** | Mediodía / Tarde temprana (12:00 a 15:59) | 2 | 1 | 1 | 50,00% | -3,45% | `MUESTRA INSUFICIENTE` |
| **`04-07`** | Temprano (04:00 a 07:59) | 1 | 0 | 1 | 0,00% | -53,45% | `MUESTRA INSUFICIENTE` |

**Hallazgos de gestión:**
* `Frikz#xoro` disputa la gran mayoría de sus partidas (81 de 116) en la noche (`20-23`), pero su rendimiento allí es ligeramente inferior a su promedio personal (50,62% vs 53,45%).
* Sus mejores resultados se concentran en la tarde (`16-19`: 61,11%) y en la madrugada (`00-03`: 64,29%), superando tanto el 50% como su media global.
* Las franjas de mañana y mediodía no alcanzan el umbral de 10 partidas y quedan protegidas como `MUESTRA INSUFICIENTE`.

---

### B. Evidencia de KPI 4: Alertas de Sobrecarga (≥ 7 partidas) y Winrate Diario (≥ 5 partidas)

Al evaluar las sesiones en la base de datos real con el umbral de **5 partidas**:

| Jugador | Fecha (Chile) | Partidas Día | Horas Estimadas | Alerta Sobrecarga | Winrate Diario | Interpretación |
| :--- | :---: | :---:| :---:| :---:| :---:| :--- |
| **Frikz#xoro** | 2026-01-10 | 7 | 4,18 hrs | `true`  | 71,43% | Alerta activa (≥7); sesión intensa y con excelente efectividad |
| **Frikz#xoro** | 2026-09-10 | 6 | 3,21 hrs | `false` | 50,00% | Actividad moderada (<7); winrate diario evaluado (≥5 partidas) |
| **Frikz#xoro** | 2026-10-05 | 5 | 2,16 hrs | `false` | 20,00% | Actividad moderada (<7); detección de día adverso (5 partidas) |
| **Michael Kaiser#10皇帝** | 2026-02-08 | 14 | 6,03 hrs | `true`  | 64,29% | Alerta activa; sesión muy prolongada con racha ganadora |
| **Michael Kaiser#10皇帝** | 2026-02-11 | 11 | 5,02 hrs | `true`  | 27,27% | Alerta activa; sobrecarga con caída pronunciada de rendimiento |

Esta evidencia corrobora en datos reales que:
1. La alerta de actividad elevada se activa de forma estricta al alcanzar 7 partidas en la misma fecha calendario.
2. El winrate diario permite analizar el desempeño en días de actividad moderada a alta (desde 5 partidas), evitando el ruido de jornadas de 1 a 4 partidas.

---

## Trazabilidad de Extremo a Extremo (RAW → DW → MART)

1. **RAW (`raw.raw_partidas`):** Contiene el JSON original devuelto por Match-V5. El campo `info.gameCreation` almacena el timestamp en milisegundos UTC (ej. `1792805088895` ms -> `2026-10-24 01:24:48 UTC`).
2. **STAGING (`staging.stg_partidas`):** Se convierte el timestamp a `datetime` con `ZoneInfo("America/Santiago")`, descartando partidas de duración menor a 5 minutos (*remakes*) o fuera de la cola `queue_id = 420`.
3. **Data Warehouse (`dw.dim_tiempo` y `dw.fact_partidas`):** La partida se registra con fecha `2026-10-23`, hora `22` (bloque `20-23`) en horario local de Chile, y se enlaza a la tabla de hechos.
4. **Capa Mart (`mart.kpi_02_winrate_horario` y `mart.kpi_04_control_actividad_diaria`):** Agrega las métricas y aplica las reglas de muestra mínima y alertas.

---

## Ejecución del Script de Consultas

El script ejecutable con las consultas de HU-02 se encuentra en [`sql/03_consulta_kpi_02_04_horario_actividad.sql`](../sql/03_consulta_kpi_02_04_horario_actividad.sql):

```powershell
Get-Content .\sql\03_consulta_kpi_02_04_horario_actividad.sql -Raw |
  docker compose exec -T lol-postgres psql -U postgres -d gestion_lol
```
