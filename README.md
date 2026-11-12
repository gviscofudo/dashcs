# Central de llamados – Fudo CS

Panel para la campaña de retención sobre cuentas de Argentina bloqueadas en Dash con estado comercial activo, más cuentas sumadas a mano con etiqueta (por ejemplo «Riesgo alto»).

- Frontend: `index.html` (página estática, se publica con GitHub Pages).
- Backend: Supabase, proyecto «Central de llamados CS» (`rgbnwwppkrcbyolegnpi`).
  - Tablas: `cuentas`, `gestiones`, `llamados`, `equipo`, `cuentas_extra` (cuentas sumadas a mano), `sync_log`, y el histórico de campañas cerradas (`llamados_historico`, `gestiones_historico`).
  - Edge Functions: `sync-cuentas` (trae las cuentas de HubSpot cada hora), `sync-llamadas-intercom`, `contactos`, `hubspot-llamado`, `planilla-activacion`, `usuarios`.
- Acceso con mail y contraseña. Los usuarios los crea un líder desde «Equipo y usuarios».

La clave que aparece en `index.html` es la clave pública (publishable) de Supabase: está pensada para estar en el navegador. Los tokens de HubSpot e Intercom viven solo como secretos de Supabase, nunca en este repo.
