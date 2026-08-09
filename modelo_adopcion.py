from __future__ import annotations

import numpy as np
import pandas as pd
from pandas.api.types import is_numeric_dtype

from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score, average_precision_score, precision_score, recall_score, f1_score
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier

from ecosistema_sqlite import OUTPUT_DIR

BASE_FILE = OUTPUT_DIR / "base_analitica_cliente.csv"

EXCLUDE_FEATURES = {
    "numero_id", "score_adopcion", "segmento_prioridad",
    "monto_potencial_12m", "monto_potencial_12m_conservador",
    "target_proxy", "prob_ml_adopcion", "segmento_ml",
    "monto_potencial_12m_ml", "monto_potencial_12m_ml_conservador",
    "ingreso_disponible_mensual", "riqueza_neta",
    "ingresos_mensuales", "total_egresos_mensuales",
    "total_activos", "total_pasivos", "total_patrimonio",
    "tiene_productos_inversion", "tiene_productos_ahorro",
    "aho_n_reg", "bol_n_reg", "usa_invesbot", "usa_cdt_o_virtual", "usa_fiducuenta",
    "fidu_n_reg", "fidu_n_meses", "fidu_saldo_sum", "fidu_saldo_avg", "fidu_saldo_max", "fidu_saldo_last",
    "cdt_n_reg", "cdt_n_meses", "cdt_saldo_sum", "cdt_saldo_avg", "cdt_saldo_max", "cdt_saldo_last",
    "cdt_only_saldo_sum", "inv_virtual_saldo_sum",
    "inv_n_reg", "inv_n_meses", "inv_saldo_sum", "inv_saldo_avg", "inv_saldo_max", "inv_saldo_last",
}


def build_target_proxy(df: pd.DataFrame) -> pd.Series:
    inv_last = df["fidu_saldo_last"].fillna(0) + df["cdt_saldo_last"].fillna(0) + df["inv_saldo_last"].fillna(0)
    inv_hist = df["fidu_saldo_sum"].fillna(0) + df["cdt_saldo_sum"].fillna(0) + df["inv_saldo_sum"].fillna(0)
    inv_meses = df["fidu_n_meses"].fillna(0) + df["cdt_n_meses"].fillna(0) + df["inv_n_meses"].fillna(0)

    inversionista = (
        (df["tiene_productos_inversion"] == 1)
        & ((inv_meses >= 6) | (inv_last >= inv_last.quantile(0.70)) | (inv_hist >= inv_hist.quantile(0.75)))
        & (df["ingreso_disponible_mensual"] > 0)
    )
    prospecto = (
        (df["tiene_productos_inversion"] == 0)
        & (df["tiene_productos_ahorro"] == 1)
        & (df["ingreso_disponible_mensual"] >= df["ingreso_disponible_mensual"].quantile(0.80))
        & (df["riqueza_neta"] >= df["riqueza_neta"].quantile(0.80))
    )
    return (inversionista | prospecto).astype(int)


def main() -> None:
    if not BASE_FILE.exists():
        raise FileNotFoundError("Ejecuta primero construir_base_modelo.py")

    df = pd.read_csv(BASE_FILE)
    df["target_proxy"] = build_target_proxy(df)

    features = [c for c in df.columns if c not in EXCLUDE_FEATURES]
    num_cols = [c for c in features if is_numeric_dtype(df[c])]
    cat_cols = [c for c in features if c not in num_cols]

    X, y = df[features], df["target_proxy"].astype(int)
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.25, random_state=42, stratify=y)

    prep = ColumnTransformer([
        ("num", Pipeline([("imp", SimpleImputer(strategy="median")), ("sc", StandardScaler(with_mean=False))]), num_cols),
        ("cat", Pipeline([("imp", SimpleImputer(strategy="most_frequent")), ("oh", OneHotEncoder(handle_unknown="ignore"))]), cat_cols),
    ])

    models = {
        "logistic": LogisticRegression(max_iter=1000, random_state=42, class_weight="balanced"),
        "random_forest": RandomForestClassifier(n_estimators=200, max_depth=10, min_samples_leaf=80, random_state=42, n_jobs=-1, class_weight="balanced_subsample"),
    }

    metrics, trained = [], {}
    for name, clf in models.items():
        pipe = Pipeline([("prep", prep), ("model", clf)])
        pipe.fit(X_train, y_train)
        prob = pipe.predict_proba(X_test)[:, 1]
        pred = (prob >= 0.5).astype(int)
        cut = np.quantile(prob, 0.90)
        top = (prob >= cut).astype(int)
        metrics.append({
            "modelo": name,
            "auc_roc": roc_auc_score(y_test, prob),
            "auc_pr": average_precision_score(y_test, prob),
            "precision_top10": precision_score(y_test, top, zero_division=0),
            "recall_top10": recall_score(y_test, top, zero_division=0),
            "f1": f1_score(y_test, pred, zero_division=0),
        })
        trained[name] = pipe

    metrics_df = pd.DataFrame(metrics).sort_values("auc_roc", ascending=False)
    best = trained[metrics_df.iloc[0]["modelo"]]

    df["prob_ml_adopcion"] = best.predict_proba(X)[:, 1]
    p95, p80 = df["prob_ml_adopcion"].quantile(0.95), df["prob_ml_adopcion"].quantile(0.80)
    df["segmento_ml"] = np.where(df["prob_ml_adopcion"] >= p95, "Alta", np.where(df["prob_ml_adopcion"] >= p80, "Media", "Baja"))
    df["monto_potencial_12m_ml"] = df["monto_potencial_12m"] * (0.35 + 0.65 * df["prob_ml_adopcion"])
    df["monto_potencial_12m_ml_conservador"] = df["monto_potencial_12m_ml"] * 0.30

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_DIR / "base_analitica_final.csv", index=False)
    metrics_df.to_csv(OUTPUT_DIR / "modelo_metricas.csv", index=False)

    resumen = df.groupby("segmento_ml").agg(
        clientes=("numero_id", "count"),
        prob_promedio=("prob_ml_adopcion", "mean"),
        monto_conservador_total=("monto_potencial_12m_ml_conservador", "sum"),
    ).reset_index()
    resumen.to_csv(OUTPUT_DIR / "resumen_segmentos_ml.csv", index=False)

    df.sort_values("prob_ml_adopcion", ascending=False).head(20000).to_csv(
        OUTPUT_DIR / "top_clientes_ml.csv", index=False
    )

    print(f"Modelo: {metrics_df.iloc[0]['modelo']} | AUC: {metrics_df.iloc[0]['auc_roc']:.4f}")


if __name__ == "__main__":
    main()
