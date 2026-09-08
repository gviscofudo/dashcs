# Tablero de Engagement y Onboarding — Argentina

Tablero de retención, churn y objetivo mensual para los equipos de Engagement y Onboarding de Fudo Argentina.

## Estructura

- `index.html` — el tablero. No hay que tocarlo para actualizar datos.
- `data_blob.js` — todos los datos del tablero, en un `const DATA = {...}` que `index.html` carga por separado.
- `scripts/refresh_data.py` — se conecta a Metabase, recalcula la sección **"Objetivo de retención"** y pisa esa parte de `data_blob.js`, dejando el resto (churn, NRR, composición, cohortes, N1/N2, curva histórica de desbloqueo) tal como estaba.
- `.github/workflows/refresh.yml` — corre ese script todos los días a las 09:00 (Argentina) y commitea el `data_blob.js` actualizado.

## ⚠️ Automatización parcial

Por ahora **solo se actualiza en vivo la sección "Objetivo de retención"** (la barra de baja, el indicador de cuentas faltantes, y la comparación con el mes anterior). El resto del tablero — churn mensual, NRR, composición por plan, cohortes M3/M6/M12, curva histórica de desbloqueo, KPIs de arriba — sigue mostrando el último dato que se cargó a mano en esta conversación.

Extender la automatización al resto es el mismo patrón (una función en `refresh_data.py` por sección, usando las consultas SQL ya validadas), pero no estaba armado en esta entrega. Si querés que sigamos completándolo, avisá.

## Configurar la actualización automática

1. Conseguí un **API key de Metabase**: Admin → Settings → Authentication → API Keys → Create API Key.
2. En el repo de GitHub: **Settings → Secrets and variables → Actions → New repository secret**, y cargá:
   - `METABASE_URL` → ej. `https://metabase.fu.do` (sin `/api` al final)
   - `METABASE_API_KEY` → la key del paso 1
   - `METABASE_DB_ID` → `4` (el id de base de datos que usamos en todo este tablero; confirmalo en Metabase si no estás seguro)
3. Listo — el workflow corre solo todos los días. También podés dispararlo a mano desde la pestaña **Actions** del repo → "Actualizar tablero" → "Run workflow".

## Publicarlo con GitHub Pages

1. Creá un repositorio nuevo en GitHub (privado si los datos son sensibles — con cuenta gratuita, Pages en repo privado no queda público sin loguearse; necesitás plan Pro/Team/Enterprise para eso).
2. Subí todo el contenido de esta carpeta (`index.html`, `data_blob.js`, `scripts/`, `.github/`) a la raíz del repo.
3. **Settings → Pages** → Source: **Deploy from a branch**, branch `main`, carpeta `/ (root)` → Save.
4. En un par de minutos vas a tener la URL pública (`https://tu-usuario.github.io/nombre-repo/`).

## Sobre "en vivo" (sin esperar al cron diario)

Una versión realmente en vivo (que consulte Metabase en el momento en que alguien abre la página, no una vez por día) necesitaría exponer credenciales de Metabase en el navegador — no es seguro para una página pública, ni siquiera privada. La alternativa segura sería usar los **public links de Metabase** (compartir cada pregunta/dashboard como pública desde Metabase, sin necesidad de API key) y que el HTML haga `fetch()` directo a esas URLs públicas al cargar. Si te interesa esa vía, avisame — implica primero guardar estas consultas como preguntas en Metabase y activarles el link público.
