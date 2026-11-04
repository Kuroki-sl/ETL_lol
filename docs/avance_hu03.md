# Avance HU-03: evaluación de desempeño por rol y meta observado

## Reglas acordadas

### 1. KPI 3 — Calificación de desempeño por rol (escala 1,0 a 7,0)
- **Métricas por minuto y agregadas:** Las métricas acumuladas se normalizan dividiendo por la duración de la partida en minutos (`dano_campeones / duracion_min`, `oro / duracion_min`, `vision / duracion_min`, `dano_torres / duracion_min`). El KDA se calcula como una razón agregada del período `(kills + assists) / GREATEST(deaths, 1)` sin dividirlo por minutos ni promediar razones individuales.
- **Aproximación individual para Jungla (JG):** Como Match-V5 no entrega de forma consistente el daño porcentual al objetivo por jugador, se utiliza la suma individual de dragones y barones asegurados por el jugador (`dragonKills + baronKills` por partida), evitando atribuir automáticamente a cada jungla todos los objetivos asegurados por su equipo.
- **Tabla de referencias acordadas por rol para el proyecto:**
  Las referencias son parámetros operativos acordados por el equipo para contextualizar las métricas en la escala chilena; no constituyen benchmarks oficiales de Riot Games:

| Rol | Factor 1 (Criterio y Referencia) | Factor 2 (Criterio y Referencia) |
| :--- | :--- | :--- |
| **TOP** | Daño a campeones / min (`650.0` DPM) | Daño a torres / min (`200.0` Torres/min) |
| **JUNGLE** | KDA agregado (`4.5`) | Dragones y Barones individuales por partida (`3.0` Obj/partida) |
| **MIDDLE** | KDA agregado (`4.5`) | Daño a campeones / min (`700.0` DPM) |
| **BOTTOM / ADC** | Daño a campeones / min (`750.0` DPM) | Oro por minuto (`500.0` GPM) |
| **UTILITY / SUPPORT** | KDA agregado (`4.0`) | Puntuación de visión / min (`2.0` VSPM) |

- **Normalización y cálculo de nota:**
  Cada factor se acota estrictamente al intervalo $[0, 1]$:
  $$N_i = \min\left(1, \max\left(0, \frac{\text{Métrica Promedio}_i}{\text{Referencia}_i}\right)\right)$$
  La nota se mapea a la escala 1,0 a 7,0 mediante:
  $$\text{Nota} = 1.0 + 6.0 \times \left(\frac{N_1 + N_2}{2}\right)$$
- **Umbral de cumplimiento de meta:**
  - $\text{Nota} > 5.5$: `Logra la meta`
  - $\text{Nota} \le 5.5$: `No logró la meta`
  - Partidas $< 10$: `Muestra insuficiente` (no evalúa meta definitiva)

---

### 2. KPI 5 — Rendimiento de campeones por rol en la muestra analizada (Meta vs OTP)
- **Ámbito agregado:** Evalúa a los diez participantes de cada partida recolectada en la cohorte.
- **Agrupación y partición:** Agrupa por campeón (`championName`), rol (`teamPosition`) y parche (`gameVersion` / `parche`), garantizando que cada participante compute una sola vez por partida.
- **Mínimo de muestra:** Se requiere un mínimo de **10 participaciones** en ese rol y parche para clasificar.
- **Criterios de clasificación:**
  - Partidas $\ge 10$ y Winrate $> 52.0\%$: `Destacado en la muestra`
  - Partidas $\ge 10$ y Winrate $\le 52.0\%$: `No supera el umbral`
  - Partidas $< 10$: `Muestra insuficiente` (evita declarar casos atípicos o especializados como dominantes).
- **Aclaración sobre sesgo y alcance:** El indicador describe el meta observado en las partidas recolectadas para la cohorte analizada.

---

## Evidencia Validada en Base de Datos Real

### A. Resultados de KPI 3 para `Frikz#xoro` (116 partidas analizadas en DW)

Al ejecutar la consulta sobre la base de datos PostgreSQL real, se obtienen las siguientes calificaciones por rol para `Frikz#xoro`:

| Rol | Partidas | KDA | DPM | GPM | Visión/min | Torres/min | Obj JG/partida | Nota (1–7) | Estado de Rendimiento |
| :--- | :---:| :---:| :---:| :---:| :---:| :---:| :---:| :---:| :--- |
| **MIDDLE** | 78 | 2,42 | 935,98 | 415,87 | 0,83 | 214,82 | 0,04 | **5,6** | `Logra la meta` |
| **JUNGLE** | 16 | 2,19 | 833,34 | 450,76 | 0,92 | 115,91 | 2,88 | **5,3** | `No logró la meta` |
| **BOTTOM** | 14 | 2,36 | 972,49 | 467,38 | 0,90 | 198,49 | 0,36 | **6,8** | `Logra la meta` |
| **UTILITY** | 6 | 5,83 | 439,52 | 328,26 | 2,70 | 66,63 | 0,17 | **7,0** | `Logra la meta` |
| **TOP** | 2 | 0,00 | 588,67 | 324,36 | 0,74 | 81,61 | 0,00 | **4,9** | `No logró la meta` |

**Hallazgos de gestión:**
* `Frikz#xoro` es predominantemente jugador de carril central (`MIDDLE` con 78 partidas). Su daño promedio es altísimo (935,98 DPM vs referencia 700), lo que satura su factor ofensivo al máximo (1,0) y compensa su KDA de 2,42 (vs referencia 4,5), alcanzando una nota de 5,6.
* En `JUNGLE` (16 partidas), no supera la referencia de objetivos neutrales individuales con 2,88 dragones/barones por partida frente a la referencia de 3,0.
* Las participaciones en `UTILITY` (6) y `TOP` (2) presentan notas elevadas, pero al contar con menos de 10 partidas se interpretan con cautela.

---

### B. Evidencia de KPI 5: Tierlist del Meta Observado (Umbral ≥ 10 partidas)

En la muestra consolidada (4.819 combinaciones de campeón/rol/parche), 29 combinaciones superan el 52% de winrate con al menos 10 partidas:

| Campeón | Rol | Parche | Partidas Totales | Winrate Global | KDA Global | Clasificación Tier |
| :--- | :--- | :--- | :---:| :---:| :---:| :--- |
| **Soraka** | UTILITY | 15.15 | 10 | **90,00%** | 3,65 | `Destacado en la muestra` |
| **Soraka** | UTILITY | 15.14 | 17 | **88,24%** | 5,37 | `Destacado en la muestra` |
| **Caitlyn** | BOTTOM | 16.18 | 16 | **75,00%** | 3,62 | `Destacado en la muestra` |
| **Nami** | UTILITY | 16.7 | 11 | **72,73%** | 7,66 | `Destacado en la muestra` |
| **Lulu** | UTILITY | 16.19 | 11 | **72,73%** | 7,50 | `Destacado en la muestra` |
| **Lulu** | UTILITY | 16.7 | 14 | **71,43%** | 7,70 | `Destacado en la muestra` |
| **Tristana** | BOTTOM | 16.17 | 10 | **70,00%** | 3,55 | `Destacado en la muestra` |
| **LeeSin** | JUNGLE | 16.18 | 16 | **68,75%** | 6,83 | `Destacado en la muestra` |

Ejemplos de campeones con muestra suficiente que **no superan el umbral** (≤ 52%):
* **Lulu** (UTILITY, parche 16.18): 26 partidas, 38,46% winrate, KDA 5,07 → `No supera el umbral`.
* **Jax** (TOP, parche 16.1): 22 partidas, 31,82% winrate, KDA 2,03 → `No supera el umbral`.
* **Yunara** (BOTTOM, parche 16.18): 19 partidas, 42,11% winrate, KDA 2,56 → `No supera el umbral`.

Y 4.763 combinaciones con menos de 10 partidas quedan catalogadas como `Muestra insuficiente`.

---

## Trazabilidad de Extremo a Extremo (RAW → DW → MART)

1. **RAW (`raw.raw_partidas`):** Contiene el payload completo devuelto por Match-V5. Cada entrada del arreglo `info.participants` provee `kills`, `deaths`, `assists`, `totalDamageDealtToChampions`, `goldEarned`, `visionScore`, `damageDealtToTurrets`, `dragonKills` y `baronKills`.
2. **STAGING (`staging.stg_partidas` / `staging.estadisticas_jugador`):** Extrae y valida la consistencia de tipos numéricos, calcula métricas preliminares por minuto y filtra partidas no clasificatorias o remakes ($< 5$ min).
3. **Data Warehouse (`dw.fact_partidas`):** Almacena las 9.070 participaciones clasificatorias Solo/Duo vinculadas a `dw.dim_jugador` y `dw.dim_tiempo`.
4. **Capa Mart (`mart.kpi_03_calificacion_rol` y `mart.kpi_05_tierlist_meta_vs_otp`):** Reconstruye las tablas analíticas agregando métricas por rol y parche, aplicando las fórmulas de normalización y los umbrales de muestra.

---

## Ejecución del Script de Consultas

El script ejecutable con las consultas de HU-03 se encuentra en [`sql/04_consulta_kpi_03_05_rol_meta.sql`](../sql/04_consulta_kpi_03_05_rol_meta.sql):

```powershell
Get-Content .\sql\04_consulta_kpi_03_05_rol_meta.sql -Raw |
  docker exec -i db_lol psql -U postgres -d gestion_lol
```
