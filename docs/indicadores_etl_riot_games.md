# Definición de indicadores de gestión — Proyecto ETL League of Legends

## 1. Contexto y alcance

Este documento consolida las ideas del equipo para definir **cinco indicadores de gestión** obtenidos a partir de datos de partidas de *League of Legends* mediante las APIs de Riot Games y el catálogo de Data Dragon. Se plantea como una **especificación conceptual para un proyecto universitario de ETL**, no como un sistema profesional ni como una investigación que pretenda establecer relaciones causales sobre el rendimiento competitivo.

La propuesta considera **cuatro indicadores para un jugador específico** y **uno agregado sobre los participantes de las partidas recolectadas**. Para cada indicador se explicitan nombre, objetivo o decisión que apoya, fórmula, fuentes, periodicidad y meta o umbral. Los valores de referencia son **criterios operativos propuestos por el equipo** y podrán ajustarse antes de implementar el ETL.

### Criterios generales

- Analizar principalmente partidas clasificatorias Solo/Duo (`queue=420`), aplicando el mismo filtro en los indicadores para que las comparaciones sean consistentes.
- Excluir partidas que no sean comparables, como remakes, y documentar las reglas de calidad aplicadas.
- Para los indicadores del perfil, identificar al jugador mediante su `puuid`.
- Mostrar el tamaño de muestra junto con los porcentajes, especialmente cuando se elaboren rankings.
- No confundir **frecuencia de ejecución del ETL** con **período de análisis del indicador**. Un ETL puede actualizarse diariamente y un KPI analizar los últimos siete, treinta días o el parche actual.
- Los umbrales se utilizarán como **reglas de clasificación del proyecto**. No representan estándares oficiales de Riot Games.
- Para el KDA de una partida, usar `(asesinatos + asistencias) / MAX(muertes, 1)`. Si el jugador no muere, se divide por 1: no se penaliza una partida sin muertes ni se deja el KDA nulo.
- Para el KDA de un período, usar `(suma de asesinatos + suma de asistencias) / MAX(suma de muertes, 1)`. No promediar los KDA por partida, porque ese promedio da el mismo peso a partidas con distinta cantidad de muertes.

---

## KPI 1. Rendimiento y tasa de victorias por campeón y rol del jugador

**Ámbito:** Perfil específico.

**Objetivo y decisión que apoya:** Identificar con qué campeones obtiene mejores resultados un jugador en partidas clasificatorias. Mostrar una vista general por campeón y permitir filtrar por TOP, JG, MID, ADC y SUPP. Apoya la elección y priorización del *champion pool*.

**Fórmula:**

\[
\operatorname{Winrate}_{c,r}(\%) = \frac{\text{Victorias con el campeón }c\text{ en rol }r}{\text{Partidas con el campeón }c\text{ en rol }r}\times 100
\]

Para la vista **GENERAL**, el cálculo agrega las partidas del campeón en todos los roles, sin duplicar filas del desglose por rol.

En la implementación actual se añade un **puntaje compuesto de 0 a 100** para ordenar el desempeño por jugador, campeón y rol:

\[
\operatorname{Puntaje}=0{,}60\times\operatorname{Winrate}(\%)
+0{,}25\times\min(100,20\times\operatorname{KDA})
+0{,}15\times\min(100,2\times\operatorname{Partidas})
\]

El puntaje exploratorio se calcula desde 3 partidas. Entre 3 y 4 se marca **«Muestra corta»**; desde 5 partidas se considera adecuada para evaluar `cumple_meta` (winrate > 55%). El componente de KDA llega a su máximo al alcanzar 5,0; el componente de volumen llega al máximo en 50 partidas.

**Fuentes:** Match-V5 para participaciones y resultados, Account-V1 para identificar el perfil por `puuid`, y Data Dragon para nombres de campeones. Summoner-V4 puede aportar atributos complementarios del jugador, pero no es necesario para calcular el winrate.

**Periodicidad propuesta:** Semanal, por ejemplo, sobre una ventana móvil de datos disponibles.

**Meta / umbral:** **Winrate > 55%**. Se muestran candidatos desde **3 partidas**; se requieren **5 partidas por campeón y rol** para evaluar el cumplimiento de la meta.

**Reglas e interpretación:**

- Mostrar partidas jugadas, victorias y winrate.
- Con menos de 3 partidas, marcar **«Muestra insuficiente»** y no calcular puntaje. Con 3 o 4, mostrar el candidato como **«Muestra corta»** sin afirmar que supera o incumple la meta. Desde 5 partidas, evaluar el winrate frente al 55%.
- Evaluar por separado las muestras de la vista general y de cada rol. Cinco partidas en general no implican cinco partidas en TOP, por ejemplo.
- El 55%, el piso exploratorio de 3 y el mínimo adecuado de 5 son decisiones del proyecto, no reglas oficiales del juego ni una garantía de significancia estadística.

**Ejemplo:** Un campeón con 1 victoria en 1 partida muestra 100%, pero queda marcado como muestra insuficiente. Otro con 12 victorias en 20 partidas muestra 60% y supera el umbral.

---

## KPI 2. Tasa de victorias del jugador por bloque horario

**Ámbito:** Perfil específico.

**Objetivo y decisión que apoya:** Identificar las franjas horarias en las que el jugador presenta mejores o peores resultados históricos y utilizar esa información como apoyo para organizar sus sesiones de juego. El indicador describe una **asociación observada**; no pretende demostrar que el horario por sí solo causa un cambio de rendimiento.

**Fórmula:**

\[
\operatorname{Winrate}_{b}(\%)=\frac{\text{Victorias en partidas iniciadas en el bloque }b}{\text{Partidas iniciadas en el bloque }b}\times 100
\]

Comparación de referencia:

\[
\operatorname{Winrate\ global}(\%)=\frac{\text{Victorias totales del jugador en el período}}{\text{Partidas totales del jugador en el período}}\times100
\]

**Fuentes:** Match-V5 (`gameCreation`, resultado y `puuid`), con transformación a la dimensión de tiempo (`dw.dim_tiempo`). Account-V1 identifica al jugador.

**Periodicidad propuesta:** Mensual o acumulada, con desglose en **seis bloques de cuatro horas** según la hora de inicio de partida convertida a la hora local de Chile (`America/Santiago`):
- `00-03`: Madrugada (00:00 a 03:59)
- `04-07`: Temprano (04:00 a 07:59)
- `08-11`: Mañana (08:00 a 11:59)
- `12-15`: Mediodía / Tarde temprana (12:00 a 15:59)
- `16-19`: Tarde / Noche temprana (16:00 a 19:59)
- `20-23`: Noche (20:00 a 23:59)

**Meta / umbral:** **Mínimo de 10 partidas por bloque**. Si se alcanza el mínimo, se evalúa si el winrate del bloque supera el 50% y cómo se posiciona frente al winrate global del propio jugador.

**Reglas de clasificación del bloque (`recomendacion_gestion`):**

| Condición | Clasificación | Interpretación |
|---|---|---|
| Partidas en bloque < 10 | `MUESTRA INSUFICIENTE` | Muestra no representativa; no se recomienda ni califica la franja |
| Partidas ≥ 10 y Winrate > 50% y Winrate > Winrate Global | `FRANJA FAVORABLE EN MUESTRA` | Horario destacado con desempeño superior al promedio personal y al 50% |
| Partidas ≥ 10 y Winrate > Winrate Global (Winrate ≤ 50%) | `SOBRE PROMEDIO PERSONAL` | Rinde mejor que su media personal, aunque bajo el 50% global del juego |
| Partidas ≥ 10 y Winrate < Winrate Global | `BAJO PROMEDIO PERSONAL` | Franja con rendimiento inferior al promedio habitual del jugador |
| Partidas ≥ 10 y Winrate > 50% (Winrate ≤ Winrate Global) | `SOBRE 50%, SIMILAR AL GLOBAL` | Franja positiva, alineada con un winrate global alto del jugador |
| Partidas ≥ 10 (otros casos) | `SIMILAR AL PROMEDIO GLOBAL` | Desempeño sin variaciones relevantes respecto al promedio general |

**Reglas e interpretación:**

- Transformar `gameCreation` (timestamp en milisegundos UTC) a la zona horaria `America/Santiago` **antes** de extraer la hora y asignar el bloque correspondiente.
- La hora se refiere al **inicio de la partida**, no a la hora de finalización.
- La agrupación en bloques de 4 horas evita la dispersión excesiva que ocurriría al evaluar 24 horas individuales en muestras universitarias, concentrando las observaciones para alcanzar el umbral de significancia analítica de 10 partidas.
- Calcular el winrate global con el total acumulado de victorias dividido por el total acumulado de partidas Solo/Duo. No promediar sin ponderación los winrates de los bloques.

**Ejemplo:** Un jugador disputa 15 partidas en el bloque `20-23` y gana 10 (winrate 66,67%), mientras que su winrate global es 52,00%. El sistema clasifica el bloque como `FRANJA FAVORABLE EN MUESTRA`. En cambio, si en el bloque `04-07` registra 2 partidas con 2 victorias (100%), se clasifica como `MUESTRA INSUFICIENTE` y no se emite recomendación positiva.

---

## KPI 3. Calificación integral de desempeño por rol (escala 1,0 a 7,0)

**Ámbito:** Perfil específico.

**Objetivo y decisión que apoya:** Obtener una nota comparativa del desempeño del jugador en cada rol, usando métricas pertinentes para sus responsabilidades. Apoya la identificación de fortalezas, oportunidades de mejora y posibles preferencias de rol principal.

### Problema de la propuesta inicial

Evaluar exclusivamente cifras acumuladas de daño, oro o visión favorece indirectamente a partidas de mayor duración: 30.000 de daño en 45 minutos no significa lo mismo que 30.000 en 25 minutos. Por ello se propone **normalizar por minuto las métricas acumulativas**, antes de convertirlas a una escala común de puntuación.

### Métricas propuestas por rol

| Rol | Factor 1 | Factor 2 | Motivo |
|---|---|---|---|
| TOP | Daño a campeones por minuto | Daño a torres por minuto | Presión en combate y estructuras |
| JG | KDA | Participación en objetivos por partida | Combates y control de objetivos |
| MID | KDA | Daño a campeones por minuto | Supervivencia/contribución y presión ofensiva |
| ADC | Daño a campeones por minuto | Oro por minuto | Producción de daño y obtención de recursos |
| SUPP | KDA | Puntuación de visión por minuto | Participación en jugadas y aporte de visión |

**Nota sobre JG:** «Participación en objetivos» requiere una definición técnica que evite contabilizar automáticamente para cada jungla todos los objetivos obtenidos por el equipo. Puede emplearse una métrica de participación individual disponible y verificable en Match-V5; si no hay un campo consistente, el equipo debe definir una aproximación documentada antes de programar el cálculo. La tabla representa la intención conceptual del indicador.

### Normalización y fórmula

Para cada partida, cuando la duración sea válida:

\[
\operatorname{Métrica\ por\ minuto}=\frac{\operatorname{Métrica\ acumulada}}{\operatorname{Duración\ de\ partida\ en\ minutos}}
\]

Cada factor se compara con una referencia **establecida por el equipo y expresada en la misma unidad**. Los valores se acotan para impedir notas mayores que 7:

\[
N_i=\min\left(1,\max\left(0,\frac{\operatorname{Factor}_i}{\operatorname{Referencia}_i}\right)\right)
\]

\[
\operatorname{Nota\ por\ rol}=1+6\times\frac{N_1+N_2}{2}
\]

Se propone calcular cada factor como **promedio de la métrica de las partidas del jugador en ese rol durante el período** y, a continuación, aplicar la fórmula de normalización a esos promedios. Debe documentarse el mismo procedimiento para todos los roles.

**Referencias:** Los valores originales del borrador (por ejemplo, KDA 4,0 o cantidades totales de daño y visión) eran ilustrativos. **No deben reutilizarse sin adaptación** cuando la métrica pase a expresarse por minuto. El equipo definirá una tabla de referencias por rol antes de implementar, indicando unidad, criterio y valor. No se presentan como benchmarks oficiales.

**Referencias usadas provisionalmente por la implementación actual:** TOP: daño/minuto 600 y daño a torres/minuto 150; JG: KDA 4 y dragones/barones individuales por partida 1; MID: KDA 4 y daño/minuto 700; ADC: daño/minuto 750 y oro/minuto 450; SUPP: KDA 4 y visión/minuto 2. Son parámetros definidos para este proyecto, no benchmarks oficiales de Riot, y deben revisarse con el equipo/profesora.

**Fuentes:** Match-V5, campos de participaciones y estadísticas por partida. Account-V1 para identificar el perfil.

**Periodicidad propuesta:** Semanal.

**Meta / umbral:** **Nota > 5,0** para considerar que el rol supera la meta definida.

**Reglas e interpretación:**

- Mantener la escala chilena 1,0 a 7,0 porque resulta familiar y fácil de explicar.
- Mostrar el número de partidas analizadas en cada rol y, cuando resulte posible, los valores de ambos factores antes de convertirlos a nota.
- La calificación es un **índice construido para el proyecto**, no una clasificación oficial de habilidad ni una demostración de que un rol es objetivamente «mejor» que otro.
- Normalizar por minuto los acumulados y utilizar unidades coherentes. El KDA es una razón y no debe dividirse por la duración.
- Si faltan datos para un factor, documentar su tratamiento y evitar asignar automáticamente una nota válida.

---

## KPI 4. Volumen diario de partidas del jugador

**Ámbito:** Perfil específico.

**Objetivo y decisión que apoya:** Monitorear la actividad diaria del jugador y generar una alerta cuando supere el volumen de juego propuesto. Puede servir como recordatorio para descansar o distribuir mejor las sesiones. **No diagnostica fatiga** ni busca explicar necesariamente el winrate.

**Fórmula:**

\[
\operatorname{Partidas\ diarias}_{d}=\operatorname{COUNT}(\text{partidas del jugador iniciadas en la fecha local }d)
\]

**Fuentes:** Match-V5, `puuid`, identificador de partida y hora de inicio transformada a fecha local. Account-V1 para identificar al jugador.

**Periodicidad propuesta:** Actualización diaria y resumen semanal.

**Meta / umbral:** **Menos de 7 partidas por día**. Por tanto, con **7 o más** se activa una alerta de actividad elevada.

**Reglas e interpretación:**

- Contar cada partida del jugador una sola vez.
- Utilizar fecha local de Chile para agrupar correctamente las partidas que ocurren cerca de medianoche.
- En promedios diarios, distinguir entre promedio por **día con actividad** y promedio por **día calendario**, incluyendo días con cero partidas si se usa este último.
- El umbral de 7 es una regla práctica propuesta para el proyecto y no una recomendación médica o científica.

**Ejemplo:** Si el jugador disputa 8 partidas en un día, se genera «Alerta de actividad elevada». No se concluye automáticamente que su rendimiento haya disminuido.

---

## KPI 5. Rendimiento de campeones por rol en la muestra analizada (análisis del meta)

**Ámbito:** Agregado, considerando los diez participantes de las partidas recolectadas.

**Objetivo y decisión que apoya:** Identificar qué campeones muestran tasas de victorias elevadas por rol en la muestra disponible, evitando que campeones poco frecuentes o casos extremos encabecen el ranking solamente por haber aparecido en unas pocas partidas.

### Aclaración principal sobre OTP y sesgos

**El indicador NO pretende identificar campeones OTP ni clasificar jugadores como OTP.** La motivación es precisamente reducir el efecto que pueden tener los **casos atípicos** en las conclusiones. Por ejemplo, algunos especialistas de Riven pueden obtener winrates muy altos, aunque eso no signifique por sí solo que Riven sea un campeón dominante del meta general. Un número mínimo de observaciones ayuda a evitar que un campeón con 1, 2 o 5 partidas y winrate extraordinario sea presentado automáticamente como una opción dominante.

El mínimo de partidas **reduce la sensibilidad a muestras pequeñas**, pero **no elimina por completo el sesgo de especialización**: incluso una muestra de tamaño considerable podría estar concentrada en pocos jugadores expertos. En el contexto universitario, esta limitación se explicitará sin exigir un modelo avanzado de corrección estadística.

**Fórmula:**

\[
\operatorname{Winrate}_{c,r}(\%)=\frac{\text{Victorias de participantes que usaron }c\text{ en }r}{\text{Participaciones con }c\text{ en }r}\times100
\]

**Fuentes:** Match-V5 para resultados, campeones, rol y participantes; Data Dragon para los nombres de los campeones.

**Periodicidad propuesta:** Quincenal o al actualizarse el parche, siempre que el conjunto de partidas contenga suficientes registros.

**Meta / umbral:** **Winrate > 52% y al menos 10 participaciones del campeón en ese rol**, como criterios conceptuales definidos por el equipo. El mínimo de 10 es ilustrativo y conviene ampliarlo si se recolecta una muestra grande.

**Reglas de clasificación:**

| Condición | Resultado | Interpretación |
|---|---|---|
| Menos de 10 participaciones | Muestra insuficiente | Se muestra el dato, pero no se usa para declarar dominancia |
| 10 o más participaciones y winrate > 52% | Destacado en la muestra | Cumple los criterios propuestos para el ranking |
| 10 o más participaciones y winrate ≤ 52% | No supera el umbral | Tiene información suficiente, pero no cumple la meta |

**Ejemplo ilustrativo:**

| Campeón | Participaciones en su rol | Winrate | Resultado |
|---|---:|---:|---|
| Riven | 5 | 80% | Muestra insuficiente |
| Garen | 40 | 55% | Destacado en la muestra |
| Darius | 35 | 48% | No supera el umbral |
| Fiora | 2 | 100% | Muestra insuficiente |

**Interpretación y alcance:**

- El conjunto proviene de las partidas recolectadas a partir de los jugadores seleccionados. No equivale a una muestra representativa de todos los servidores, regiones o rangos de League of Legends.
- En la implementación, conviene guardar el **parche de cada partida** (`gameVersion`) y permitir filtrar por parche para evitar mezclar versiones con balances diferentes.
- Si varios perfiles objetivo permiten recuperar una misma partida, debe guardarse una sola vez y contabilizar cada participación una sola vez; la clave compuesta `(match_id, puuid)` facilita este control.
- Si se desea mejorar el análisis posteriormente, se puede medir también el número de **jugadores distintos** que utilizaron un campeón. Es un complemento útil para detectar concentración de resultados, pero no es necesario para la primera versión.
- Hablar de **«meta observado en la muestra»**, no afirmar que se ha determinado el meta global del juego.

---

## 2. Resumen para la implementación

| KPI | Nivel de análisis | Métrica principal | Meta o regla | Ajuste clave |
|---|---|---|---|---|
| 1. Winrate por campeón | Jugador, campeón y rol | Victorias / partidas | Mostrar desde 3; evaluar > 55% desde 5 partidas | Marcar 3–4 como muestra corta y evitar rankings de muestras mínimas |
| 2. Winrate horario | Jugador y bloque local de 4 horas | Victorias / partidas por bloque | > 50%, mínimo 10 partidas por bloque | Comparar con el winrate global ponderado por partidas |
| 3. Calificación por rol | Jugador y rol | Dos factores normalizados y nota 1–7 | Nota > 5,0, mínimo 10 partidas | Pasar acumulados a tasas por minuto y usar referencias operativas documentadas |
| 4. Partidas por día | Jugador y fecha local | Recuento de partidas | Alerta desde 7 partidas | Mostrar winrate diario solo desde 10 partidas; medir actividad, no diagnosticar fatiga |
| 5. Meta observado | Campeón, rol, parche y muestra | Victorias / participaciones | > 52%, mínimo 10 participaciones | Excluir muestras pequeñas de la clasificación de dominancia; no etiquetar OTP |

## 3. Requisitos de datos que se desprenden de los indicadores

Los cinco indicadores pueden construirse a partir de una tabla de hechos a nivel **una partida por participante**, enlazada al jugador, campeón y fecha/hora. Se recomiendan los siguientes datos en la etapa de transformación:

- Identificación: `match_id`, `puuid`, `championId`, `teamPosition`.
- Resultado: `win` y métricas del participante como `kills`, `deaths`, `assists`, `totalDamageDealtToChampions`, `damageDealtToTurrets`, `goldEarned`, `visionScore`, `dragonKills` y `baronKills`.
- Tiempo: `gameCreation`, `gameDuration`, fecha y hora local derivadas.
- Contexto competitivo: `queueId` y `gameVersion` de la partida.
- Control de calidad: deduplicación por `(match_id, puuid)`, validación de roles y tratamiento explícito de remakes y datos incompletos.

**Cierre de parámetros operativos:** Para el KPI 3 se ratificaron en la implementación SQL los dos factores por rol normalizados por minuto (TOP, MID, ADC, SUPP) y la aproximación de JG (`dragonKills + baronKills` asegurados individualmente por partida). En KPI 1 se muestran candidatos desde 3 partidas y se evalúa la meta desde 5; en KPI 2, 3 y 5 se mantiene el mínimo de 10 partidas/participaciones como umbral operativo del proyecto.

## 4. Conclusión

Se conservan los **cinco indicadores originales** y su propósito. Los cambios principales consisten en **normalizar correctamente la calificación por rol** (KPI 3) y **aclarar que el mínimo de partidas del análisis del meta reduce la influencia de muestras pequeñas y casos atípicos, sin identificar OTP** (KPI 5). Los demás ajustes buscan que sus fórmulas, resultados y reglas de clasificación sean coherentes, reproducibles y fáciles de defender en una evaluación universitaria.

> Este documento define los indicadores a nivel conceptual. No reemplaza la implementación SQL ni garantiza por sí solo el cumplimiento completo de la rúbrica de la asignatura.

---

## 5. Correcciones registradas en la implementación (2026-10-26 a 2026-10-28)

Esta sección registra cómo quedó implementado el proyecto después de las correcciones. Los mínimos y referencias numéricas son decisiones operativas de esta versión; no son reglas de Riot ni evidencia estadística concluyente.

1. **KDA cuando hay cero muertes:** se corrigió el tratamiento anterior que dejaba el KDA nulo. Por partida se divide por `MAX(muertes, 1)`; en una agregación se divide por `MAX(suma de muertes, 1)`. Por eso, por ejemplo, una partida `5/0/10` tiene KDA 15, no nulo ni penalizado. El KDA del período se calcula con las sumas del período, no como promedio de los KDA por partida.
2. **Partidas duplicadas o participaciones omitidas:** `raw.raw_partidas` guarda una sola fila por `match_id` y conserva la extracción más reciente si había duplicados. La transformación procesa una vez cada partida guardada e incluye sus diez participantes, con una fila por `(match_id, puuid)`. La sincronización actualiza los hechos desde STAGING; si RAW no produce partidas válidas o STAGING está vacío mientras DW tiene hechos, el proceso se detiene/conserva la última carga en vez de borrar los datos existentes.
3. **Alcance competitivo y calidad:** todos los KPI filtran clasificatorias Solo/Duo (`queue_id=420`). Las partidas menores de cinco minutos se descartan como remakes. Las horas y fechas se convierten a `America/Santiago` antes de agrupar.
4. **Muestras pequeñas:** KPI 1 muestra un puntaje exploratorio desde 3 partidas, marca 3–4 como muestra corta y evalúa la meta desde 5. KPI 2, 3 y 5 conservan su mínimo de 10 partidas/participaciones. KPI 2 se presenta en bloques de cuatro horas y se compara con el winrate global del jugador. En KPI 4, la alerta de actividad sigue desde 7 partidas en el día; el winrate diario solo se informa desde 10.
5. **Puntaje compuesto de KPI 1:** se añadió la ponderación de winrate (60%), KDA normalizado a 100 al llegar a KDA 5 (25%) y cantidad de partidas normalizada a 100 al llegar a 50 (15%). El puntaje exploratorio parte de 3; `cumple_meta` conserva la regla separada de winrate > 55% desde 5 partidas.
6. **Calificación por rol de KPI 3:** se normalizan dos factores por rol entre 0 y 1 y se calcula `1 + 6 × promedio(factor1, factor2)`. Las referencias actuales están listadas en KPI 3 y son provisionales. JG usa `dragonKills + baronKills` del jugador como aproximación individual, no el total del equipo.
7. **KPI 5 y parche:** se calcula sobre los participantes de las partidas recolectadas y se agrupa por campeón, rol y parche (`gameVersion`), con umbral >52% y mínimo 10 participaciones. Se clasifica como **«Destacado en la muestra»**; no se identifica OTP ni se afirma que la muestra represente todo LAS.

**Estrategia y capacidad de recolección vigente (actualizado al 28-10-2026):** La extracción implementa paginación (`start` y `count`) consultando páginas de 20 partidas hasta un máximo de **100 partidas Solo/Duo por jugador** (`MAX_MATCHES_PER_PLAYER = 100`). La cohorte activa en Airflow (`riot_target_players`) monitorea 10 cuentas de nivel Diamante I/II de LAS, y el DAG de partidas delimita las peticiones a Riot únicamente para estos Riot IDs mediante consulta parametrizada en base de datos. La base conserva el historial acumulativo y registra todas las participaciones (`(match_id, puuid)`) deduplicadas, alcanzando más de 970 partidas en RAW y más de 9.000 participaciones en el Data Warehouse.
