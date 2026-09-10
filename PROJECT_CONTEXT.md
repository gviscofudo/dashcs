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
  Base confirmada de **septiembre 2026: 13.749** cuentas (total, todos los ejecutivos).
- **Objetivo de retención**: 98% (2% de baja máxima permitida sobre esa base).
  Escala de color: verde ≤2%, ámbar hasta 2.5%, rojo por encima.
- **Pico de bloqueos mensual**: los bloqueos no se dan gradualmente, se dan todos de
  golpe un día del mes (verificado: fue el día 8 en septiembre 2026, no el día 6 como se
  creía — el script de refresco lo detecta automáticamente comparando bloqueadas día a día).
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
  puntuales del panel desplegable. Si se toca este KPI, validar de nuevo contra
  `dropped_al_inicio_mes` (universo total de cuentas alguna vez dadas de baja por ejecutivo)
  antes de confiar el resultado.
- **"Cuentas faltantes para churn on target"** = bloqueadas hoy − (2% de la base).
  Si supera la cantidad de bloqueadas disponibles, el objetivo ya no es alcanzable ese mes
  aunque paguen todas — mostrarlo así, no ocultarlo.
- **Churn mensual** (para los gráficos de series históricas) = (bajas del mes − recuperadas
  del mes) / activas al inicio del mes. Verificado contra medición manual: ~2.9% en agosto 2026.
- **NRR**: MRR del día 1 vs. MRR día 31 de esa misma cohorte + recuperadas. Da bastante
  más bajo que la retención por cantidad de cuentas (~82% vs ~97%) — es esperable, no es
  un error, revisar igual si se pide.

## Estado de la automatización
NO se usa GitHub Actions con API key de Metabase (decisión tomada: no guardar esa key en
secrets de GitHub). El refresh lo corre Cowork manualmente/por tarea programada, usando el
conector de Metabase directo, y sube los cambios a mano porque esta sesión de Cowork no
tiene el repo `gviscofudo/dashcs` autorizado para hacer `git push` (pendiente: autorizar el
repo en la integración de GitHub de la cuenta de Claude). `scripts/refresh_data.py` documenta
la lógica de referencia pero no se ejecuta directamente por ese motivo.

Secciones que SÍ se actualizan en cada refresh: `retentionTarget` completo (bloqueadas,
recuperadas, dropped, pico del mes — pero NO la base día 1, ver arriba), los KPI de arriba
de todo del tablero ("Cuentas activas (hoy)", "Cuentas bloqueadas (hoy)", "Recupero de bajas
(hoy)", "Bloqueadas con intento de login (≤7 días)" — estos tres últimos con un panel
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
cuenta con `{n: nombre, u: url de HubSpot, l: fecha de último login "YYYY-MM-DD"}` (el
campo `l` es lo que hace que el panel muestre "último login: ..." en cada fila — los otros
accountLists no lo llevan).

**"Cuentas activas (hoy)"** (`data.snapshot[ejecutivo].today/prev.activasRaw/activasAdj`,
usado en `index.html` sólo `activasAdj`) — **IMPORTANTE, se pisó mal una vez, no repetir el
error**: NO es "activo hoy sin más" ni "activo desde el día 1 del mes". Es, en vivo, sobre
el alcance actual del ejecutivo (misma regla de exclusividad engagement/onboarding de
siempre):
  - `activasRaw` = `commercial_status`=ACTIVE hoy Y `sales_count > 0`.
  - `activasAdj` = `commercial_status`=ACTIVE hoy Y `sales_count > 50` (el mismo umbral que
    "base día 1", pero medido EN VIVO cada refresh, no congelado — por eso puede diferir
    bastante de `baseDia1` sin que sea un error).
  Reconstruido y validado el 10/9/2026 contra los valores históricos ya guardados en
  `snapshot[ejecutivo].prev` (coinciden exacto o casi exacto por ejecutivo). Hasta esa
  fecha se había usado por error una definición sin filtro de `sales_count` (contaba
  activas desde el día 1 del mes sin importar ventas), lo que infló el total ~13.370→13.713
  de un día a otro sin que hubiera movimiento real — el usuario lo detectó comparando contra
  el valor del día anterior. Si el número de "Cuentas activas (hoy)" pega un salto raro de
  un refresh a otro, sospechar primero de esto antes de asumir que es un problema de datos.

Secciones que siguen con el último dato cargado a mano (no automatizadas todavía): churn
histórico, NRR, composición, cohortes M3/M6/M12, curva de desbloqueo, N1/N2, gráfico de
graduación, "Solicitudes de baja". Extenderlo es el mismo patrón: una función por sección.

## Qué NO hacer
- No asumir que el pico de bloqueos es siempre el día 6 (era un supuesto incorrecto).
- No sumar "baja confirmada" + "bloqueadas" como poblaciones separadas del total.
- No usar el total de la compañía como base si el usuario filtró por ejecutivo — la base
  tiene que ser la de los ejecutivos seleccionados.
- No recalcular "base día 1" (`baseDia1` / `baseFija`) en un refresh que no sea el primero
  del mes — ver la nota de "IMPORTANTE" más arriba.
- No inventar una definición nueva para "Cuentas activas (hoy)" (`activasRaw`/`activasAdj`)
  sin validarla contra `snapshot[ejecutivo].prev` — ver la nota de "Cuentas activas (hoy)"
  más arriba. La fórmula correcta usa `sales_count > 0` (raw) / `sales_count > 50` (adj).
- No calcular "Recupero de bajas" como "bloqueada ayer, activa hoy" — tiene que ser
  `commercial_status`=DROPPED al día 1 del mes Y activa (no bloqueada) hoy. Ver la nota de
  "Recupero de bajas (hoy)" más arriba.
