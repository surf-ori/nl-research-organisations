# agents.md — NL Research Organisations

## What this repo is

This repository builds and maintains `data/nl_research_orgs.parquet` and `data/nl_research_orgs.csv` — a 35-column reference table of all research organisations in the Kingdom of the Netherlands, enriched with identifiers from ROR, OpenAlex, OpenAIRE, Barcelona Declaration, and 9 Dutch consortium/membership lists.

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

Valid source values: `ror`, `zenodo`, `openalex`, `openaire`, `alei`, `pic`, `barcelona`, `memberships`, `assemble`, `all`

## Required environment variables

| Variable | Used by | Required? |
|----------|---------|-----------|
| `OPENALEX_API_KEY` | src/openalex.py | Optional (rate limit is lower without it) |
| `OPENALEX_MAILTO` | src/openalex.py | Recommended |
| `OPENAIRE_REFRESH_TOKEN` | src/openaire.py | Yes (skipped if missing) |
| `LLM_BASE_URL` | src/llm_curator.py | For membership auto-update |
| `LLM_API_KEY` | src/llm_curator.py | For membership auto-update |
| `LLM_MODEL` | src/llm_curator.py | For membership auto-update |
| `KVK_API_KEY` | src/alei_fetcher.py | Placeholder — not yet implemented |
| `EU_PIC_API_KEY` | src/pic_fetcher.py | Placeholder — not yet implemented |

Copy `.env.example` to `.env` and fill in values.

## Data file locations

| File | Description |
|------|-------------|
| `data/nl_research_orgs.parquet` | Primary output — committed |
| `data/nl_research_orgs.csv` | CSV copy — committed |
| `data/raw/ror/page_<CC>_<NNN>.json` | ROR API page cache — gitignored |
| `data/raw/openalex/<ror_id>.json` | OpenAlex per-org cache — gitignored |
| `data/raw/openaire/<ror_id>.json` | OpenAIRE per-org cache — gitignored |
| `data/raw/barcelona/signatories.csv` | Barcelona Declaration download — gitignored |
| `data/raw/zenodo/nl-orgs-baseline.xlsx` | Zenodo baseline — gitignored |
| `data/curated/*.csv` | Hand/LLM-maintained membership lists — **committed** |
| `data/raw/*/_metadata.json` | Fetch timestamp + record count — gitignored |

## Module contract

Every `src/*.py` stage is a marimo notebook that also works as a Python module. To add a new data source:

1. Create `src/mysource.py` as a marimo notebook
2. Define at module level (outside cells):
   ```python
   def fetch(force_refresh: bool = False) -> dict:
       # fetch and cache to data/raw/mysource/
       # write data/raw/mysource/_metadata.json
       return {"record_count": int, "fetched_at": "ISO8601", "output_path": str}

   def load_results() -> dict[str, str | None]:
       # return {ror_id_url: value_or_none}
       return {}
   ```
3. Import and call in `src/assembler.py` to add the column
4. Add a stage card in `notebook.py` STAGE_META dict
5. Add to `pipeline.py` ORDER list
6. Document in this file and README.md

## Known limitations

- **ALEI/KVK and PIC IDs** are empty placeholder columns — awaiting API access
- **OpenAIRE refresh tokens** expire; if lookups fail, obtain a new token
- **Membership CSVs** are seeded with known data as of 2026-06 — use LLM auto-update or manual editing to keep them current
- **ROR API** has no key requirement but rate-limits at ~1000 req/hr
- **Barcelona Declaration CSV** column names may change — check `src/barcelona.py` if matching breaks

## Contact

Maurice Vanderfeesten — maurice.vanderfeesten@gmail.com
