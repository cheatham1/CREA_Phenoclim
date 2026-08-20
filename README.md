## An interactive dashboard showing the impact of participants' phenology observations, powered directly by the CREA Mont-Blanc Phénoclim data API.

# CREA
CREA Mont-Blanc is a scientific NGO whose mission is to explore the impact of climate change on biodiversity and to share this knowledge with decision-makers and citizens.

# Phenology
The Phenoclim program seeks to measure and understand the impact of climatic changes on the phenology (seasonal rhythms) of different species found in mountain environments. In spring and fall, common tree and plant species as well as bird species are monitored by CREA Mont-Blanc's researchers and volunteers across the Alps. Phenoclim is a participatory science program, and since 2004 has received contributions from over 5,000 citizen scientists, including several hundred who participate every year.

Phénoclim est un programme scientifique et pédagogique initié en 2004 par le Centre de Recherches sur les Écosystèmes d'Altitude (CREA) qui invite le public à mesurer l'impact du changement climatique sur la faune et la flore en montagne par le biais d'un programme scientifique participatif.

https://creamontblanc.org/en/citizen-science/

# Phénoclim Dashboard

A static dashboard visualising seasonal (phenological) observations from the
CREA Phénoclim citizen-science network:
when trees leaf out, flower, and change colour across France's mountain massifs,
and how that varies by region, altitude, and year.

The page is plain HTML/JavaScript. It reads a single pre-computed data file,
`phenoclim_data.json`, which is regenerated from the CREA API on a schedule.
There is no server and no database to run.

---

## What's in the repo

**Published to the web (served by GitHub Pages):**

- `phenoclim_dashboard.html` — the dashboard. Fetches `phenoclim_data.json` at load time.
- `phenoclim_data.json` — the pre-aggregated data the dashboard renders. **Regenerated automatically** (see *Automatic updates*).

**The build pipeline (runs in CI, not in the browser):**

- `build_phenoclim_data.py` — fetches the full export from the CREA API, cleans it, assigns regions, and writes `phenoclim_data.json`.
- `region_assign.py` — the region-allocation engine (see *Region allocation* below).
- `refresh_phenoclim.py` — convenience wrapper for running the refresh locally.
- `requirements.txt` — Python dependencies for the pipeline.
- `.github/workflows/refresh.yml` — the scheduled GitHub Actions job.

**Reference data (used only during the build):**

- `a-com2022-topo-2154.json` — official French commune contours (TopoJSON, Lambert-93 / EPSG:2154), carrying each commune's INSEE code and département. Source: *Contours des communes de France simplifié*, data.gouv.fr.
- `diffusion-zonages-massifs-cog2021.xls` — official *loi Montagne* commune-to-massif list (INSEE → massif). Source: ANCT / data.gouv.fr, *Communes classées en massif*.

**Cache (regenerated, safe to delete):**

- `zone_regions.csv` — a `nom_zone → region` lookup so recurring builds only geocode genuinely new monitoring zones. If you change the region logic, delete this file (or run with `--refresh-regions`) so it rebuilds.

---

## Automatic updates

Data refreshes from the CREA API with **no manual intervention**, on a cadence
matched to the phenology calendar:

- **Spring (March–May)** and **autumn (September–November)** — the active
  observing seasons — refresh **weekly**.
- **Rest of the year** — refresh **monthly** (first run of the month only).

This is implemented in `.github/workflows/refresh.yml`. GitHub's cron scheduler
has no concept of seasons, so the workflow is triggered **weekly year-round** and
decides *at runtime* whether the current week should rebuild:

- In an active-season month → always rebuild.
- Otherwise → rebuild only if it's the first Monday of the month; skip otherwise.

When it runs, the workflow fetches the live export, regenerates
`phenoclim_data.json`, and commits it back to the repo **only if the data
changed**. GitHub Pages then serves the updated file automatically. You can also
trigger a run by hand from the **Actions** tab (with an optional *force* toggle).

To run the same refresh locally:

```bash
pip install -r requirements.txt
export PHENO_COMMUNES=./a-com2022-topo-2154.json
export PHENO_MASSIF=./diffusion-zonages-massifs-cog2021.xls
python build_phenoclim_data.py           # live API
# or, offline from a cached export:
python build_phenoclim_data.py --raw raw_items.json
```

---

## Region allocation

Every observation is assigned to exactly one **region**. The nine regions are:

> Alpes du Nord · Alpes du Sud · Mont-Blanc · Jura · Vosges · Massif Central ·
> Pyrénées · Corse · Autre (*Other*)

Assignment is **spatial and exact**, not based on bounding boxes or postcodes.
Each observation carries Lambert-93 coordinates (`coord_x_2154` / `coord_y_2154`)
in the same projection as the official commune contours, so the pipeline can
place each point in its commune directly.

### The steps

**1. Sanity filter.** Observations with impossible coordinates (the raw export
contains a few stray points far outside France) are dropped: kept only if
latitude ∈ [41, 51.5] and longitude ∈ [−5.5, 10].

**2. Point-in-polygon → commune.** Each observation is located *within* a commune
polygon (`a-com2022-topo-2154.json`), yielding the commune's **INSEE code** and
**département**.

**3. Commune → massif.** The INSEE code is joined to the official *loi Montagne*
list (`diffusion-zonages-massifs-cog2021.xls`), giving the massif: Alpes, Jura,
Vosges, Massif Central, Pyrénées, Corse — or **"Hors massif"**, which becomes
**Autre / Other**. (A handful of communes flagged "partiellement" are treated as
belonging to their named massif.)

> **Note on what "massif" means.** The *loi Montagne* perimeters are
> **administrative**: they deliberately include piedmonts and connecting plains,
> not just mountain terrain. So a "Jura" or "Alpes" label is an administrative
> statement, not a topographic one — observers living in the foothills fall
> inside the massif too. Communes genuinely outside every massif (e.g. lowland
> Rhône) are labelled **Autre**.

**4. Split the Alps into North and South.** For observations whose massif is
**Alpes**, the massif label is refined **by département** (following the standard
CREA definition):

- **Alpes du Nord** — Savoie (73), Haute-Savoie (74), Isère (38).
- **Alpes du Sud** — Drôme (26), Vaucluse (84), Hautes-Alpes (05),
  Alpes-de-Haute-Provence (04), Alpes-Maritimes (06).

The rule is **massif-first**: a point must already be in the Alps massif *and*
in one of those départements. Départements do not override massif membership, so
lowland communes outside the Alpine perimeter are not pulled in.

**5. Extract Mont-Blanc.** Observations in the Chamonix / Mont-Blanc valley area
are pulled out of *Alpes du Nord* into their own **Mont-Blanc** region. This is
currently defined by a geographic box (latitude 45.75–46.05, longitude
6.60–7.10), which spans the massif on both sides of the border. CREA's densest
monitoring is here, so it warrants its own region rather than dominating
*Alpes du Nord*.

**6. Foreign observations.** The Phénoclim network extends into Italy,
Switzerland, Spain, and Andorra. These points fall outside every French commune,
so step 2 returns no match. They are classified by coordinate band, following
CREA's country rule:

- Eastern Alpine band (Italy / Switzerland) → **Alpes** → **Alpes du Nord**.
- South-western band (Spain / Andorra) → **Pyrénées**.

This is the **one approximate step**: the French commune file cannot classify
foreign points, so they are assigned by geography rather than by an official
boundary. Everything inside France is an exact commune lookup. (An Italian /
Swiss commune layer, or a country field from reverse-geocoding, would make the
foreign side exact too.)

### Caching

The `nom_zone → region` mapping is stable between runs, so it is cached in
`zone_regions.csv`; a scheduled refresh only re-assigns monitoring zones it has
not seen before. Delete the cache (or pass `--refresh-regions`) to force a full
re-assignment — do this whenever you change any of the rules above.

---

## Data & licence

Observation data © CREA Mont-Blanc / Phénoclim, via the GeoNature export API.
Reference geographies from data.gouv.fr / ANCT under the *Licence Ouverte*.
Please retain the attribution shown in the dashboard footer.

Developed with the help of Claude.ai Opus4.8
