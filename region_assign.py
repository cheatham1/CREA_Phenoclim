#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
region_assign.py — EXACT region assignment for the Phénoclim dashboard.

Method (no geocoding needed)
----------------------------
Each observation carries Lambert-93 coordinates (coord_x_2154 / coord_y_2154).
We point-in-polygon them against the official commune contours (same CRS) to get
the INSEE code, then:
  INSEE -> massif        (diffusion-zonages-massifs-cog2021.xls)
  INSEE -> departement   (carried on the commune contours themselves)
  massif == 'Alpes'      -> split into Alpes du Nord / Alpes du Sud by dept
  Mont-Blanc  -> pulled out of Alpes du Nord (transboundary box)
  'Hors massif'          -> Other
Foreign observations (no French commune) are classed by coordinate quadrant,
matching the R country rule: eastern Alps band -> Alps (IT/CH -> Nord), south-
western band -> Pyrénées (ES/AD).

Split rule (massif-first, per your definition)
  Alpes du Nord = Alps ∩ dept {73 Savoie, 74 Haute-Savoie, 38 Isère}  + IT/CH
  Alpes du Sud  = Alps ∩ dept {04, 05, 06, 26, 84}

Caching
-------
The zone→region lookup is stable, so it is cached (CACHE_CSV). Recurring runs
only re-assign zones not already in the cache. Pass refresh=True to rebuild.

Reference files (set via env or defaults):
  PHENO_COMMUNES  a-com2022-topo-2154.json   (TopoJSON, layer a_com2022, EPSG:2154)
  PHENO_MASSIF    diffusion-zonages-massifs-cog2021.xls
"""
import os, json
import pandas as pd

CACHE_CSV = os.environ.get("PHENO_REGION_CACHE", "zone_regions.csv")
COMMUNES  = os.environ.get("PHENO_COMMUNES", "a-com2022-topo-2154.json")
MASSIF    = os.environ.get("PHENO_MASSIF",   "diffusion-zonages-massifs-cog2021.xls")

DEPTS_NORD = {"73", "74", "38"}
DEPTS_SUD  = {"26", "84", "05", "04", "06"}
MONT_BLANC_BOX = (45.75, 46.05, 6.60, 7.10)  # lat_min,lat_max,lon_min,lon_max
SANE = (41.0, 51.5, -5.5, 10.0)

LABEL = {"Alpes":"Alpes","Jura":"Jura","Vosges":"Vosges",
         "Massif Central":"Massif Central","Pyrénées":"Pyrenees",
         "Corse":"Corse","Hors massif":"Other"}


def _load_communes():
    import geopandas as gpd
    com = gpd.read_file(COMMUNES, layer="a_com2022").set_crs("EPSG:2154")
    xlm = pd.ExcelFile(MASSIF, engine="calamine")
    m = xlm.parse("Communes de massif (COG 2021)", header=5, dtype=str)[["CODGEO","MASSIF"]].dropna(subset=["CODGEO"])
    m["MASSIF"] = m["MASSIF"].str.replace(" (partiellement)","",regex=False)
    com = com.merge(m, left_on="codgeo", right_on="CODGEO", how="left")
    return com[["codgeo","dep","MASSIF","geometry"]]


def _foreign_massif(lat, lon):
    if lon < 3.5 and lat < 43.5:  return "Pyrénées"   # ES / Andorra
    if lon > 6.2 and lat < 47.5:  return "Alpes"      # IT / CH
    return None


def _assign_points(df):
    """Point-in-polygon assign a dataframe of observations. Needs coord_*_2154
    and coord_*_4326 columns. Returns df with a 'region' column."""
    import geopandas as gpd
    from shapely.geometry import Point
    com = _load_communes()
    pts = gpd.GeoDataFrame(
        df, geometry=[Point(x,y) for x,y in zip(df.coord_x_2154, df.coord_y_2154)],
        crs="EPSG:2154")
    j = gpd.sjoin(pts, com, how="left", predicate="within")
    j = j[~j.index.duplicated(keep="first")].copy()

    un = j["codgeo"].isna()
    j.loc[un,"MASSIF"] = [_foreign_massif(la,lo)
                          for la,lo in zip(j.loc[un,"coord_y_4326"], j.loc[un,"coord_x_4326"])]
    j["massif"] = j["MASSIF"].map(LABEL).fillna(j["MASSIF"]).fillna("Other")

    def region(r):
        if r["massif"] != "Alpes": return r["massif"]
        d = r["dep"]
        if pd.isna(d): return "Alpes du Nord"     # foreign Alps (IT/CH)
        if d in DEPTS_NORD: return "Alpes du Nord"
        if d in DEPTS_SUD:  return "Alpes du Sud"
        return "Alpes du Nord"
    j["region"] = j.apply(region, axis=1)

    la0,la1,lo0,lo1 = MONT_BLANC_BOX
    in_mb = j.coord_y_4326.between(la0,la1) & j.coord_x_4326.between(lo0,lo1)
    j.loc[in_mb & (j.region=="Alpes du Nord"), "region"] = "Mont-Blanc"
    return j


def _sane(df):
    df = df.copy()
    # accept either raw coord_*_4326 or the renamed latitude/longitude
    if "coord_y_4326" not in df.columns and "latitude" in df.columns:
        df["coord_y_4326"] = df["latitude"]
    if "coord_x_4326" not in df.columns and "longitude" in df.columns:
        df["coord_x_4326"] = df["longitude"]
    for c in ("coord_x_2154","coord_y_2154","coord_x_4326","coord_y_4326"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["coord_x_2154","coord_y_2154","coord_x_4326","coord_y_4326"])
    la0,la1,lo0,lo1 = SANE
    return df[df.coord_y_4326.between(la0,la1) & df.coord_x_4326.between(lo0,lo1)].copy()


def assign_regions(items_df, refresh=False, cache_csv=CACHE_CSV):
    """Return a nom_zone -> region lookup (DataFrame: nom_zone, region),
    caching so recurring runs only assign new zones."""
    df = _sane(items_df)

    cached = pd.DataFrame()
    if not refresh and os.path.exists(cache_csv):
        cached = pd.read_csv(cache_csv)
        known = set(cached["nom_zone"])
        todo = df[~df["nom_zone"].isin(known)]
        print(f"  region cache: {len(known)} zones cached, "
              f"{todo['nom_zone'].nunique()} new to assign")
        if todo["nom_zone"].nunique() == 0:
            return cached
        df = todo
    elif refresh:
        print("  --refresh: rebuilding the whole zone→region lookup")

    j = _assign_points(df)
    fresh = (j.groupby("nom_zone")["region"]
             .agg(lambda s: s.value_counts().index[0]).reset_index())
    out = pd.concat([cached, fresh], ignore_index=True) if len(cached) else fresh
    out = out.drop_duplicates(subset="nom_zone", keep="last")
    out.to_csv(cache_csv, index=False)
    print(f"  wrote {cache_csv} ({len(out)} zones)")
    return out


if __name__ == "__main__":
    import sys
    src = sys.argv[1] if len(sys.argv) > 1 else "raw_items.json"
    payload = json.load(open(src, encoding="utf-8"))
    items = payload["items"] if isinstance(payload, dict) else payload
    df = pd.DataFrame(items)
    lk = assign_regions(df, refresh="--refresh" in sys.argv)
    j = _assign_points(_sane(df))
    print("\nobservations per region:")
    print(j["region"].value_counts().to_string())
