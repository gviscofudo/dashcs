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
- **Objetivo de retención**: 98% (2% de baja máxima permitida sobre esa base).
  Escala de color: verde ≤2%, ámbar hasta 2.5%, rojo por encima.
- **Pico de bloqueos mensual**: los bloqueos no se dan gradualmente, se dan todos de
  golpe un día del mes (verificado: fue el día 8 en septiembre 2026, no el día 6 como se
  creía — el script de refresco lo detecta automáticamente comparando bloqueadas día a día).
- **Bajas confirmadas**: recién existen a fin de mes, de las bloqueadas que no pagaron.
  No sumar baja confirmada + bloqueadas como si fueran poblaciones separadas — las
  bloqueadas SON parte de la misma base, no se agregan aparte.
- **"Cuentas faltantes para churn on target"** = bloqueadas hoy − (2% de la base).
  Si supera la cantidad de bloqueadas disponibles, el objetivo ya no es alcanzable ese mes
  aunque paguen todas — mostrarlo así, no ocultarlo.
- **Churn mensual** (para los gráficos de series históricas) = (bajas del mes − recuperadas
  del mes) / activas al inicio del mes. Verificado contra medición manual: ~2.9% en agosto 2026.
- **NRR**: MRR del día 1 vs. MRR día 31 de esa misma cohorte + recuperadas. Da bastante
  más bajo que la retención por cantidad de cuentas (~82% vs ~97%) — es esperable, no es
  un error, revisar igual si se pide.

## Estado de la automatización
`scripts/refresh_data.py` + `.github/workflows/refresh.yml` actualizan automáticamente
UNA SOLA sección del tablero (Objetivo de retención) una vez por día, vía GitHub Actions.
El resto del tablero (churn histórico, NRR, composición, cohortes M3/M6/M12, curva de
desbloqueo, KPIs de arriba) sigue con el último dato cargado a mano — no está automatizado
todavía. Extenderlo es el mismo patrón: una función por sección en refresh_data.py.

## Qué NO hacer
- No asumir que el pico de bloqueos es siempre el día 6 (era un supuesto incorrecto).
- No sumar "baja confirmada" + "bloqueadas" como poblaciones separadas del total.
- No usar el total de la compañía como base si el usuario filtró por ejecutivo — la base
  tiene que ser la de los ejecutivos seleccionados.
