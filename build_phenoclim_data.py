#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_phenoclim_data.py
=======================
Fetches the Phénoclim "public" export (id 3) from the CREA Mont-Blanc GeoNature
API, cleans it following the project's Colab logic, aggregates it, and writes a
compact `phenoclim_data.json` that the dashboard loads instead of its hard-coded
arrays.

Run:  python build_phenoclim_data.py
Out:  phenoclim_data.json   (a few KB — safe to commit to the repo)

Requires: requests, pandas   (pip install requests pandas)

NOTE ON ALTITUDE: the original Colab notebook back-filled missing altitudes by
calling the Open-Elevation API row-by-row. That is slow and network-heavy. For a
motivational summary page the altitude *chart* only needs rows that already have
an altitude, so by default we DO NOT call Open-Elevation (FILL_MISSING_ALTITUDE
= False). Rows missing altitude are simply excluded from the altitude aggregation
(they still count everywhere else). Set FILL_MISSING_ALTITUDE = True to reproduce
the notebook's behaviour exactly.
"""

import json
import time
import math
import sys

import requests
import pandas as pd

# ──────────────────────────────────────────────────────────────────────────
# CONFIG
# ──────────────────────────────────────────────────────────────────────────
API_URL = "https://geonature.spot.creamontblanc.org/geonature/api/exports/api/3"
# This server returns the WHOLE export when limit=0 (offset/page are ignored,
# and a positive limit is capped at 1000). So we fetch everything in one call.
PAGE_SIZE = 0              # 0 = no limit = full export
REQUEST_TIMEOUT = 300      # the full payload is ~42 MB, so allow time
RETRIES = 3
FILL_MISSING_ALTITUDE = False   # True = call Open-Elevation for missing altitudes (slow)
OUTPUT = "phenoclim_data.json"

# Stages we keep (mirrors keep_columns in the Colab notebook)
KEEP_PHENO = [
    "Changement de couleur - Ok 10%",
    "Changement de couleur - Ok 50%",
    "Débourrement - Ok 10%",
    "Feuillaison - Ok 10%",
    "Floraison - Ok 10%",
    "Fructification",
]

TREES_OF_INTEREST = [
    "noisetier", "pin sylvestre", "mélèze", "sapin", "épicéa",
    "frene", "frêne", "sorbier", "bouleau", "hêtre",
]

# Region bounding boxes (lat_min, lat_max, lon_min, lon_max) — from the notebook
REGION_DEFINITION = [
    ("Alps",              43.87, 47.26,  5.02, 9.51),
    ("Mont-Blanc Massif", 45.7,  46.0,   6.6,  7.1),
    ("Jura",              46.2,  48.21,  5.5,  6.9),
    ("Pyrenees",          42.11, 43.72, -1.8,  3.0),
    ("Massif Central",    44.07, 46.37,  1.47, 4.87),
    ("Corsica",           41.3,  43.0,   8.5,  9.6),
    ("Vosges",            47.75, 48.77,  6.7,  7.3),
]

# The four species the dashboard charts (its internal keys)
DASHBOARD_SPECIES = ["bouleau", "mélèze", "noisetier", "sorbier"]
# Map the cleaning-script species label -> dashboard key
SPECIES_TO_DASHBOARD = {
    "bouleau": "bouleau",
    "mélèze": "mélèze",
    "noisetier": "noisetier",
    "sorbier": "sorbier",
}
STAGE_ORDER = ["Débourrement", "Feuillaison", "Floraison", "Changement de couleur"]


# ──────────────────────────────────────────────────────────────────────────
# 1. FETCH
# ──────────────────────────────────────────────────────────────────────────
def fetch_all():
    """
    Fetch the FULL export in one request.

    This GeoNature server ignores `offset`/`page` and caps `limit` at 1000 for
    normal requests — BUT `limit=0` is treated as "no limit" and returns the
    entire export (~70k rows, ~42 MB) in a single response. Confirmed via
    diagnose_api2.py.
    """
    print("  requesting full export (limit=0) ...")
    last_err = None
    for attempt in range(1, RETRIES + 1):
        try:
            r = requests.get(
                API_URL,
                params={"limit": 0},
                timeout=max(REQUEST_TIMEOUT, 300),  # big payload, allow time
            )
            r.raise_for_status()
            payload = r.json()
            break
        except Exception as e:
            last_err = e
            print(f"  ! request failed (attempt {attempt}): {e}")
            if attempt == RETRIES:
                raise
            time.sleep(3 * attempt)

    items = payload.get("items", [])
    total = payload.get("total")
    license_name = payload.get("license", {}).get("name")
    print(f"  total reported: {total}  |  received: {len(items)}  |  licence: {license_name}")
    if total and len(items) < total:
        print(f"  ! WARNING: received fewer rows ({len(items)}) than total ({total}).")
        print(f"    The server may have changed behaviour — check the API.")
    return items, license_name


# ──────────────────────────────────────────────────────────────────────────
# 2. CLEAN  (mirrors the Colab notebook)
# ──────────────────────────────────────────────────────────────────────────
def get_altitude_open_elevation(lat, lon):
    try:
        url = f"https://api.open-elevation.com/api/v1/lookup?locations={lat},{lon}"
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            return resp.json()["results"][0]["elevation"]
    except Exception as e:
        print(f"    open-elevation error: {e}")
    return None


def clean(items):
    df = pd.DataFrame(items)

    # pheno_etape_value falls back to pheno_stade_value when null
    if "pheno_stade_value" in df.columns:
        df["pheno_etape_value"] = df["pheno_etape_value"].fillna(df["pheno_stade_value"])

    # rename coordinates
    df = df.rename(columns={"coord_y_4326": "latitude", "coord_x_4326": "longitude"})

    # keep only the phenological stages of interest
    df = df[df["pheno_etape_value"].isin(KEEP_PHENO)].copy()

    # split "Débourrement - Ok 10%" -> pheno_etape="Débourrement", Percentage=10
    split_values = df["pheno_etape_value"].str.split(" - ", expand=True)
    df["pheno_etape"] = split_values[0]
    if split_values.shape[1] > 1:
        sp = split_values[1].str.split(" ", expand=True)
        df["Percentage"] = sp[1] if sp.shape[1] > 1 else 0
    else:
        df["Percentage"] = 0
    df["Percentage"] = (
        df["Percentage"].astype(str).str.replace("%", "", regex=False)
    )
    df["Percentage"] = pd.to_numeric(df["Percentage"], errors="coerce").astype("Int64")

    # fruits_amount: convert ranges to midpoints
    fruit_map = {
        "10-20": "15", "5-10": "7", "20-30": "25", "500-1000": "750",
        "1000-2000": "1500", "5000-Inf": "5000", "1-30": "15", "200-300": "250",
    }
    if "fruits_amount" in df.columns:
        fa = df["fruits_amount"].astype("object")
        for k, v in fruit_map.items():
            fa = fa.str.replace(k, v, regex=False) if hasattr(fa, "str") else fa
        df["fruits_amount"] = pd.to_numeric(fa, errors="coerce").astype("Int64")

    # dates -> year / month
    df["visit_date"] = pd.to_datetime(df["visit_date"], errors="coerce")
    df["visit_year"] = df["visit_date"].dt.year
    df["visit_month"] = df["visit_date"].dt.month

    # altitude numeric
    df["altitude"] = pd.to_numeric(df.get("altitude"), errors="coerce")

    # unify altitude across identical lat/long (mean), like the notebook
    alt_known = df.dropna(subset=["altitude"])
    if len(alt_known):
        alt_avg = (
            alt_known.groupby(["latitude", "longitude"])["altitude"]
            .mean().round().astype(int).reset_index()
            .rename(columns={"altitude": "altitude_avg"})
        )
        df = df.merge(alt_avg, on=["latitude", "longitude"], how="left")
        df["altitude"] = df["altitude_avg"].combine_first(df["altitude"])
        df.drop(columns=["altitude_avg"], inplace=True)

    # optionally back-fill missing altitude via Open-Elevation (slow)
    if FILL_MISSING_ALTITUDE:
        missing = (
            df[df["altitude"].isnull()][["latitude", "longitude"]]
            .drop_duplicates().dropna()
        )
        print(f"  filling {len(missing)} missing altitudes via Open-Elevation ...")
        fills = {}
        for _, r in missing.iterrows():
            a = get_altitude_open_elevation(r["latitude"], r["longitude"])
            if a is not None:
                fills[(r["latitude"], r["longitude"])] = a
            time.sleep(0.5)
        if fills:
            df["altitude"] = df.apply(
                lambda row: fills.get((row["latitude"], row["longitude"]), row["altitude"])
                if pd.isnull(row["altitude"]) else row["altitude"],
                axis=1,
            )

    # species from base_site_name
    df["base_site_name_lc"] = df["base_site_name"].str.lower()
    df["species"] = None
    for tree in TREES_OF_INTEREST:
        df.loc[df["base_site_name_lc"].str.contains(tree, na=False), "species"] = tree
    df["species"] = df["species"].str.replace("frene", "frêne", case=False)

    # region via exact point-in-polygon assignment (commune -> massif, with the
    # Alps split into Alpes du Nord / Alpes du Sud and Mont-Blanc
    # pulled out). Cached per nom_zone. See region_assign.py.
    from region_assign import assign_regions  # local module
    refresh = "--refresh-regions" in sys.argv
    # assign_regions needs the raw Lambert-93 + WGS84 coords; pass the columns
    # it expects (coord_x/y_2154 and coord_x/y_4326 are still on df here).
    lookup = assign_regions(df, refresh=refresh)
    df = df.merge(lookup[["nom_zone", "region"]], on="nom_zone", how="left")
    df["Region"] = df["region"]
    df.drop(columns=["region"], inplace=True)

    return df


# ──────────────────────────────────────────────────────────────────────────
# 3. AGGREGATE  ->  the structures the dashboard needs
# ──────────────────────────────────────────────────────────────────────────
def _mean_doy(sub):
    """Mean day-of-year from visit_date."""
    doy = sub["visit_date"].dt.dayofyear
    return round(float(doy.mean()), 1)


def aggregate(df, raw_items=None):
    # restrict to the 4 charted species + valid dates
    d = df[df["species"].isin(DASHBOARD_SPECIES) & df["visit_date"].notna()].copy()
    d["doy"] = d["visit_date"].dt.dayofyear

    # For "Changement de couleur" the dashboard separates 10% and 50%.
    # For the other stages it uses the 10% records.
    def stage_pct(row):
        return int(row) if pd.notna(row) else None

    out = {}

    # ---- TIMING: mean doy by species × stage × year (10%) ----
    timing, timing50 = [], []
    for (sp, st, yr), sub in d.groupby(["species", "pheno_etape", "visit_year"]):
        if pd.isna(yr):
            continue
        is_couleur = (st == "Changement de couleur")
        pct = sub["Percentage"]
        if is_couleur:
            s10 = sub[pct == 10]
            s50 = sub[pct == 50]
            if len(s10):
                timing.append({"s": sp, "st": st, "y": int(yr), "d": round(float(s10["doy"].mean()), 1)})
            if len(s50):
                timing50.append({"s": sp, "st": st, "y": int(yr), "d": round(float(s50["doy"].mean()), 1)})
        else:
            timing.append({"s": sp, "st": st, "y": int(yr), "d": round(float(sub["doy"].mean()), 1)})
    out["TIMING"] = timing
    out["TIMING50"] = timing50

    # ---- ALT: mean doy by species × 200 m altitude band ----
    # Exclude the 0–200 m band: not a meaningful altitude in the Alps.
    da = d[d["altitude"].notna()].copy()
    da["band"] = (da["altitude"] // 200 * 200).astype(int)
    da = da[da["band"] >= 200]
    alt, alt50 = [], []
    # Débourrement bands (no st field in dashboard's ALT for débourrement)
    for (sp, band), sub in da[da["pheno_etape"] == "Débourrement"].groupby(["species", "band"]):
        if len(sub) >= 3:  # ignore tiny bins
            alt.append({"s": sp, "a": int(band), "d": round(float(sub["doy"].mean()), 1)})
    # Changement de couleur bands (10% and 50%)
    for (sp, band), sub in da[da["pheno_etape"] == "Changement de couleur"].groupby(["species", "band"]):
        s10 = sub[sub["Percentage"] == 10]
        s50 = sub[sub["Percentage"] == 50]
        if len(s10) >= 3:
            alt.append({"s": sp, "st": "Changement de couleur", "a": int(band), "d": round(float(s10["doy"].mean()), 1)})
        if len(s50) >= 3:
            alt50.append({"s": sp, "st": "Changement de couleur", "a": int(band), "d": round(float(s50["doy"].mean()), 1)})
    out["ALT"] = alt
    out["ALT50"] = alt50

    # ---- OBS: observation count per year (ALL cleaned rows, not just 4 species) ----
    # ---- OBS: observation count per year ----
    # Use the RAW export (all contributions) so the bar chart and headline
    # reflect everything participants collected, not just the analysed subset.
    raw_df = None
    if raw_items is not None:
        raw_df = pd.DataFrame(raw_items)
        raw_df["visit_date"] = pd.to_datetime(raw_df["visit_date"], errors="coerce")
        raw_df["visit_year"] = raw_df["visit_date"].dt.year
        obs_src = raw_df[raw_df["visit_year"].notna()]
    else:
        obs_src = df[df["visit_year"].notna()]
    obs = (
        obs_src.groupby("visit_year").size().reset_index(name="c")
        .sort_values("visit_year")
    )
    out["OBS"] = [{"y": int(r.visit_year), "c": int(r.c)} for r in obs.itertuples()]

    # ---- REGIONS: mean doy by region × species for Débourrement & Floraison ----
    regions = []
    dr = d[d["Region"].notna()].copy()
    # normalise region label to the dashboard's short names
    region_label = {
        "Alps": "Alps", "Alpes du Nord": "Alpes du Nord", "Alpes du Sud": "Alpes du Sud",
        "Mont-Blanc": "Mont-Blanc",
        "Pyrenees": "Pyrenees", "Massif Central": "Massif Central", "Jura": "Jura",
        "Vosges": "Vosges", "Corse": "Corse", "Other": "Other",
    }
    for (reg, sp, st), sub in dr.groupby(["Region", "species", "pheno_etape"]):
        if st not in ("Débourrement", "Floraison"):
            continue
        if len(sub) < 3:
            continue
        regions.append({
            "r": region_label.get(reg, reg), "s": sp, "st": st,
            "d": round(float(sub["doy"].mean()), 1),
        })
    out["REGIONS"] = regions

    # ---- HEATMAP: Alps observation counts per species × year × 200 m band ----
    # Drives the "Où avons-nous besoin de vous ?" heatmaps. Alps region only,
    # counting ALL observations (any stage) for each charted species, in 200 m
    # bands from 200 m upward (0–200 m excluded — see ALT above).
    heatmap = {}
    # "Alps" here means the greater Alps, which includes the Mont-Blanc massif
    # (our region boxes split Mont-Blanc out separately, but it is part of the Alps).
    alps_regions = ["Alps", "Alpes du Nord", "Alpes du Sud", "Mont-Blanc"]
    hd = df[
        df["species"].isin(DASHBOARD_SPECIES)
        & df["Region"].isin(alps_regions)
        & df["altitude"].notna()
        & df["visit_year"].notna()
    ].copy()
    hd["band"] = (hd["altitude"] // 200 * 200).astype(int)
    hd = hd[hd["band"] >= 200]
    for sp in DASHBOARD_SPECIES:
        sp_rows = hd[hd["species"] == sp]
        counts = (
            sp_rows.groupby(["visit_year", "band"]).size().reset_index(name="count")
        )
        data = [
            {"year": int(r.visit_year), "alt": int(r.band), "count": int(r.count)}
            for r in counts.itertuples()
        ]
        heatmap[sp] = {"data": data}
    out["HEATMAP"] = heatmap

    # ---- headline stats for the cards ----
    alt_series = df["altitude"].dropna()
    raw_total = int(len(raw_items)) if raw_items is not None else int(len(df))
    # year range from raw data if we have it (so headline "years" matches the bars)
    if raw_df is not None and raw_df["visit_year"].notna().any():
        y_min = int(raw_df["visit_year"].min())
        y_max = int(raw_df["visit_year"].max())
    else:
        y_min = int(df["visit_year"].min()) if df["visit_year"].notna().any() else None
        y_max = int(df["visit_year"].max()) if df["visit_year"].notna().any() else None
    out["META"] = {
        "total_obs": raw_total,             # RAW — shown everywhere as "observations"
        "cleaned_obs": int(len(df)),        # cleaned subset used by the analytical charts
        "year_min": y_min,
        "year_max": y_max,
        "alt_min": int(alt_series.min()) if len(alt_series) else None,
        "alt_max": int(alt_series.max()) if len(alt_series) else None,
        "n_species": int(df["species"].nunique()),
        "n_regions": int(df["Region"].nunique()),
    }

    # ---- region coverage counts (for the "où avons-nous besoin de vous" panel) ----
    reg_counts = (
        df[df["Region"].notna()].groupby("Region").size()
        .sort_values(ascending=False)
    )
    out["REGION_COUNTS"] = [
        {"region": region_label.get(k, k), "obs": int(v)} for k, v in reg_counts.items()
    ]

    # ---- species coverage counts (+ breadth: how many years / regions) ----
    sp_df = df[df["species"].notna()]
    sp_counts = sp_df.groupby("species").size().sort_values(ascending=False)
    sp_years = sp_df.groupby("species")["visit_year"].nunique()
    sp_regions = sp_df.groupby("species")["Region"].nunique()
    out["SPECIES_COUNTS"] = [
        {
            "species": k,
            "obs": int(v),
            "n_years": int(sp_years.get(k, 0)),
            "n_regions": int(sp_regions.get(k, 0)),
        }
        for k, v in sp_counts.items()
    ]

    # ---- derived numbers for the narrative insight texts ----
    # Everything here is computed from the data so no prose in the dashboard
    # has to hard-code a figure.
    insights = {}

    # Altitude gradient per species: slope in days per 100 m, plus the span
    # between the lowest and highest band actually observed (Débourrement).
    grad = {}
    for sp in DASHBOARD_SPECIES:
        pts = sorted(
            [(a["a"], a["d"]) for a in alt if a["s"] == sp and "st" not in a],
            key=lambda t: t[0],
        )
        if len(pts) < 2:
            continue
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        n = len(xs)
        mx = sum(xs) / n
        my = sum(ys) / n
        denom = sum((x - mx) ** 2 for x in xs)
        slope = (sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / denom) if denom else 0.0
        grad[sp] = {
            "alt_min": int(xs[0]),
            "alt_max": int(xs[-1]),
            "doy_min": round(ys[0], 1),
            "doy_max": round(ys[-1], 1),
            "span_days": round(ys[-1] - ys[0], 1),
            "days_per_100m": round(slope * 100, 2),
        }
    insights["ALT_GRADIENT"] = grad

    # Autumn colour: mean 10%->50% progression width per species.
    colour = {}
    for sp in DASHBOARD_SPECIES:
        b10 = {a["a"]: a["d"] for a in alt if a["s"] == sp and a.get("st") == "Changement de couleur"}
        b50 = {a["a"]: a["d"] for a in alt50 if a["s"] == sp}
        common = sorted(set(b10) & set(b50))
        if not common:
            colour[sp] = None
            continue
        widths = [b50[a] - b10[a] for a in common]
        lo, hi = common[0], common[-1]
        colour[sp] = {
            "n_bands": len(common),
            "mean_width_days": round(sum(widths) / len(widths), 1),
            "alt_min": int(lo),
            "alt_max": int(hi),
            "trend_days": round(b10[hi] - b10[lo], 1),  # <0 = earlier up high
        }
    insights["COLOUR_PROGRESSION"] = colour

    # Débourrement: earliest species overall, and the most extreme years.
    deb = [t for t in timing if t["st"] == "Débourrement"]
    if deb:
        by_sp = {}
        for t in deb:
            by_sp.setdefault(t["s"], []).append(t["d"])
        means = {k: sum(v) / len(v) for k, v in by_sp.items()}
        earliest = min(means, key=means.get)
        by_year = {}
        for t in deb:
            by_year.setdefault(t["y"], []).append(t["d"])
        ymeans = {y: sum(v) / len(v) for y, v in by_year.items()}
        ranked = sorted(ymeans.items(), key=lambda kv: kv[1])
        insights["DEBOURREMENT"] = {
            "earliest_species": earliest,
            "earliest_species_doy": round(means[earliest], 1),
            "early_years": [int(y) for y, _ in ranked[:3]],
            "late_years": [int(y) for y, _ in ranked[-3:]],
            "spread_days": round(ranked[-1][1] - ranked[0][1], 1),
        }

    # Recent contribution trend (last 6 years of the OBS series) + whether the
    # Alps heatmap totals are actually declining, and since when.
    obs_list = out["OBS"]
    insights["RECENT_OBS"] = obs_list[-6:]
    alps_by_year = {}
    for sp_data in heatmap.values():
        for r in sp_data["data"]:
            alps_by_year[r["year"]] = alps_by_year.get(r["year"], 0) + r["count"]
    if alps_by_year:
        peak_year = max(alps_by_year, key=alps_by_year.get)
        yrs = sorted(alps_by_year)
        last = yrs[-1]
        insights["ALPS_TREND"] = {
            "peak_year": int(peak_year),
            "peak_count": int(alps_by_year[peak_year]),
            "last_year": int(last),
            "last_count": int(alps_by_year[last]),
            "declining_since_peak": bool(alps_by_year[last] < alps_by_year[peak_year]),
            "pct_vs_peak": round(100.0 * alps_by_year[last] / alps_by_year[peak_year], 1),
        }

    # Weakest regions / species, for the call-to-action list.
    insights["WEAKEST_REGIONS"] = [
        region_label.get(k, k) for k in reg_counts.index[-2:]
    ][::-1]
    insights["WEAKEST_SPECIES"] = [k for k in sp_counts.index[-3:]][::-1]

    out["INSIGHTS"] = insights

    return out


# ──────────────────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────────────────
def main():
    # --raw PATH reads a cached raw_items.json instead of hitting the API.
    # Handy for reruns/testing and when the API is unavailable.
    raw_path = None
    if "--raw" in sys.argv:
        i = sys.argv.index("--raw")
        raw_path = sys.argv[i + 1] if i + 1 < len(sys.argv) else "raw_items.json"

    if raw_path:
        print(f"1/3  Loading cached raw export from {raw_path} ...")
        payload = json.load(open(raw_path, encoding="utf-8"))
        items = payload["items"] if isinstance(payload, dict) else payload
        license_name = (payload.get("license", {}).get("name")
                        if isinstance(payload, dict) else None)
    else:
        print("1/3  Fetching from CREA API ...")
        items, license_name = fetch_all()
    print(f"     got {len(items)} raw rows")

    print("2/3  Cleaning ...")
    df = clean(items)
    print(f"     {len(df)} rows after cleaning/filtering")

    print("3/3  Aggregating ...")
    agg = aggregate(df, raw_items=items)
    agg["LICENSE"] = license_name or "CC-BY 1.0"
    agg["GENERATED"] = time.strftime("%Y-%m-%d")

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(agg, f, ensure_ascii=False, separators=(",", ":"))
    size_kb = round(len(json.dumps(agg)) / 1024, 1)
    print(f"\nWrote {OUTPUT}  ({size_kb} KB)")
    print("Headline:", agg["META"])


if __name__ == "__main__":
    main()
