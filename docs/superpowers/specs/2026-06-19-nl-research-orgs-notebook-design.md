# Design Spec: NL Research Organisations Notebook

**Date:** 2026-06-19
**Author:** Maurice Vanderfeesten
**Status:** Approved

---

## Overview

A marimo notebook application that builds and maintains a comprehensive reference table of all research organisations in the Kingdom of the Netherlands (NL, AW, CW, SX, BQ — including special municipalities). The primary output is `data/nl_research_orgs.parquet` and `data/nl_research_orgs.csv`, committed to the repository so downstream tools can consume them without running the pipeline.

The notebook runs in **app mode** for interactive use and supports **headless/CLI mode** for automated/scheduled updates.

---

## Repository Structure

```
nl-research-organisations/
├── notebook.py                  # main orchestration app (marimo, app mode)
├── pipeline.py                  # thin CLI wrapper (marimo nb, headless)
├── src/
│   ├── ror_fetcher.py           # Stage 1: ROR API fetch & cache
│   ├── zenodo_baseline.py       # Stage 2: Zenodo baseline XLSX download
│   ├── openalex.py              # Stage 3a: OpenAlex institution ID lookup
│   ├── openaire.py              # Stage 3b: OpenAIRE org ID lookup
│   ├── alei_fetcher.py          # Stage 4: ALEI/KVK ID lookup (placeholder)
│   ├── pic_fetcher.py           # Stage 5: PIC ID lookup (placeholder)
│   ├── barcelona.py             # Stage 6: Barcelona Declaration CSV
│   ├── memberships.py           # Stage 7: membership list joins
│   ├── llm_curator.py           # on-demand: LLM-based membership CSV update
│   └── assembler.py             # Stage 8: DuckDB assembly → Parquet/CSV
├── data/
│   ├── raw/                     # gitignored — cached API responses (JSON, XLSX)
│   ├── curated/                 # committed — hand/LLM-maintained membership CSVs
│   │   ├── surf_members.csv
│   │   ├── ukb_members.csv
│   │   ├── shb_members.csv
│   │   ├── unl_members.csv
│   │   ├── umcnl_members.csv
│   │   ├── vh_members.csv
│   │   ├── knaw_institutes.csv
│   │   ├── nwoi_institutes.csv
│   │   └── openaire_members.csv
│   ├── nl_research_orgs.parquet # committed — primary output
│   └── nl_research_orgs.csv     # committed — primary output (human-readable)
├── .env                         # gitignored — API keys
├── .env.example                 # committed — key template
├── .gitignore
├── README.md
└── agents.md
```

---

## Packaging

All notebooks use inline `uv` script metadata so `uvx marimo run notebook.py` works with no separate install step:

```python
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "marimo",
#   "duckdb",
#   "requests",
#   "python-dotenv",
#   "openpyxl",
#   "anthropic",
# ]
# ///
```

Each sub-notebook declares only the dependencies it needs.

---

## Data Sources & Pipeline Stages

Each stage saves raw data to `data/raw/<source>/` and writes a `_metadata.json` sidecar with:
- `fetched_at`: ISO 8601 timestamp
- `record_count`: number of records
- `source_url`: the URL or API endpoint used

Stages skip fetching if `data/raw/<source>/` is non-empty, unless `--force-refresh` is passed.

### Stage 1 — ROR Fetch (`src/ror_fetcher.py`)

- Paginates `api.ror.org/v2/organizations` for each of the 6 country codes: `NL, AW, CW, SX, BQ`
- Results merged and deduplicated by ROR id
- Raw pages saved as `data/raw/ror/page_<CC>_<NNN>.json`
- DuckDB JSON path queries extract all 20 base columns (see Output Columns below)
- No API key required

### Stage 2 — Zenodo Baseline (`src/zenodo_baseline.py`)

- Downloads `nl-orgs-baseline.xlsx` from `https://zenodo.org/records/18957154/files/nl-orgs-baseline.xlsx?download=1`
- Saved to `data/raw/zenodo/nl-orgs-baseline.xlsx`
- Matched on ROR id → `ori_base_org` TRUE/FALSE

### Stage 3a — OpenAlex (`src/openalex.py`)

- Per-ROR-id lookup: `api.openalex.org/institutions?filter=ror:<ror_url>`
- Results cached individually as `data/raw/openalex/<ror_id>.json`
- Skips already-cached IDs on re-run
- Requires: `OPENALEX_API_KEY`, `OPENALEX_MAILTO`
- Output: `openalex_institution_id`

### Stage 3b — OpenAIRE (`src/openaire.py`)

- Obtains access token via refresh token from `aai.openaire.eu/oidc/token`
- Per-ROR-id lookup: `api.openaire.eu/graph/v1/organizations?pid=<ror_url>`
- Results cached as `data/raw/openaire/<ror_id>.json`
- Requires: `OPENAIRE_REFRESH_TOKEN`
- Output: `openaire_org_id`

### Stage 4 — ALEI / KVK (`src/alei_fetcher.py`) — Placeholder

- Skeleton module documenting the target API (KVK / ekys.org / ISO 8000-116 IBRN)
- `.env.example` stub: `KVK_API_KEY=`
- Assembler wires `alei_id` column as empty string until implemented
- Shows "Not yet implemented — awaiting API access" banner in the notebook UI

### Stage 5 — PIC ID (`src/pic_fetcher.py`) — Placeholder

- Skeleton module documenting the EU Participant Portal API
- `.env.example` stub: `EU_PIC_API_KEY=`
- Assembler wires `pic_id` column as empty string until implemented
- Shows "Not yet implemented — awaiting API access" banner in the notebook UI

### Stage 6 — Barcelona Declaration (`src/barcelona.py`)

- Direct CSV download from `https://barcelona-declaration.org/downloads/barcelonadeclaration_signatories_supporters.csv`
- Saved to `data/raw/barcelona/signatories.csv`
- Matched on ROR id; fuzzy name match as fallback
- Output: `is_barcelona_signatory` TRUE/FALSE

### Stage 7 — Memberships (`src/memberships.py`)

- Reads committed `data/curated/*.csv` files (each has at minimum a `ror_id` column)
- Produces boolean columns via DuckDB JOIN:
  - `is_surf_member`, `surf_member_type`
  - `is_ukb`
  - `is_shb`
  - `is_unl`
  - `is_umcnl`
  - `is_vh`
  - `is_knaw_institute`
  - `is_nwoi_institute`
  - `is_openaire_member`

### Stage 8 — Assembly (`src/assembler.py`)

- DuckDB reads all cached sources and JOINs on ROR id
- Writes `data/nl_research_orgs.parquet` and `data/nl_research_orgs.csv`
- ALEI_ID and PIC_ID present as empty string columns

### On-demand — LLM Curator (`src/llm_curator.py`)

- Not part of the sequential pipeline; triggered manually per membership source from Tab 3
- Accepts: base URL, API key, model name (from UI or `.env`)
- Sends source URL + current curated CSV to LLM, asks for updated CSV
- Uses Anthropic SDK by default; accepts any OpenAI-compatible endpoint
- After LLM response, notebook shows a diff (old vs new rows) for user confirmation before saving

---

## Module Contract

Every `src/*.py` stage module exposes:

```python
def fetch(force_refresh: bool = False) -> dict:
    """
    Fetch and cache data for this source.
    Returns: {"record_count": int, "fetched_at": str, "output_path": str}
    """
```

This contract means adding a real implementation to a placeholder is a one-file change with no assembler surgery.

---

## Output Columns

| Column | Source |
|---|---|
| `name` | ROR |
| `acronym` | ROR |
| `aliases` | ROR |
| `ror_id` | ROR |
| `ror_id_url` | ROR |
| `org_type` | ROR |
| `status` | ROR |
| `established_year` | ROR |
| `country_code` | ROR |
| `location_name` | ROR (`locations/geonames_details/name`) |
| `lat` | ROR |
| `lng` | ROR |
| `geonames_id` | ROR |
| `website_url` | ROR |
| `wikipedia_url` | ROR |
| `isni_id` | ROR |
| `wikidata_id` | ROR |
| `grid_id` | ROR |
| `fundref_id` | ROR |
| `ori_base_org` | Zenodo baseline |
| `openalex_institution_id` | OpenAlex |
| `openaire_org_id` | OpenAIRE |
| `alei_id` | ALEI/KVK (placeholder) |
| `pic_id` | EU PIC (placeholder) |
| `is_barcelona_signatory` | Barcelona Declaration |
| `is_surf_member` | data/curated/surf_members.csv |
| `surf_member_type` | data/curated/surf_members.csv |
| `is_ukb` | data/curated/ukb_members.csv |
| `is_shb` | data/curated/shb_members.csv |
| `is_unl` | data/curated/unl_members.csv |
| `is_umcnl` | data/curated/umcnl_members.csv |
| `is_vh` | data/curated/vh_members.csv |
| `is_knaw_institute` | data/curated/knaw_institutes.csv |
| `is_nwoi_institute` | data/curated/nwoi_institutes.csv |
| `is_openaire_member` | data/curated/openaire_members.csv |

Total: 35 columns.

---

## Notebook UI (App Mode)

Five tabs via `mo.ui.tabs()`:

### Tab 1 — Dashboard

- Summary stat row: total organisations, last full pipeline run timestamp
- Status card grid (one per stage): source name, record count, last-updated timestamp, freshness indicator (green < 7 days / amber < 30 days / red ≥ 30 days)
- `Full Refresh` button (runs all stages sequentially)
- `Export` button (triggers download of current Parquet + CSV)

### Tab 2 — Pipeline Stages

- One `mo.ui.accordion()` section per stage
- Each section: source URL, last-updated timestamp, record count, `Refresh this source` button, 10-row DuckDB preview
- Placeholder stages show a "Not yet implemented" banner instead of a refresh button

### Tab 3 — LLM Configuration

- Base URL text input (pre-populated from `LLM_BASE_URL` in `.env`)
- API key password input (pre-populated from `LLM_API_KEY` in `.env`)
- Model dropdown (populated from provider `/models` endpoint after "Test connection"; falls back to hardcoded list)
- `Test connection` button with inline success/error feedback
- Note: "Settings are session-only. To persist, add to your `.env` file."

### Tab 4 — Membership Curation

- One sub-section per curated CSV
- Each shows: reference source URL (clickable), editable table via `mo.ui.table(editable=True)`, `Save to CSV` button, `LLM Auto-update` button
- After LLM update: diff view (old vs new rows), `Accept` / `Discard` buttons

### Tab 5 — Output Preview

- `mo.ui.table(df)` of the assembled Parquet — marimo's built-in search, sort, filter, pagination, and column selection used as-is; no custom UI needed

---

## Headless / CLI Mode (`pipeline.py`)

```bash
uvx marimo run pipeline.py -- --source all
uvx marimo run pipeline.py -- --source ror --force-refresh
```

- Uses `mo.cli_args()` for `--source` and `--force-refresh`
- API keys read from `.env` via `python-dotenv`
- Prints per-stage progress to stdout
- Suitable for cron / CI

---

## Environment Variables

**`.env.example`:**

```dotenv
# OpenAlex
OPENALEX_API_KEY=your_key_here
OPENALEX_MAILTO=your@email.com

# OpenAIRE
OPENAIRE_REFRESH_TOKEN=your_token_here

# LLM curator (Anthropic default; any OpenAI-compatible endpoint works)
LLM_BASE_URL=https://api.anthropic.com
LLM_API_KEY=your_key_here
LLM_MODEL=claude-sonnet-4-6

# ALEI / KVK (placeholder — not yet implemented)
KVK_API_KEY=

# EU Participant Portal PIC (placeholder — not yet implemented)
EU_PIC_API_KEY=
```

`.env` is gitignored. `.env.example` is committed.

---

## `.gitignore`

```
.env
data/raw/
```

---

## README.md Outline

1. Project title + one-line description
2. What it produces and why
3. Data sources table (name, what it provides, update frequency, machine-readable?)
4. Quickstart: `uvx marimo run notebook.py`
5. Headless/CLI usage
6. How to add API keys
7. How to update membership lists (Tab 4)
8. Column reference table (all 35 columns)
9. Contributing / license

---

## agents.md Outline

1. What this repo is and what data it produces
2. How to run the pipeline (command, required env vars)
3. Data file locations and formats
4. Module contract: how to add a new data source
5. Known limitations (ALEI/PIC placeholders, rate limits, membership list staleness)
6. Contact / maintainer
