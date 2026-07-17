# agents.md — NL Research Organisations

## What this repo is

This repository builds and maintains `data/nl_research_orgs.parquet` and `data/nl_research_orgs.csv` — a 47-column reference table of all research organisations in the Kingdom of the Netherlands, enriched with identifiers from ROR, OpenAlex, OpenAIRE (plus PIC/GRID/Wikidata/ISNI/VIAF/RingGold/FundRef/OrgRef/OrgReg/RRID/LinkedIn/MAG extracted from OpenAIRE's cached `pids` array), EU PIC, ALEI/KVK, the Barcelona Declaration, DUO's official HO/MBO institution address lists, and 9 Dutch consortium/membership lists.

A read-only snapshot (`apps/dashboard.py`) is also published to GitHub Pages via WASM on every push to `master` — see README.md's "Published read-only app" section.

## How to run the pipeline

Full pipeline (fetches everything, writes parquet + CSV):

```bash
uvx marimo run pipeline.py -- --source all
```

Force re-fetch even if cache exists:

```bash
uvx marimo run pipeline.py -- --source all --force-refresh true
```

Single stage:

```bash
uvx marimo run pipeline.py -- --source ror
```

Valid source values: `ror`, `zenodo`, `openalex`, `openaire`, `alei`, `pic`, `barcelona`, `duo`, `memberships`, `assemble`, `all`

Note: `pic` and `alei` search their APIs by organisation name rather than ROR ID, so
their stage dispatch passes the full org list (`load_orgs()`), not just ROR URLs —
see the `elif stage == "pic"` / `elif stage == "alei"` branches in `pipeline.py` and
`notebook.py` if adding another name-keyed source.

## Required environment variables

| Variable | Used by | Required? |
|----------|---------|-----------|
| `OPENALEX_API_KEY` | src/openalex.py | Optional (rate limit is lower without it) |
| `OPENALEX_MAILTO` | src/openalex.py | Recommended |
| `OPENAIRE_CLIENT_ID`, `OPENAIRE_CLIENT_SECRET` | src/openaire.py | Optional (Graph API is public without auth, at a lower rate limit) |
| `LLM_BASE_URL` | src/llm_curator.py | For membership auto-update |
| `LLM_API_KEY` | src/llm_curator.py | For membership auto-update |
| `LLM_MODEL` | src/llm_curator.py | For membership auto-update |
| `OVERHEID_IO_API_KEY` | src/alei_fetcher.py | Yes (skipped, reports 0 records, if missing) — **unverified against the live API**, see the module's `ponytail:` docstring note |
| `EU_LOGIN_CLIENT_ID`, `EU_LOGIN_CLIENT_SECRET` | src/pic_fetcher.py | Yes (skipped, reports 0 records, if missing) — **unverified against the live API**, see the module's `ponytail:` docstring note |

Copy `.env.example` to `.env` and fill in values. See README.md's "API keys" table for signup links.

## Data file locations

All of `data/raw/` is committed (~34MB) for transparency — anyone can inspect exactly
what each stage fetched, via GitHub's file browser or a local clone. Only
`__pycache__`, `.env`, `__marimo__/`, and `apps/public/` (a build artifact, see below)
are gitignored.

| File | Description |
|------|-------------|
| `data/nl_research_orgs.parquet` | Primary output — committed |
| `data/nl_research_orgs.csv` | CSV copy — committed |
| `data/raw/ror/page_<CC>_<NNN>.json` | ROR API page cache — committed |
| `data/raw/openalex/<ror_id>.json` | OpenAlex per-org cache — committed |
| `data/raw/openaire/<ror_id>.json` | OpenAIRE per-org cache — committed |
| `data/raw/barcelona/signatories.csv` | Barcelona Declaration download — committed |
| `data/raw/zenodo/nl-orgs-baseline.xlsx` | Zenodo baseline — committed |
| `data/raw/duo/ho.json`, `data/raw/duo/mbo.json` | DUO HO/MBO address list dumps — committed |
| `data/curated/*.csv` | Hand/LLM-maintained membership lists — committed |
| `data/raw/*/_metadata.json`, `data/raw/_assembly_metadata.json` | Fetch timestamp + record count per stage — committed |
| `apps/public/` | Built by `apps/build_public.sh` for the published app; gitignored, regenerated on every deploy |

## Module contract

Every `src/*.py` stage is a marimo notebook that also works as a Python module. To add a new data source:

1. Create `src/mysource.py` as a marimo notebook
2. Define at module level (outside cells):
   ```python
   def fetch(force_refresh: bool = False) -> dict:
       # fetch and cache to data/raw/mysource/
       # write data/raw/mysource/_metadata.json
       # Data-fetching stages return source_url; the assembler returns output_path instead.
       return {"record_count": int, "fetched_at": "ISO8601", "source_url": str}

   def load_results() -> dict[str, str | None]:
       # return {ror_id_url: value_or_none}
       return {}
   ```
   Note: `src/assembler.py` is the exception — its `fetch()` returns `output_path` (the path to the
   written parquet) instead of `source_url`, because it produces a file rather than fetching from a URL.

   If your source matches by organisation name rather than ROR ID (like `pic`/`alei`/`duo`),
   `load_results()` takes `ror_orgs: list[dict]` instead and does its own matching — see
   `src/barcelona.py` (fuzzy `difflib` match — only safe when names are in the same
   language/convention) or `src/duo_ho_mbo.py` (exact match — required when they aren't,
   see that module's `_match()` docstring for why).
3. Import and call in `src/assembler.py` to add the column(s), and add them to `COLUMN_ORDER`
4. Add a stage card in `notebook.py`'s `STAGE_META` dict, and wire up its refresh handler
   in both `full_refresh` and `pipeline_section` if it needs `orgs`/`ror_urls` as input
5. Add to `pipeline.py`'s `STAGES`/`ORDER` (and its `elif` dispatch if it needs `orgs`/`ror_urls`)
6. Add a test module under `tests/` (mock `requests` calls; see `tests/test_barcelona.py`
   or `tests/test_duo_ho_mbo.py`)
7. Document in this file and README.md (data sources table, column reference, API keys table)

## Known limitations

- **ALEI/KVK and PIC IDs**: both are implemented but **unverified against the live
  API** — neither the requester nor the implementer has credentials for either
  service. See the `ponytail:` note in each module's docstring before trusting their
  output; verify request/response shapes the first time real credentials exist.
- **DUO HO/MBO matching undercounts**: it only matches ROR orgs by *exact* name or
  alias against DUO's official (usually Dutch) institution names — many ROR orgs use
  an English display name with no matching Dutch alias, so they won't match even
  though they are real HO/MBO institutions. This is deliberate: an earlier
  fuzzy-matching attempt produced confident-looking false positives between unrelated
  institutions sharing a generic suffix (e.g. "X University of Applied Sciences").
  Missing matches are safer than wrong ones, but this means `is_ho_institution`/
  `is_mbo_institution` should be read as "confirmed match found", not "definitely not
  an HO/MBO institution" when `False`.
- **OpenAIRE credentials** are optional but recommended for volume; without them the
  public (lower rate limit) endpoint is used automatically
- **Membership CSVs** are seeded with known data as of 2026-06 — use LLM auto-update or manual editing to keep them current
- **ROR API** has no key requirement but rate-limits at ~1000 req/hr
- **Barcelona Declaration CSV** column names may change — check `src/barcelona.py` if matching breaks

## Contact

Maurice Vanderfeesten — maurice.vanderfeesten@gmail.com
