from __future__ import annotations

import numpy as np
import pandas as pd

from ecosistema_sqlite import OUTPUT_DIR, open_ecosystem

BASE_QUERY = """
WITH clientes_dedup AS (
    SELECT
        numero_id,
        MAX(grupo_edad) AS grupo_edad,
        MAX(desc_genero) AS desc_genero,
        MAX(desc_segmento) AS desc_segmento,
        MAX(desc_tipo_de_vivienda) AS desc_tipo_de_vivienda,
        MAX(ingresos_mensuales) AS ingresos_mensuales,
        MAX(total_egresos_mensuales) AS total_egresos_mensuales,
        MAX(total_activos) AS total_activos,
        MAX(total_pasivos) AS total_pasivos,
        MAX(total_patrimonio) AS total_patrimonio
    FROM clientes_db.clientes
    GROUP BY numero_id
),
estimador AS (
    SELECT numero_id, MAX(estimador_ingreso) AS estimador_ingreso
    FROM estimador_db.estimador_ing
    GROUP BY numero_id
),
aho_agg AS (
    SELECT
        numero_id,
        COUNT(*) AS aho_n_reg,
        COUNT(DISTINCT substr(fecha, 1, 7)) AS aho_n_meses,
        SUM(saldo) AS aho_saldo_sum,
        AVG(saldo) AS aho_saldo_avg,
        MAX(saldo) AS aho_saldo_max,
        SUM(CASE WHEN upper(producto) LIKE '%AHORRO%' THEN saldo ELSE 0 END) AS aho_saldo_ahorro_sum,
        SUM(CASE WHEN upper(producto) LIKE '%CORRIENTE%' THEN saldo ELSE 0 END) AS aho_saldo_corriente_sum
    FROM aho_db.crean_aho_cte
    GROUP BY numero_id
),
aho_last AS (
    SELECT numero_id, saldo AS aho_saldo_last
    FROM (
        SELECT numero_id, saldo,
               ROW_NUMBER() OVER (PARTITION BY numero_id ORDER BY fecha DESC) AS rn
        FROM aho_db.crean_aho_cte
    ) t WHERE rn = 1
),
bol_agg AS (
    SELECT
        numero_id,
        COUNT(*) AS bol_n_reg,
        COUNT(DISTINCT substr(fecha, 1, 7)) AS bol_n_meses,
        SUM(saldo) AS bol_saldo_sum,
        AVG(saldo) AS bol_saldo_avg,
        MAX(saldo) AS bol_saldo_max
    FROM bolsillos_db.crean_bolsillos
    GROUP BY numero_id
),
bol_last AS (
    SELECT numero_id, saldo AS bol_saldo_last
    FROM (
        SELECT numero_id, saldo,
               ROW_NUMBER() OVER (PARTITION BY numero_id ORDER BY fecha DESC) AS rn
        FROM bolsillos_db.crean_bolsillos
    ) t WHERE rn = 1
),
fidu_agg AS (
    SELECT
        numero_id,
        COUNT(*) AS fidu_n_reg,
        COUNT(DISTINCT substr(fecha, 1, 7)) AS fidu_n_meses,
        SUM(saldo) AS fidu_saldo_sum,
        AVG(saldo) AS fidu_saldo_avg,
        MAX(saldo) AS fidu_saldo_max
    FROM fiducuenta_db.crean_fiducuenta
    GROUP BY numero_id
),
fidu_last AS (
    SELECT numero_id, saldo AS fidu_saldo_last
    FROM (
        SELECT numero_id, saldo,
               ROW_NUMBER() OVER (PARTITION BY numero_id ORDER BY fecha DESC) AS rn
        FROM fiducuenta_db.crean_fiducuenta
    ) t WHERE rn = 1
),
cdt_agg AS (
    SELECT
        numero_id,
        COUNT(*) AS cdt_n_reg,
        COUNT(DISTINCT substr(fecha, 1, 7)) AS cdt_n_meses,
        SUM(saldo) AS cdt_saldo_sum,
        AVG(saldo) AS cdt_saldo_avg,
        MAX(saldo) AS cdt_saldo_max,
        SUM(CASE WHEN upper(producto) LIKE '%CDT%' THEN saldo ELSE 0 END) AS cdt_only_saldo_sum,
        SUM(CASE WHEN upper(producto) LIKE '%VIRTUAL%' THEN saldo ELSE 0 END) AS inv_virtual_saldo_sum
    FROM cdt_db.crean_inv_virtual_cdt
    GROUP BY numero_id
),
cdt_last AS (
    SELECT numero_id, saldo AS cdt_saldo_last
    FROM (
        SELECT numero_id, saldo,
               ROW_NUMBER() OVER (PARTITION BY numero_id ORDER BY fecha DESC) AS rn
        FROM cdt_db.crean_inv_virtual_cdt
    ) t WHERE rn = 1
),
inv_agg AS (
    SELECT
        numero_id,
        COUNT(*) AS inv_n_reg,
        COUNT(DISTINCT substr(fecha, 1, 7)) AS inv_n_meses,
        SUM(saldo) AS inv_saldo_sum,
        AVG(saldo) AS inv_saldo_avg,
        MAX(saldo) AS inv_saldo_max
    FROM invesbot_db.invesbot
    GROUP BY numero_id
),
inv_last AS (
    SELECT numero_id, saldo AS inv_saldo_last
    FROM (
        SELECT numero_id, saldo,
               ROW_NUMBER() OVER (PARTITION BY numero_id ORDER BY fecha DESC) AS rn
        FROM invesbot_db.invesbot
    ) t WHERE rn = 1
),
base AS (
    SELECT
        c.numero_id,
        c.grupo_edad, c.desc_genero, c.desc_segmento, c.desc_tipo_de_vivienda,
        COALESCE(c.ingresos_mensuales, 0) AS ingresos_mensuales,
        COALESCE(c.total_egresos_mensuales, 0) AS total_egresos_mensuales,
        COALESCE(c.total_activos, 0) AS total_activos,
        COALESCE(c.total_pasivos, 0) AS total_pasivos,
        COALESCE(c.total_patrimonio, 0) AS total_patrimonio,
        COALESCE(e.estimador_ingreso, 0) AS estimador_ingreso,
        COALESCE(a.aho_n_reg, 0) AS aho_n_reg,
        COALESCE(a.aho_n_meses, 0) AS aho_n_meses,
        COALESCE(a.aho_saldo_sum, 0) AS aho_saldo_sum,
        COALESCE(a.aho_saldo_avg, 0) AS aho_saldo_avg,
        COALESCE(a.aho_saldo_max, 0) AS aho_saldo_max,
        COALESCE(a.aho_saldo_ahorro_sum, 0) AS aho_saldo_ahorro_sum,
        COALESCE(a.aho_saldo_corriente_sum, 0) AS aho_saldo_corriente_sum,
        COALESCE(al.aho_saldo_last, 0) AS aho_saldo_last,
        COALESCE(b.bol_n_reg, 0) AS bol_n_reg,
        COALESCE(b.bol_n_meses, 0) AS bol_n_meses,
        COALESCE(b.bol_saldo_sum, 0) AS bol_saldo_sum,
        COALESCE(b.bol_saldo_avg, 0) AS bol_saldo_avg,
        COALESCE(b.bol_saldo_max, 0) AS bol_saldo_max,
        COALESCE(bl.bol_saldo_last, 0) AS bol_saldo_last,
        COALESCE(f.fidu_n_reg, 0) AS fidu_n_reg,
        COALESCE(f.fidu_n_meses, 0) AS fidu_n_meses,
        COALESCE(f.fidu_saldo_sum, 0) AS fidu_saldo_sum,
        COALESCE(f.fidu_saldo_avg, 0) AS fidu_saldo_avg,
        COALESCE(f.fidu_saldo_max, 0) AS fidu_saldo_max,
        COALESCE(fl.fidu_saldo_last, 0) AS fidu_saldo_last,
        COALESCE(d.cdt_n_reg, 0) AS cdt_n_reg,
        COALESCE(d.cdt_n_meses, 0) AS cdt_n_meses,
        COALESCE(d.cdt_saldo_sum, 0) AS cdt_saldo_sum,
        COALESCE(d.cdt_saldo_avg, 0) AS cdt_saldo_avg,
        COALESCE(d.cdt_saldo_max, 0) AS cdt_saldo_max,
        COALESCE(d.cdt_only_saldo_sum, 0) AS cdt_only_saldo_sum,
        COALESCE(d.inv_virtual_saldo_sum, 0) AS inv_virtual_saldo_sum,
        COALESCE(dl.cdt_saldo_last, 0) AS cdt_saldo_last,
        COALESCE(i.inv_n_reg, 0) AS inv_n_reg,
        COALESCE(i.inv_n_meses, 0) AS inv_n_meses,
        COALESCE(i.inv_saldo_sum, 0) AS inv_saldo_sum,
        COALESCE(i.inv_saldo_avg, 0) AS inv_saldo_avg,
        COALESCE(i.inv_saldo_max, 0) AS inv_saldo_max,
        COALESCE(il.inv_saldo_last, 0) AS inv_saldo_last
    FROM clientes_dedup c
    LEFT JOIN estimador e ON c.numero_id = e.numero_id
    LEFT JOIN aho_agg a ON c.numero_id = a.numero_id
    LEFT JOIN aho_last al ON c.numero_id = al.numero_id
    LEFT JOIN bol_agg b ON c.numero_id = b.numero_id
    LEFT JOIN bol_last bl ON c.numero_id = bl.numero_id
    LEFT JOIN fidu_agg f ON c.numero_id = f.numero_id
    LEFT JOIN fidu_last fl ON c.numero_id = fl.numero_id
    LEFT JOIN cdt_agg d ON c.numero_id = d.numero_id
    LEFT JOIN cdt_last dl ON c.numero_id = dl.numero_id
    LEFT JOIN inv_agg i ON c.numero_id = i.numero_id
    LEFT JOIN inv_last il ON c.numero_id = il.numero_id
)
SELECT
    *,
    MAX(ingresos_mensuales - total_egresos_mensuales, 0) AS ingreso_disponible_mensual,
    MAX(total_activos - total_pasivos, 0) AS riqueza_neta,
    (CASE WHEN (fidu_n_reg + cdt_n_reg + inv_n_reg) > 0 THEN 1 ELSE 0 END) AS tiene_productos_inversion,
    (CASE WHEN (bol_n_reg + aho_n_reg) > 0 THEN 1 ELSE 0 END) AS tiene_productos_ahorro
FROM base
"""


def _scale_log_p95(series: pd.Series) -> pd.Series:
    s = series.fillna(0).clip(lower=0)
    p95 = float(s.quantile(0.95))
    if p95 <= 0:
        return pd.Series(0.0, index=series.index)
    return (np.log1p(s) / np.log1p(p95)).clip(0, 1)


def main() -> None:
    with open_ecosystem() as (conn, _):
        df = pd.read_sql_query(BASE_QUERY, conn)

    inv_saldo_last = (
        df["fidu_saldo_last"].fillna(0)
        + df["cdt_saldo_last"].fillna(0)
        + df["inv_saldo_last"].fillna(0)
    )
    inv_meses = (
        df["fidu_n_meses"].fillna(0)
        + df["cdt_n_meses"].fillna(0)
        + df["inv_n_meses"].fillna(0)
    )

    df["score_adopcion"] = (
        _scale_log_p95(df["ingreso_disponible_mensual"]) * 0.28
        + _scale_log_p95(df["riqueza_neta"]) * 0.24
        + _scale_log_p95(inv_saldo_last) * 0.18
        + (inv_meses / 13.0).clip(0, 1) * 0.12
        + _scale_log_p95(df["estimador_ingreso"]) * 0.10
        + df["tiene_productos_inversion"].fillna(0).clip(0, 1) * 0.08
    ).clip(0, 1)

    p95 = float(df["score_adopcion"].quantile(0.95))
    p80 = float(df["score_adopcion"].quantile(0.80))
    df["segmento_prioridad"] = np.where(
        df["score_adopcion"] >= p95,
        "Alta",
        np.where(df["score_adopcion"] >= p80, "Media", "Baja"),
    )

    base_monto = (
        df["ingreso_disponible_mensual"].fillna(0).clip(lower=0) * 12 * 0.15
        + df["riqueza_neta"].fillna(0).clip(lower=0) * 0.015
        + inv_saldo_last.clip(lower=0) * 0.06
    )
    df["monto_potencial_12m"] = base_monto * (0.40 + 0.60 * df["score_adopcion"])
    df["monto_potencial_12m"] = df["monto_potencial_12m"].clip(
        upper=float(df["monto_potencial_12m"].quantile(0.99))
    )
    df["monto_potencial_12m_conservador"] = df["monto_potencial_12m"] * 0.30

    df["usa_invesbot"] = (df["inv_n_reg"].fillna(0) > 0).astype(int)
    df["usa_cdt_o_virtual"] = (df["cdt_n_reg"].fillna(0) > 0).astype(int)
    df["usa_fiducuenta"] = (df["fidu_n_reg"].fillna(0) > 0).astype(int)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_DIR / "base_analitica_cliente.csv", index=False)

    resumen = (
        df.groupby("segmento_prioridad")
        .agg(
            clientes=("numero_id", "count"),
            score_promedio=("score_adopcion", "mean"),
            monto_total=("monto_potencial_12m", "sum"),
            monto_conservador_total=("monto_potencial_12m_conservador", "sum"),
        )
        .reset_index()
    )
    resumen.to_csv(OUTPUT_DIR / "resumen_segmentos.csv", index=False)
    print(f"Listo: {len(df):,} clientes -> output/")


if __name__ == "__main__":
    main()
