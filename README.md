# Phénoclim — Les Saisons en Montagne

An interactive dashboard showing the impact of participants' phenology observations, powered directly by the CREA Mont-Blanc Phénoclim data API.

## CREA

CREA Mont-Blanc is a scientific NGO whose mission is to explore the impact of climate change on biodiversity and to share this knowledge with decision-makers and citizens.

## Phenology

The Phenoclim program seeks to measure and understand the impact of climatic changes on the phenology (seasonal rhythms) of different species found in mountain environments. In spring and fall, common tree and plant species as well as bird species are monitored by CREA Mont-Blanc's researchers and volunteers across the Alps. Phenoclim is a participatory science program, and since 2004 has received contributions from over 5,000 citizen scientists, including several hundred who participate every year.

Phénoclim est un programme scientifique et pédagogique initié en 2004 par le Centre de Recherches sur les Écosystèmes d'Altitude (CREA) qui invite le public à mesurer l'impact du changement climatique sur la faune et la flore en montagne par le biais d'un programme scientifique participatif.

https://creamontblanc.org/en/citizen-science/

## About this dashboard

This dashboard (generated with the help of Claude.ai) focuses on 4 tree species across 6 regions (Corsica currently has only 14 observations and is not shown).

**Data source.** The dashboard is powered directly by the CREA Mont-Blanc Phénoclim data API (a public GeoNature export). A build script (`build_phenoclim_data.py`) fetches the full public dataset (70,000+ observations), cleans and aggregates it following the project's established method, and writes a small summary file (`phenoclim_data.json`) that the page displays. This keeps the page fast to load and reliable, while reflecting the latest data.

**Automatic updates.** The data refreshes on a schedule matched to the phenology calendar — weekly during the active seasons (spring: March–May; autumn: September–November) and roughly monthly the rest of the year — with no manual intervention. The page shows the date of the last update and the data licence (CC-BY, CREA Mont-Blanc / Phénoclim).

**A note on the figures.** The headline observation count reflects all records contributed by participants. The analytical charts use the subset of validated, fully-attributed observations suitable for analysis, so their basis is slightly smaller; a short note on those charts explains the difference.

## The four visualizations

**📈 Tendances** — Phenological timing over 20+ years for the 4 main species, filterable by stage (débourrement, feuillaison, floraison, changement de couleur). This reveals year-to-year variability and potential climate-driven shifts — for instance, hazel flowering has been trending earlier, reaching as early as February 4th in 2020.

**⛰️ Altitude** — The altitudinal gradient of bud break, showing how spring arrives ~3 days later for every 100 m gain in elevation. Birch buds open 46 days later at 1800 m than at 200 m. This is a vivid, tangible result that participants can relate to from their own sites.

**🗺️ Régions** — Comparing phenology across the Alps, Pyrenees, Mont-Blanc, Massif Central, Jura, and Vosges. The Massif Central springs to life earliest, while high-altitude regions lag behind.

**🤝 Votre impact** — An observation counter (70,000+ total) and a motivational summary of why continued participation matters: the 20+ year time series is scientifically irreplaceable, and the altitude/geographic coverage is impossible to replicate with automated stations.

## Repository contents

| File | Purpose |
|------|---------|
| `phenoclim_dashboard.html` | The dashboard page (loads `phenoclim_data.json`). |
| `phenoclim_data.json` | Pre-aggregated data the page reads (regenerated automatically). |
| `build_phenoclim_data.py` | Fetches from the CREA API, cleans, aggregates, and writes the JSON. |
| `.github/workflows/update-phenoclim-data.yml` | GitHub Action that refreshes the data on schedule. |

## Running the build manually

```bash
pip install requests pandas
python build_phenoclim_data.py
```

This writes a fresh `phenoclim_data.json` next to the dashboard. Serve the folder over HTTP (e.g. `python -m http.server`) or publish via GitHub Pages — opening the HTML directly from disk will not load the data.

## Licence

Data: CC-BY 1.0 — CREA Mont-Blanc / Phénoclim. Please retain attribution when reusing.
