import zipfile
from io import BytesIO

import pandas as pd


# ─── Catégories Tableau Performance ──────────────────────────────────────────
# Alignées sur le dashboard Performance natif de Tableau (exclut "Other")

def _categoriser(event_name: str) -> str:
    """Mappe un Event Name vers la catégorie du dashboard Tableau Performance."""
    n = str(event_name).lower()
    if "query-batch.process" in n or "execute-query" in n:
        return "Executing Query"
    if n == "sort":
        return "Sorting Data"
    if "partition-interpreter" in n or "visual-model-producer" in n:
        return "Computing Layout"
    if "compute-totals" in n or "totals-interpreter" in n:
        return "Computing Totals"
    if "renderactive" in n or (n.startswith("render") and "xml" not in n):
        return "Rendering"
    if "domparser_parsexmlstring" in n:
        return "Parsing XML"
    return "Other"


CATEGORIES_SIGNIFICATIVES = {
    "Executing Query",
    "Sorting Data",
    "Computing Layout",
    "Computing Totals",
    "Rendering",
    "Parsing XML",
}


# ─── Extraction ──────────────────────────────────────────────────────────────

def extraire_perf_gantt(twbx_bytes: bytes) -> pd.DataFrame:
    """Extrait le fichier perf_gantt.tab d'une archive .twbx et retourne un DataFrame."""
    with zipfile.ZipFile(BytesIO(twbx_bytes)) as z:
        candidats = [n for n in z.namelist() if n.lower().endswith("perf_gantt.tab")]
        if not candidats:
            raise ValueError("Aucun fichier perf_gantt.tab trouvé dans l'archive .twbx.")
        with z.open(candidats[0]) as f:
            df = pd.read_csv(f, sep="|", low_memory=False, on_bad_lines="skip")
    return _preparer(df)


def _preparer(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["Elapsed Time"] = pd.to_numeric(
        df["Elapsed Time"] if "Elapsed Time" in df.columns else 0.0,
        errors="coerce",
    ).fillna(0.0)
    for col in ("Worksheet", "Dashboard", "DataSource Name", "Event Name", "CacheHit"):
        if col in df.columns:
            df[col] = df[col].fillna("").astype(str).str.strip()
    df["Catégorie"] = df["Event Name"].apply(_categoriser)
    return df


def filtrer_significatifs(df: pd.DataFrame) -> pd.DataFrame:
    """Conserve uniquement les événements des catégories Tableau (exclut 'Other').
    Ces événements sont des feuilles non imbriquées : leur somme est fiable."""
    return df[df["Catégorie"].isin(CATEGORIES_SIGNIFICATIVES)].reset_index(drop=True)


# ─── Analyse ─────────────────────────────────────────────────────────────────

def calculer_kpis(df: pd.DataFrame) -> dict:
    """df doit être le dataframe filtré par filtrer_significatifs()."""
    mask_query = df["Catégorie"] == "Executing Query"
    mask_miss  = mask_query & df["CacheHit"].isin(["false", "0", ""])
    return {
        "temps_total":    round(float(df["Elapsed Time"].sum()), 3) if not df.empty else 0.0,
        "max_event":      round(float(df["Elapsed Time"].max()), 3) if not df.empty else 0.0,
        "nb_requetes":    int(mask_query.sum()),
        "nb_cache_miss":  int(mask_miss.sum()),
        "temps_requetes": round(float(df.loc[mask_query, "Elapsed Time"].sum()), 3),
    }


def top_evenements_lents(df: pd.DataFrame, n: int = 15) -> pd.DataFrame:
    """Les N événements individuels ayant pris le plus de temps."""
    voulues = ["Catégorie", "Event Name", "Worksheet", "Dashboard", "DataSource Name", "Elapsed Time"]
    cols = [c for c in voulues if c in df.columns]
    result = (
        df[cols]
        .sort_values("Elapsed Time", ascending=False)
        .head(n)
        .reset_index(drop=True)
    )
    result["Elapsed Time"] = result["Elapsed Time"].round(3)
    return result


def resume_par_feuille(df: pd.DataFrame) -> pd.DataFrame:
    """Temps total et nombre d'événements par feuille (Worksheet)."""
    mask = df["Worksheet"].str.len() > 0
    if not mask.any():
        return pd.DataFrame()
    agg = (
        df[mask]
        .groupby("Worksheet")["Elapsed Time"]
        .agg(["count", "sum", "max"])
        .reset_index()
        .rename(columns={
            "Worksheet": "Feuille",
            "count":     "Évènements",
            "sum":       "Temps total (s)",
            "max":       "Temps max (s)",
        })
        .sort_values("Temps total (s)", ascending=False)
        .reset_index(drop=True)
    )
    agg["Temps total (s)"] = agg["Temps total (s)"].round(3)
    agg["Temps max (s)"]   = agg["Temps max (s)"].round(3)
    return agg


def resume_par_categorie(df: pd.DataFrame) -> pd.DataFrame:
    """Résumé par catégorie Tableau, trié par temps total décroissant."""
    agg = (
        df.groupby("Catégorie")["Elapsed Time"]
        .agg(["count", "sum", "mean", "max"])
        .reset_index()
        .rename(columns={
            "Catégorie": "Catégorie",
            "count":     "Occurrences",
            "sum":       "Temps total (s)",
            "mean":      "Temps moyen (s)",
            "max":       "Temps max (s)",
        })
        .sort_values("Temps total (s)", ascending=False)
        .reset_index(drop=True)
    )
    for col in ("Temps total (s)", "Temps moyen (s)", "Temps max (s)"):
        agg[col] = agg[col].round(3)
    return agg


def requetes_sans_cache(df: pd.DataFrame) -> pd.DataFrame:
    """Requêtes SQL exécutées sans cache (CacheHit = false), triées par durée."""
    mask = (
        (df["Catégorie"] == "Executing Query")
        & df["CacheHit"].isin(["false", "0", ""])
    )
    voulues = ["Catégorie", "Worksheet", "Dashboard", "DataSource Name", "Elapsed Time"]
    cols = [c for c in voulues if c in df.columns]
    result = (
        df.loc[mask, cols]
        .sort_values("Elapsed Time", ascending=False)
        .reset_index(drop=True)
    )
    if "Elapsed Time" in result.columns:
        result["Elapsed Time"] = result["Elapsed Time"].round(3)
    return result
