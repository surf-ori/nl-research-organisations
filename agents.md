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

Four tiers:

- **Bronze** (`data/raw/`) — raw API/webpage responses, one subdirectory per stage.
  Gitignored (thousands of small files, ~34MB — too big/slow to commit) but
  reproducible any time via that stage's `fetch()`. Each subdirectory keeps a
  `.gitkeep` placeholder so the tree exists on a fresh clone.
- **Silver** (`data/processed/`) — one Parquet file per source (`ror.parquet`,
  `openalex.parquet`, `ukb_members.parquet`, ...), built by `src/processor.py` from
  whatever's currently in `data/raw/` + `data/curated/`. Committed — small, uniform,
  and what both `notebook.py`'s Dataset Preview and the published
  `apps/dashboard.py` actually read (neither reads `data/raw/` directly — GitHub
  Pages can't, and re-parsing thousands of raw files on every preview is slow). Each
  source also gets `data/processed/<name>_metadata.json` (copied from that stage's
  raw `_metadata.json`), which drives the freshness cards.
- **Curated** (`data/curated/*.csv`) — hand/LLM-maintained membership lists.
  Committed; this is the only copy, there's no upstream API to re-derive it from.
- **Gold** (`data/nl_research_orgs.parquet`/`.csv`) — the final assembled output.
  Committed.

Only `__pycache__`, `.env`, `__marimo__/`, `apps/public/` (a build artifact, see
below), and `data/raw/**` (bronze, see above) are gitignored.

| File | Description |
|------|-------------|
| `data/nl_research_orgs.parquet` | Primary output — committed |
| `data/nl_research_orgs.csv` | CSV copy — committed |
| `data/raw/<stage>/...` | Per-stage bronze cache — gitignored, regenerate via that stage's `fetch()` |
| `data/processed/<name>.parquet` | Per-source silver snapshot — committed, built by `src/processor.py`'s `fetch()` |
| `data/processed/<name>_metadata.json` | Fetch timestamp + record count per stage — committed |
| `data/curated/*.csv` | Hand/LLM-maintained membership lists — committed |
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
6. Wire it into `src/processor.py`'s `fetch()` so it gets a `data/processed/<name>.parquet`
   silver snapshot — this is what Dataset Preview (both `notebook.py` and
   `apps/dashboard.py`) actually reads, not `data/raw/` directly
7. Add a test module under `tests/` (mock `requests` calls; see `tests/test_barcelona.py`
   or `tests/test_duo_ho_mbo.py`)
8. Document in this file and README.md (data sources table, column reference, API keys table)

## Known limitations

- **ALEI/KVK**: verified against the live overheid.io API (2026-07) — see
  `src/alei_fetcher.py`'s docstring. Coverage is low (roughly 6% of orgs matched) because
  OpenKvK's search is a text match against Dutch legal entity names, which often differ
  from a research organisation's public/brand name (e.g. "Vrije Universiteit Amsterdam"
  is legally "Stichting VU") — the module tries the org's aliases as fallback queries,
  but a curated legal-name list would likely raise coverage further.
- **EU PIC**: implemented but **unverified against the live API** — the implementer
  has no EU Login credentials to test with. See the `ponytail:` note in
  `src/pic_fetcher.py`'s docstring before trusting its output; verify request/response
  shapes the first time real credentials exist.
- **DUO HO/MBO matching undercounts**: it only matches ROR orgs by *exact* name or
  alias against DUO's official (usually Dutch) institution names — many ROR orgs use
  an English display name with no matching Dutch alias, so they won't match even
  though they are real HO/MBO institutions. This is deliberate: an earlier
  fuzzy-matching attempt produced confident-looking false positives between unrelated
  institutions sharing a generic suffix (e.g. "X University of Applied Sciences").
  Missing matches are safer than wrong ones, but this means `is_duo_institute`
  should be read as "confirmed match found", not "definitely not an HO/MBO
  institution" when `False`. HO and MBO matches are combined into one set of
  `duo_*` columns (no ROR org has been found in both lists) — `duo_institute_type`
  carries the HO ("SOORT HO") or MBO ("MBO INSTELLINGSSOORT - CODE") type code
  as-is, so which vocabulary a value belongs to still tells you HO vs MBO.
- **OpenAIRE credentials** are optional but recommended for volume; without them the
  public (lower rate limit) endpoint is used automatically
- **Membership CSVs** are seeded with known data as of 2026-06 — use LLM auto-update or manual editing to keep them current
- **ROR API** has no key requirement but rate-limits at ~1000 req/hr
- **Barcelona Declaration CSV** column names may change — check `src/barcelona.py` if matching breaks

## Zenodo archival

This repo is archived on Zenodo (concept DOI `10.5281/zenodo.21416468`, always
resolves to the latest version). Metadata is defined in `.zenodo.json` at the repo
root. Keeping a new GitHub release and a new Zenodo version in sync — matching
version strings, attaching `data/nl_research_orgs.csv`/`.parquet` alongside the
repo snapshot, setting the CSV as the default file preview, updating
`related_identifiers`/`custom.code:codeRepository` — follows the
`zenodo-github-release-sync` skill, published at
[github.com/surf-ori/agentic-tools/skills/zenodo-github-release-sync](https://github.com/surf-ori/agentic-tools/tree/main/skills/zenodo-github-release-sync)
(install with `npx skills add surf-ori/agentic-tools@zenodo-github-release-sync`),
which documents the full REST API workflow and is written to be reusable across
projects, not specific to this repo. **Always confirm with the user before
creating a GitHub release or publishing/editing a Zenodo deposition** — both are
public and hard or impossible to fully undo.

## Contact

Maurice Vanderfeesten — maurice.vanderfeesten@gmail.com
