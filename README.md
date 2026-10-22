# Central de llamados – Fudo CS

Panel para la campaña de retención sobre cuentas de Argentina bloqueadas en Dash con estado comercial activo.

- Frontend: `index.html` (página estática, se publica con GitHub Pages).
- Backend: Supabase, proyecto «Central de llamados CS» (`rgbnwwppkrcbyolegnpi`).
  - Tablas: `cuentas`, `gestiones`, `llamados`, `equipo`, `sync_log`.
  - Edge Functions: `sync-cuentas` (trae las cuentas de HubSpot, corre cada hora de 8 a 21 hs), `contactos` (contactos de HubSpot + Intercom), `hubspot-llamado` (crea nota y tarea en HubSpot).
- Acceso con mail y contraseña. Los usuarios los crea un líder desde el botón «Equipo» del panel (Edge Function `usuarios`), y solo entran mails @fu.do activos en la tabla `equipo`.

La clave que aparece en `index.html` es la clave pública (publishable) de Supabase: está pensada para estar en el navegador. Los tokens de HubSpot e Intercom viven solo como secretos de Supabase, nunca en este repo.

Para cambiar las propuestas comerciales o los motivos de baja, editá las listas `PROPUESTAS` y `MOTIVOS` al principio del script en `index.html`.
