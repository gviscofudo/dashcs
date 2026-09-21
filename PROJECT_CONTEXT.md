# Contexto del proyecto — Tablero Engagement/Onboarding Argentina

## Qué es esto
Tablero HTML autocontenido (index.html + data_blob.js) con métricas de retención/churn
para los equipos de Engagement y Onboarding de Fudo Argentina. Se publica con GitHub Pages.

## Roster de ejecutivos (fijo, no cambia sin avisar)
- Engagement: Brizeth Avalos, Exequiel Galarza, Gabriel Visco, Carla A.
- Onboarding: Luis González, Florencia Fanego, Camila Ferretti, Camila Mettica
- Son mutuamente excluyentes: Engagement = tiene engagement_executive asignado.
  Onboarding = tiene onboarding_executive pero NO engagement_executive todavía.

## Fuente de datos
Metabase, database_id=4 (fudata / fudata_v2 en ClickHouse). Cuentas de Argentina,
cruzadas con fudata_v2.hubspot_accounts por engagement_executive/onboarding_executive.

**IMPORTANTE — tabla correcta para reconstrucción histórica / point-in-time (18/9/2026)**:
para cualquier lookup histórico (ASOF join a "cómo estaba esta cuenta tal día"), la tabla
correcta es **`fudata.accounts`** (schema viejo, con `valid_from`/`valid_to`/`current`/
`commercial_status`/`status`/`country_normalized`), **NO** `fudata_v2.accounts`. Usar la
tabla v2 para esto da resultados visiblemente mal (probado: `bloqueadasPico` reconstruida
con `fudata_v2.accounts` salió ~27% más baja que con `fudata.accounts`). `fudata_v2` sólo
se usa para `hubspot_accounts` (datos de CRM: ejecutivo asignado, sales_count, nombre,
hubspot_registry_id, last_login_date, drop_date).

Patrón de ASOF JOIN que funciona en ClickHouse (ojo, es quisquilloso): la condición de
desigualdad tiene que comparar dos columnas de tabla, no una columna contra una constante
calculada. Si se necesita comparar contra `now()` o `toStartOfMonth(now()) + toIntervalDay(N)`,
hay que materializar esos timestamps primero en un CTE chico (`pts`) y hacer CROSS JOIN
antes del ASOF, no ponerlos directo en el ON:
```sql
pts AS (SELECT toStartOfMonth(now()) AS ms1, now() AS nn, now() - toIntervalDay(1) AS yd),
grid AS (SELECT s.*, p.ms1, p.nn, p.yd FROM scoped s CROSS JOIN pts p),
enr AS (
  SELECT g.*, hs.cst AS cst_ms1, hn.cst AS cst_nn, hn.st AS st_nn
  FROM grid g
  ASOF LEFT JOIN hist hs ON g.aid = hs.account_id AND hs.valid_from <= g.ms1
  ASOF LEFT JOIN hist hn ON g.aid = hn.account_id AND hn.valid_from <= g.nn
)
```
`scripts/refresh_data.py` en el repo tiene las 4 queries de referencia completas (detección
de pico, base día 1, bloqueadas/recuperadas/dropped, comparación mes anterior) con este
patrón ya resuelto — es la fuente de verdad para la lógica SQL exacta.

## Definiciones de negocio ya validadas (no recalcular desde cero)
- **Base "día 1"** = cuentas activas el día 1 del mes a las 00:01hs, con **más de 50 ventas**
  (hubspot_accounts.sales_count > 50). Ojo: sales_count no tiene historial propio (no hay
  forma de saber su valor exacto el día 1), así que hay ~1% de margen de error contra un
  corte manual.
  **IMPORTANTE — se congela una sola vez por mes, NO se recalcula en cada refresh.** Como
  sales_count no tiene historial, sólo se puede leer con su valor ACTUAL — si se recalculara
  todos los días, la base iría subiendo sola a medida que más cuentas cruzan las 50 ventas
  durante el mes (sales_count es acumulativo). El refresh diario/dos-veces-al-día actualiza
  bloqueadas, recuperadas, dropped, etc. contra esta base fija, pero nunca reescribe
  `retentionTarget.progress[ejecutivo].baseDia1` ni `retentionTarget.baseFija` una vez
  fijados para el mes. Sólo se vuelve a calcular al iniciar un mes nuevo.
  Base confirmada de **septiembre 2026: 13.749** cuentas (total, todos los ejecutivos, versión
  +50 ventas). La misma base sin filtro de ventas ("todas las cuentas") también está congelada
  por mes en `baseFijaAll` (13.943 en septiembre 2026) y en `baseDia1All` por ejecutivo — mismo
  motivo y misma regla de "no recalcular", aunque técnicamente esta variante no depende de
  sales_count y por eso no arrastra el mismo drift (se congela igual, por consistencia con la
  base +50 y porque no está documentada como parte de lo que refresca `refresh_data.py`).
- **Objetivo de retención**: 98% (2% de baja máxima permitida sobre esa base).
  Escala de color: verde ≤2%, ámbar hasta 2.5%, rojo por encima.
- **Pico de bloqueos mensual**: los bloqueos no se dan gradualmente, se dan todos de
  golpe un día del mes (verificado: fue el día 8 en septiembre 2026, no el día 6 como se
  creía — el script de refresco lo detecta automáticamente comparando bloqueadas día a día,
  re-verificado el 18/9/2026 y el 20/9/2026, sigue dando día 8).
- **IMPORTANTE — 20/9/2026: los campos "actividad" (bloqueadasPico, bloqueadasHoy,
  bloqueadasMismoDiaMesAnterior, etc.) pueden saltar bastante de un refresh a otro para los
  ejecutivos grandes (Brizeth Avalos, Exequiel Galarza) sin que sea un error.** Se investigó
  un salto grande el 20/9 (`bloqueadasPico` de Brizeth bajó de 335 a 261, `bloqueadasMismoDiaMesAnterior`
  de 354 a 264) — la base (`baseDia1`/`baseMismoDiaMesAnterior`) apenas se movió (6722→6722 frozen,
  la versión recalculada a mano para diagnóstico dio 6501, y `baseMismoDiaMesAnterior` fresh dio
  6611 vs 6608 guardado — diferencias chicas), así que no era drift de `sales_count`. Se confirmó
  contra `hubspot_accounts.engagement_executive_assign_date` que hubo reasignación de cuentas entre
  Brizeth y Exequiel el 14-18/9/2026 (30-40 cuentas por día cada uno). Como el `SCOPED_CTE` de
  `refresh_data.py` define el universo de cuentas de cada ejecutivo por su asignación ACTUAL (no por
  quién era el ejecutivo en la fecha histórica que se está midiendo), una cuenta reasignada entra o
  sale de TODOS los cálculos históricos de ese ejecutivo de un día para el otro, aunque la fecha
  medida (pico, mismo día mes anterior) ya haya pasado. Esto es consistente con el diseño ya usado
  para `snapshot.prev`/`activasRaw` (que ya mostraba saltos grandes para ejecutivos con poca cartera)
  — no es un bug nuevo, es una propiedad del método, y coincide con la metodología validada de
  `refresh_data.py`. No recalcular "a mano" para compensarlo; si un salto parece demasiado grande
  para ser sólo reasignación, cruzar contra `engagement_executive_assign_date` antes de descartar
  el refresh (como se hizo acá).
- **Bajas confirmadas**: recién existen a fin de mes, de las bloqueadas que no pagaron.
  No sumar baja confirmada + bloqueadas como si fueran poblaciones separadas — las
  bloqueadas SON parte de la misma base, no se agregan aparte.
- **"Recupero de bajas (hoy)"** (KPI de arriba, `data.recover[ejecutivo].today/yesterday` y
  `data.accountLists.recuperoBajas`) — **IMPORTANTE, se calculó mal una vez, no repetir el
  error**: el criterio es `commercial_status`=**DROPPED** al día 1 del mes (`cst_ms1`) Y
  `commercial_status`=ACTIVE (con `status`!=BLOCKED) HOY — es decir, cuentas que estaban DE
  BAJA (no sólo bloqueadas) al inicio del mes y que se reactivaron completamente. NO es lo
  mismo que "estaba bloqueada ayer y hoy no" — esa definición (usada por error el 10/9/2026)
  cuenta cualquier bloqueo-y-desbloqueo dentro del mes aunque la cuenta nunca haya llegado a
  DROPPED, e infló el número de 24 a 42 cuentas. El usuario lo detectó revisando cuentas
  puntuales del panel desplegable. Reverificado el 18/9/2026: el resultado de esta fórmula
  coincidió exacto (17 de 17 para Brizeth Avalos, ambas variantes raw/adj) contra el valor ya
  guardado del refresh anterior, buena señal de que la fórmula está estable.
- **"Cuentas faltantes para churn on target"** = bloqueadas hoy − (2% de la base).
  Si supera la cantidad de bloqueadas disponibles, el objetivo ya no es alcanzable ese mes
  aunque paguen todas — mostrarlo así, no ocultarlo.
- **Churn mensual** (para los gráficos de series históricas) = (bajas del mes − recuperadas
  del mes) / activas al inicio del mes. Verificado contra medición manual: ~2.9% en agosto 2026.
- **NRR**: MRR del día 1 vs. MRR día 31 de esa misma cohorte + recuperadas. Da bastante
  más bajo que la retención por cantidad de cuentas (~82% vs ~97%) — es esperable, no es
  un error, revisar igual si se pide.

## El switch "todas las cuentas" / "+50 ventas" (`salesView`) y el sufijo de cada campo
El tablero tiene un switch arriba que cambia TODOS los KPI, el objetivo de retención y los
paneles de cuentas entre "todas las cuentas" (default) y "sólo +50 ventas". Cada número vive
DOS VECES en `data_blob.js`, y qué campo es cuál depende del TIPO de campo (esto no estaba
documentado antes del 18/9/2026 y hay que tenerlo claro para no pisar el campo equivocado):

- **Campos de "base"** (`baseDia1`, `baseMismoDiaMesAnterior`, y sus totales `baseFija`):
  el campo SIN sufijo ya es la versión **+50 ventas** (la definición de negocio original).
  La versión "todas las cuentas" vive en el campo con sufijo **`All`**
  (`baseDia1All`, `baseMismoDiaMesAnteriorAll`, `baseFijaAll`).
- **Campos de "actividad"** (`bloqueadasPico`, `recuperadasDesdePico`, `siguenBloqueadas`,
  `yaCayeronDePico`, `droppedYa`, `bloqueadasHoy`, `bloqueadasAyer`, `droppedAyer`,
  `bloqueadasMismoDiaMesAnterior`, y los `bloqueadas`/`bloqueadasAdj` de `snapshot`, y los
  `today`/`todayAdj`/`yesterday`/`yesterdayAdj` de `recover`): el campo SIN sufijo es la
  versión **todas las cuentas** (sin filtro de sales_count). La versión +50 ventas vive en
  el campo con sufijo **`Adj`**.
- La lógica está en `index.html`, funciones `baseField(name)` / `actField(name)` (buscar
  `campos "base"` en el archivo). Cualquier sección nueva que agregue un número tiene que
  decidir de entrada si es un campo "base" o "actividad" y seguir esta misma convención.
- Para las `accountLists` (bloqueadasHoy, recuperoBajas, bloqueadasConLogin) no hay listas
  separadas por sales_count: cada cuenta lleva un flag `s` (true si `sales_count > 50`), y el
  filtrado por switch se hace en el cliente (`acc.s === true` cuando `salesView==='adj'`).

## Estado de la automatización
NO se usa GitHub Actions con API key de Metabase (decisión tomada: no guardar esa key en
secrets de GitHub, y además el usuario no tiene una API key de Metabase disponible).

**IMPORTANTE — 11/9/2026: se migró la publicación "en vivo" de GitHub Pages a un Artifact de
Claude, de forma PROVISORIA**, porque el `git push` a `gviscofudo/dashcs` está bloqueado por un
bug confirmado y todavía abierto en el proxy de git de Cowork/Claude Code Remote (no es un tema
de permisos de GitHub — se probó instalar la GitHub App con acceso a "All repositories" y el
push sigue fallando con "not in this session's authorized repository set"; ver issues públicos
anthropics/claude-code #76248 y #84581, sin solución ni fecha; reconfirmado el 18/9/2026, mismo
error exacto). Mientras ese bug siga abierto:

- El tablero en vivo es el Artifact publicado en:
  **https://claude.ai/code/artifact/5315b6d7-e6a8-4e1a-a18c-693b1d6196ac**
  (privado por ahora, compartido con la organización; el usuario decide si lo comparte más
  ampliamente desde el menú de compartir del Artifact). Es un artifact multi-archivo:
  `index.html` (sin las etiquetas `<html>/<head>/<body>` porque el Artifact les pone su
  propio esqueleto — esto es normal, no es una versión distinta) + `data_blob.js` como
  archivo aparte, igual que en el repo.
- Cada refresh debe: actualizar `data_blob.js` en `/home/claude/github-deploy/data_blob.js`
  (o el working directory de la sesión) como siempre, y ADEMÁS republicar el Artifact con
  `Artifact({file_path: ".../index.html", files: {"data_blob.js": ".../data_blob.js"}, url:
  "https://claude.ai/code/artifact/5315b6d7-e6a8-4e1a-a18c-693b1d6196ac"})` para que quede
  actualizado — pasando siempre `url` (si no, se crea un artifact nuevo en vez de actualizar
  este). Antes de publicar, la sesión tiene que haber "visto" la versión actual del artifact
  (leerla con `action: "read"`) o el publish es rechazado — no es necesario si la sesión ya
  publicó en esa misma conversación antes.
- El repo de GitHub (`gviscofudo/dashcs`) sigue existiendo como respaldo del código y se le
  sigue haciendo `git commit` en cada refresh (aunque el `push` falle) — así el historial local
  queda prolijo por si se resuelve el bug o se decide reintentar el push más adelante. Si el
  push vuelve a fallar, NO reintentarlo en loop: es el mismo bug conocido, no un problema de
  permisos que se arregle solo. Avisar al usuario en una línea y seguir.
- Cuando el bug del proxy se resuelva (o el usuario decida volver a GitHub Pages), esta sección
  hay que actualizarla y decidir si se mantiene el Artifact como espejo o se vuelve 100% a
  GitHub Pages.
- **IMPORTANTE — 18/9/2026: en cada refresh, además de lo anterior, hay que guardar el set
  completo de archivos.** Pedido explícito de Gabi: quiere siempre una copia completa, no sólo
  el Artifact.
  - **Si la sesión tiene la carpeta local `dashcs-update` conectada (device bridge,
    `/Users/gabrielvisco/Desktop/dashcs-update` en la Mac de Gabi)**: crear ahí una subcarpeta
    `dashcs-update-<fecha de hoy YYYY-MM-DD>` con el set completo (`index.html`, `data_blob.js`
    ya actualizado, `PROJECT_CONTEXT.md`, `README.md`, `refresh_data.py`,
    `requirements.txt`), usando `device_stage_files`/`device_commit_files` (o `device_bash` si
    está disponible ese día — puede aparecer y desaparecer de una llamada a otra, no asumir que
    sigue disponible). Esta es la entrega preferida cuando la carpeta está conectada.
  - **Si no hay carpeta conectada esa corrida** (por ejemplo la tarea programada corre sin
    vínculo a la computadora ese día): fallback a crear `ActDashCS_<fecha>` en el working
    directory de la sesión y mandarlo con `SendUserFile`.
  - La tarea programada diaria (8am Argentina, ver más abajo) fue creada desde una conversación
    con la carpeta ya conectada específicamente para que quede vinculada a la computadora — si
    en algún momento deja de tener ese vínculo, avisar al usuario en vez de asumir que va a
    seguir funcionando igual.

`scripts/refresh_data.py` documenta la lógica de referencia (las 4 queries SQL exactas para
`retentionTarget`) pero no se ejecuta directamente como script (el refresh real lo hace Cowork
con SQL directo contra el conector de Metabase, replicando esa misma lógica más las extensiones
de abajo). El único ajuste que Cowork hace sobre lo que haría el script tal cual: el script
recalcularía `baseDia1`/`baseFija` en cada corrida (no tiene la regla de congelamiento) —
Cowork sabe que NO hay que tocar esos campos, sólo el resto de `retentionTarget.progress`.

Secciones que SÍ se actualizan en cada refresh: `retentionTarget` completo (bloqueadas,
recuperadas, dropped, pico del mes, comparación mes anterior — pero NO la base día 1, ver
arriba, en ninguna de sus dos variantes All/no-All), los KPI de arriba de todo del tablero
("Cuentas activas (hoy)" → `data.snapshot`, "Cuentas bloqueadas (hoy)" → mismo dato que
`bloqueadasHoy` de `retentionTarget`, "Recupero de bajas (hoy)" → `data.recover` +
`data.accountLists.recuperoBajas`, "Bloqueadas con intento de login (≤7 días)" →
`data.accountLists.bloqueadasConLogin`, cada uno de estos tres últimos con un panel
desplegable con buscador que lista las cuentas puntuales, linkeadas a HubSpot vía
`hubspot_accounts.hubspot_registry_id` y el portal 5096255), y "NRR último mes" / "NRR
promedio" (calculados en el cliente a partir de `execs[ejecutivo].months`, no requieren
query nueva). OJO: `hubspot_registry_id` es el ID del objeto **Deal** en HubSpot, NO el de
la Company — verificado contra 4 cuentas distintas vía la API de HubSpot. La URL correcta es
`https://app.hubspot.com/contacts/5096255/record/0-3/{hubspot_registry_id}` (0-3 = Deal;
0-2 sería Company y da un link roto/"not found").

**"Bloqueadas con intento de login (≤7 días)"**: cuentas con `commercial_status`=ACTIVE
(dentro de la base) y `status`=BLOCKED hoy (mismo criterio que "bloqueadas hoy"), Y
`hubspot_accounts.last_login_date >= today() - 7`. Señal de cuentas que quieren volver
pese a estar bloqueadas. Va en `data.accountLists.bloqueadasConLogin[ejecutivo]`, cada
cuenta con `{n: nombre, u: url de HubSpot, s: sales_count>50, l: fecha de último login
"YYYY-MM-DD"}` (el campo `l` es lo que hace que el panel muestre "último login: ..." en
cada fila — los otros accountLists no lo llevan, pero sí llevan `s`).

**"Cuentas activas (hoy)"** (`data.snapshot[ejecutivo].today/prev.activasRaw/activasAdj`) —
**IMPORTANTE, se pisó mal una vez, no repetir el error**: NO es "activo hoy sin más" ni
"activo desde el día 1 del mes". Es, en vivo, sobre el alcance actual del ejecutivo (misma
regla de exclusividad engagement/onboarding de siempre):
  - `activasRaw` = `commercial_status`=ACTIVE hoy Y `sales_count > 0`.
  - `activasAdj` = `commercial_status`=ACTIVE hoy Y `sales_count > 50` (el mismo umbral que
    "base día 1", pero medido EN VIVO cada refresh, no congelado — por eso puede diferir
    bastante de `baseDia1` sin que sea un error).
  `snapshot[ejecutivo].prev` NO es "ayer" — es el mismo cálculo pero al día equivalente del
  MES ANTERIOR (mismo offset desde el pico), para el KPI "vs. mismo día mes anterior". Su
  `bloqueadas`/`bloqueadasAdj` coincide con `bloqueadasMismoDiaMesAnterior`/`...Adj` de
  `retentionTarget.progress` (son el mismo número, expuesto en dos lugares). Reconstruido y
  re-validado el 18/9/2026: la fórmula de `activasRaw`/`activasAdj` "hoy" dio exactamente el
  mismo valor que el "hoy" guardado el día anterior para varios ejecutivos (ej. Brizeth Avalos
  6408/6348 ambos días), buena señal de estabilidad.

Secciones que siguen con el último dato cargado a mano (no automatizadas todavía): churn
histórico, NRR, composición, cohortes M3/M6/M12, curva de desbloqueo, N1/N2, gráfico de
graduación, "Solicitudes de baja". Extenderlo es el mismo patrón: una función por sección.

**IMPORTANTE**: cada vez que se carga/actualiza a mano alguna de estas secciones (no el
refresh automático de retentionTarget/snapshot/recover/accountLists), actualizar también
`data.manualDataUpdated` con la fecha de ese día (formato "YYYY-MM-DD"). El pie del tablero
muestra "Objetivo de retención actualizado: [fecha/hora de lastRefreshed] · resto del
tablero actualizado: [fecha de manualDataUpdated]" — si no se actualiza este campo al tocar
datos manuales, el pie queda desactualizado y deja de ser confiable.

## Tarea programada
Hay una tarea programada diaria ("Refresh diario ActDashCS", trig_01XcZHUCTwDBKZSusBT8gzYJ)
que corre todos los días a las 8:00 AM hora Argentina (`0 11 * * *` UTC), creada el 18/9/2026
desde una conversación con la carpeta `dashcs-update` ya conectada para que quede vinculada a
esa computadora. Hace el refresh completo (retentionTarget + snapshot + recover +
accountLists), republica el Artifact, comitea localmente (sin reintentar el push si falla), y
guarda el set completo de archivos en la carpeta conectada (o por `SendUserFile` si ese día no
hay carpeta conectada).

**20/9/2026**: esta corrida programada NO tuvo la carpeta `dashcs-update` conectada (`connectedFolders` vacío al llamar `get_device_info`) — se usó el fallback `SendUserFile` con `ActDashCS_2026-09-20`. Si esto se repite en corridas sucesivas, avisar a Gabi: puede significar que el vínculo de la tarea programada con la Mac se cortó, no asumir que se resuelve solo.

## Qué NO hacer
- No asumir que el pico de bloqueos es siempre el día 6 (era un supuesto incorrecto).
- No sumar "baja confirmada" + "bloqueadas" como poblaciones separadas del total.
- No usar el total de la compañía como base si el usuario filtró por ejecutivo — la base
  tiene que ser la de los ejecutivos seleccionados.
- No recalcular "base día 1" (`baseDia1`/`baseFija` y sus variantes `baseDia1All`/
  `baseFijaAll`) en un refresh que no sea el primero del mes — ver la nota de "IMPORTANTE"
  más arriba.
- No usar `fudata_v2.accounts` para reconstrucción histórica point-in-time — usar
  `fudata.accounts` (ver sección "Fuente de datos" más arriba). Da resultados mal (~27% de
  error visto en la práctica).
- No confundir la convención de sufijos `All`/`Adj` — ver la sección dedicada más arriba.
  Los campos "base" (sin sufijo = +50 ventas, sufijo `All` = todas) usan la convención
  INVERSA a los campos "actividad" (sin sufijo = todas, sufijo `Adj` = +50 ventas).
- No inventar una definición nueva para "Cuentas activas (hoy)" (`activasRaw`/`activasAdj`)
  sin validarla contra `snapshot[ejecutivo].prev` — ver la nota de "Cuentas activas (hoy)"
  más arriba. La fórmula correcta usa `sales_count > 0` (raw) / `sales_count > 50` (adj).
- No calcular "Recupero de bajas" como "bloqueada ayer, activa hoy" — tiene que ser
  `commercial_status`=DROPPED al día 1 del mes Y activa (no bloqueada) hoy. Ver la nota de
  "Recupero de bajas (hoy)" más arriba.
- No olvidar guardar el set completo de archivos en cada refresh (carpeta conectada
  `dashcs-update` si está disponible, si no `ActDashCS_<fecha>` + `SendUserFile`) — esto es
  un paso fijo, no algo que sólo se hace si lo piden esa vez puntual.
