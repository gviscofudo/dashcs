#!/usr/bin/env python3
"""
Refresca el tablero de Engagement/Onboarding Argentina con datos en vivo de Metabase.

Requiere las variables de entorno:
  METABASE_URL      ej. https://metabase.fu.do
  METABASE_API_KEY  API key de Metabase (Admin > Settings > Authentication > API Keys)
  METABASE_DB_ID     id de la base de datos en Metabase (por default 4, el mismo usado en todo este tablero)

Uso:
  python scripts/refresh_data.py
Escribe el resultado en index.html (en la raíz del repo), listo para GitHub Pages.
"""
import os
import sys
import json
import datetime
import requests

METABASE_URL = os.environ["METABASE_URL"].rstrip("/")
METABASE_API_KEY = os.environ["METABASE_API_KEY"]
DATABASE_ID = int(os.environ.get("METABASE_DB_ID", "4"))

HEADERS = {"x-api-key": METABASE_API_KEY, "Content-Type": "application/json"}

ENGAGEMENT_EXECS = ["Brizeth Avalos", "Exequiel Galarza", "Gabriel Visco", "Carla A."]
ONBOARDING_EXECS = ["Luis González", "Florencia Fanego", "Camila Ferretti", "Camila Mettica"]
ALL_EXECS = ENGAGEMENT_EXECS + ONBOARDING_EXECS
TEAM_OF = {e: "engagement" for e in ENGAGEMENT_EXECS}
TEAM_OF.update({e: "onboarding" for e in ONBOARDING_EXECS})
COLORS = {
    "Brizeth Avalos": "#2a78d6", "Exequiel Galarza": "#eb6834",
    "Gabriel Visco": "#1baf7a", "Carla A.": "#a259d9",
    "Luis González": "#d94f70", "Florencia Fanego": "#c99a2e",
    "Camila Ferretti": "#4fa8c9", "Camila Mettica": "#8a6d3b",
}
TARGET_RETENTION = 0.98

SCOPED_CTE = """
WITH cur0 AS (SELECT DISTINCT account_id, country_normalized FROM fudata.accounts WHERE current=1),
eng AS (
  SELECT c.account_id AS aid, h.engagement_executive AS ejec, 'engagement' AS team, h.sales_count AS sc
  FROM cur0 c LEFT JOIN fudata_v2.hubspot_accounts h ON c.account_id=h.account_id
  WHERE c.country_normalized='Argentina' AND h.engagement_executive IN ({eng_list})
),
onb AS (
  SELECT c.account_id AS aid, h.onboarding_executive AS ejec, 'onboarding' AS team, h.sales_count AS sc
  FROM cur0 c LEFT JOIN fudata_v2.hubspot_accounts h ON c.account_id=h.account_id
  WHERE c.country_normalized='Argentina' AND h.engagement_executive IS NULL
    AND h.onboarding_executive IN ({onb_list})
),
scoped AS (SELECT aid, ejec, team, sc FROM eng UNION ALL SELECT aid, ejec, team, sc FROM onb)
""".format(
    eng_list=",".join(f"'{e}'" for e in ENGAGEMENT_EXECS),
    onb_list=",".join(f"'{e}'" for e in ONBOARDING_EXECS),
)


def run_sql(sql: str):
    resp = requests.post(
        f"{METABASE_URL}/api/dataset",
        headers=HEADERS,
        json={"database": DATABASE_ID, "type": "native", "native": {"query": sql}},
        timeout=120,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("status") == "failed":
        raise RuntimeError(f"Metabase query failed: {data.get('error')}")
    cols = [c["name"] for c in data["data"]["cols"]]
    rows = data["data"]["rows"]
    return [dict(zip(cols, r)) for r in rows]


def detect_peak_day():
    """Encuentra el día del mes en curso donde más saltó la cantidad de bloqueadas (el 'pico' de bloqueo mensual)."""
    sql = SCOPED_CTE + """
    , hist AS (SELECT account_id AS aid2, valid_from AS vf, commercial_status AS cst, status AS st FROM fudata.accounts WHERE account_id IN (SELECT aid FROM scoped)),
    day_offsets AS (SELECT arrayJoin(range(0,15)) AS off),
    grid AS (SELECT s.aid AS aid9, d.off AS off9 FROM scoped s CROSS JOIN day_offsets d),
    enr AS (
      SELECT g.aid9, g.off9, h.cst AS cst_at, h.st AS st_at
      FROM grid g ASOF LEFT JOIN hist h ON g.aid9 = h.aid2 AND h.vf <= (toStartOfMonth(now()) + toIntervalDay(g.off9))
    )
    SELECT off9 AS dia, countIf(cst_at='ACTIVE' AND st_at='BLOCKED') AS bloqueadas
    FROM enr GROUP BY dia ORDER BY dia
    """
    rows = run_sql(sql)
    best_off, best_jump = 1, -1
    for i in range(1, len(rows)):
        jump = rows[i]["bloqueadas"] - rows[i - 1]["bloqueadas"]
        if jump > best_jump:
            best_jump = jump
            best_off = rows[i]["dia"]
    return best_off  # días desde el inicio del mes


def get_base_dia1_por_exec():
    """Base = activas al día 1 del mes con más de 50 ventas (definición de negocio dada por el equipo)."""
    sql = SCOPED_CTE + """
    , hist AS (SELECT account_id AS aid2, valid_from AS vf, commercial_status AS cst FROM fudata.accounts WHERE account_id IN (SELECT aid FROM scoped)),
    grid AS (SELECT s.aid AS aid9, s.ejec AS ejec9, s.team AS team9, s.sc AS sc9 FROM scoped s),
    enr AS (SELECT g.aid9, g.ejec9, g.team9, g.sc9, h.cst AS cst_ms1
            FROM grid g ASOF LEFT JOIN hist h ON g.aid9 = h.aid2 AND h.vf <= (toStartOfMonth(now()) + toIntervalMinute(1)))
    SELECT team9 AS team, ejec9 AS ejec, countIf(cst_ms1='ACTIVE' AND sc9 > 50) AS base
    FROM enr GROUP BY team, ejec ORDER BY team, ejec
    """
    return {r["ejec"]: r["base"] for r in run_sql(sql)}


def get_bloqueadas_y_confirmadas(peak_day_offset: int):
    """Bloqueadas hoy/ayer (vivo) + resolución del pico del mes (activas/bloqueadas/caídas desde el pico)."""
    sql = SCOPED_CTE + f"""
    , hist AS (SELECT account_id AS aid2, valid_from AS vf, commercial_status AS cst, status AS st FROM fudata.accounts WHERE account_id IN (SELECT aid FROM scoped)),
    pts AS (SELECT toStartOfMonth(now()) AS ms1,
                   (toStartOfMonth(now()) + toIntervalDay({peak_day_offset})) AS pico,
                   now() AS nn, now() - toIntervalDay(1) AS yd),
    grid AS (SELECT s.aid AS aid9, s.ejec AS ejec9, s.team AS team9, p.ms1 AS ms1, p.pico AS pico, p.nn AS nn, p.yd AS yd
             FROM scoped s CROSS JOIN pts p),
    enr AS (
      SELECT g.aid9, g.ejec9, g.team9,
        hs.cst AS cst_ms1,
        hp.cst AS cst_pico, hp.st AS st_pico,
        hn.cst AS cst_nn, hn.st AS st_nn,
        hy.cst AS cst_yd, hy.st AS st_yd
      FROM grid g
      ASOF LEFT JOIN hist hs ON g.aid9 = hs.aid2 AND hs.vf <= g.ms1
      ASOF LEFT JOIN hist hp ON g.aid9 = hp.aid2 AND hp.vf <= g.pico
      ASOF LEFT JOIN hist hn ON g.aid9 = hn.aid2 AND hn.vf <= g.nn
      ASOF LEFT JOIN hist hy ON g.aid9 = hy.aid2 AND hy.vf <= g.yd
    )
    SELECT team9 AS team, ejec9 AS ejec,
      countIf(cst_ms1='ACTIVE' AND cst_pico='ACTIVE' AND st_pico='BLOCKED') AS bloqueadas_pico,
      countIf(cst_ms1='ACTIVE' AND cst_pico='ACTIVE' AND st_pico='BLOCKED' AND cst_nn='ACTIVE' AND st_nn!='BLOCKED') AS recuperadas_desde_pico,
      countIf(cst_ms1='ACTIVE' AND cst_pico='ACTIVE' AND st_pico='BLOCKED' AND cst_nn='ACTIVE' AND st_nn='BLOCKED') AS siguen_bloqueadas,
      countIf(cst_ms1='ACTIVE' AND cst_pico='ACTIVE' AND st_pico='BLOCKED' AND cst_nn='DROPPED') AS ya_cayeron_de_pico,
      countIf(cst_ms1='ACTIVE' AND cst_nn='ACTIVE' AND st_nn='BLOCKED') AS bloqueadas_hoy,
      countIf(cst_ms1='ACTIVE' AND cst_yd='ACTIVE' AND st_yd='BLOCKED') AS bloqueadas_ayer,
      countIf(cst_ms1='ACTIVE' AND cst_nn='DROPPED') AS dropped_ya,
      countIf(cst_ms1='ACTIVE' AND cst_yd='DROPPED') AS dropped_ayer
    FROM enr GROUP BY team, ejec ORDER BY team, ejec
    """
    return {r["ejec"]: r for r in run_sql(sql)}


def get_base_mismo_dia_mes_anterior(peak_day_offset: int):
    """Base y bloqueadas hace un mes, en el mismo offset de día, para poder comparar el indicador contra el ciclo anterior."""
    sql = SCOPED_CTE + f"""
    , hist AS (SELECT account_id AS aid2, valid_from AS vf, commercial_status AS cst, status AS st FROM fudata.accounts WHERE account_id IN (SELECT aid FROM scoped)),
    pts AS (SELECT (toStartOfMonth(now()) - toIntervalMonth(1)) AS ms0,
                   (toStartOfMonth(now()) - toIntervalMonth(1) + toIntervalDay({peak_day_offset})) AS d_equiv),
    grid AS (SELECT s.aid AS aid9, s.ejec AS ejec9, s.team AS team9, s.sc AS sc9, p.ms0 AS ms0, p.d_equiv AS d_equiv
             FROM scoped s CROSS JOIN pts p),
    enr AS (
      SELECT g.aid9, g.ejec9, g.team9, g.sc9, hs0.cst AS cst_ms0, hd.cst AS cst_d, hd.st AS st_d
      FROM grid g
      ASOF LEFT JOIN hist hs0 ON g.aid9 = hs0.aid2 AND hs0.vf <= g.ms0
      ASOF LEFT JOIN hist hd ON g.aid9 = hd.aid2 AND hd.vf <= g.d_equiv
    )
    SELECT team9 AS team, ejec9 AS ejec,
      countIf(cst_ms0='ACTIVE' AND sc9 > 50) AS base_mes_anterior,
      countIf(cst_ms0='ACTIVE' AND cst_d='ACTIVE' AND st_d='BLOCKED') AS bloqueadas_mes_anterior
    FROM enr GROUP BY team, ejec ORDER BY team, ejec
    """
    return {r["ejec"]: r for r in run_sql(sql)}


def build_data_blob():
    peak_off = detect_peak_day()
    base_por_exec = get_base_dia1_por_exec()
    bloqueadas = get_bloqueadas_y_confirmadas(peak_off)
    mes_anterior = get_base_mismo_dia_mes_anterior(peak_off)

    progress = {}
    for e in ALL_EXECS:
        b = bloqueadas.get(e, {})
        m = mes_anterior.get(e, {})
        progress[e] = {
            "baseDia1": base_por_exec.get(e, 0),
            "bloqueadasPico": b.get("bloqueadas_pico", 0),
            "recuperadasDesdePico": b.get("recuperadas_desde_pico", 0),
            "siguenBloqueadas": b.get("siguen_bloqueadas", 0),
            "yaCayeronDePico": b.get("ya_cayeron_de_pico", 0),
            "droppedYa": b.get("dropped_ya", 0),
            "bloqueadasHoy": b.get("bloqueadas_hoy", 0),
            "bloqueadasAyer": b.get("bloqueadas_ayer", 0),
            "droppedAyer": b.get("dropped_ayer", 0),
            "baseMismoDiaMesAnterior": m.get("base_mes_anterior", 0),
            "bloqueadasMismoDiaMesAnterior": m.get("bloqueadas_mes_anterior", 0),
        }

    today = datetime.date.today()
    peak_date = (today.replace(day=1) + datetime.timedelta(days=peak_off))

    data = {
        "teamOf": TEAM_OF,
        "colors": COLORS,
        "allExecs": ALL_EXECS,
        "retentionTarget": {
            "month": today.strftime("%Y-%m"),
            "target": TARGET_RETENTION,
            "peakLabel": f"día {peak_date.day}",
            "baseFijaNota": (
                "Base = cuentas activas al día 1 del mes con más de 50 ventas (hubspot_accounts.sales_count > 50). "
                "Nota: sales_count no tiene historial propio, así que se toma su valor actual, no el que tenía exactamente el día 1 — "
                "puede generar una pequeña diferencia (~1%) contra un corte manual tomado ese mismo día."
            ),
            "progress": progress,
        },
        "generatedAt": datetime.datetime.utcnow().isoformat() + "Z",
    }
    return data


def main():
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    blob_path = os.path.join(repo_root, "data_blob.js")

    # Partimos del data_blob.js existente (mantiene churn, NRR, composición, cohortes,
    # N1/N2, etc. tal como están) y solo pisamos la sección "retentionTarget" con datos frescos.
    # Esto es automatización parcial: el resto del tablero sigue con el último dato cargado
    # manualmente hasta que se agreguen las consultas correspondientes a este script.
    if not os.path.exists(blob_path):
        print("ERROR: no existe data_blob.js en el repo — necesito un punto de partida con el resto de los gráficos.", file=sys.stderr)
        sys.exit(1)

    with open(blob_path, "r", encoding="utf-8") as f:
        content = f.read()
    prefix = "const DATA = "
    if not content.startswith(prefix):
        print("ERROR: data_blob.js no tiene el formato esperado (const DATA = {...};)", file=sys.stderr)
        sys.exit(1)
    full_data = json.loads(content[len(prefix):].rstrip().rstrip(";"))

    fresh = build_data_blob()
    full_data["retentionTarget"] = fresh["retentionTarget"]
    full_data["lastRefreshed"] = fresh["generatedAt"]

    new_content = prefix + json.dumps(full_data, ensure_ascii=False) + ";\n"
    with open(blob_path, "w", encoding="utf-8") as f:
        f.write(new_content)

    print(f"OK — data_blob.js actualizado. Pico detectado: {fresh['retentionTarget']['peakLabel']}.")


if __name__ == "__main__":
    main()
