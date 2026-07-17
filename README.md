# NL Research Organisations

[![DOI](https://zenodo.org/badge/doi/10.5281/zenodo.21416468.svg)](https://doi.org/10.5281/zenodo.21416468)

A marimo notebook that builds and maintains a comprehensive reference table of all research organisations in the Kingdom of the Netherlands (NL, AW, CW, SX, BQ), enriched with identifiers from multiple databases.

Archived on Zenodo: [10.5281/zenodo.21416468](https://doi.org/10.5281/zenodo.21416468) (always resolves to the latest version).

## What it produces

- `data/nl_research_orgs.parquet` — primary output for downstream tools
- `data/nl_research_orgs.csv` — human-readable version

Both files are committed to this repository so you can use them without running the pipeline.

## Data sources

| Source | Provides | Auto-fetch? |
|--------|----------|------------|
| ROR API | 20 base columns per organisation | Yes |
| Zenodo ORI baseline | `ori_base_org` flag | Yes |
| OpenAlex | `openalex_institution_id`/`openalex_institution_id_url` | Yes (needs API key) |
| OpenAIRE | `openaire_org_id`/`openaire_org_id_url`, plus `pic_id`/`viaf_id`/`ringgold_id`/`orgref_id`/`orgreg_id`/`rrid_id`/`linkedin_url`/`mag_id` and a fallback for `isni_id`/`wikidata_id`/`grid_id`/`fundref_id` — all extracted from the same cached response's `pids` array, no extra API calls | Yes (needs refresh token) |
| Barcelona Declaration | `is_barcelona_signatory` | Yes (public CSV) |
| DUO HO/MBO address lists | `is_duo_institute`/`duo_institution_code`/`duo_institute_type`/`duo_straatnaam`/`duo_huisnummer`/`duo_postcode`/`duo_plaatsnaam` (HO and MBO combined — no ROR org matches both lists) | Yes (public JSON dumps, no key needed) |
| SURF, UKB, SHB, UNL, UMCNL, VH, KNAW-i, NWO-i, OpenAIRE members | Membership flags | Curated CSVs (LLM-updatable) |
| ALEI / KVK (overheid.io OpenKvK) | `alei_id` | Yes (needs API key; verified against the live API — see `src/alei_fetcher.py`) |
| EU PIC (Participant Register) | `pic_id` (also see the OpenAIRE fallback above) | Yes (needs API key; unverified against the live API — see `src/pic_fetcher.py`) |

## Data layout

- `data/raw/` — bronze, one subdirectory per source. **Gitignored** (thousands of
  small per-org files, too big/slow to commit) — reproducible any time via that
  source's `fetch()`.
- `data/processed/` — silver, one Parquet file per source, built by `src/processor.py`
  from whatever's currently cached in `data/raw/` + `data/curated/`. Committed — this
  is what both `notebook.py`'s Dataset Preview and the published dashboard actually
  read.
- `data/curated/*.csv` — hand/LLM-maintained membership lists. Committed; this is the
  only copy.
- `data/nl_research_orgs.parquet`/`.csv` — the final assembled output. Committed.

## Quickstart

```bash
uvx marimo run notebook.py
```

## Published read-only app

A read-only snapshot of the Dashboard and Dataset Preview is published to GitHub Pages on
every push to `master`, via `.github/workflows/deploy-pages.yml`. It's a separate,
WASM-exportable notebook (`apps/dashboard.py`) that only reads the data already committed
to `data/processed/`, `data/curated/`, and `data/nl_research_orgs.parquet` — no
refresh/save buttons, no external API calls, no LLM configuration. To preview it locally:

```bash
bash apps/build_public.sh   # copies data/{processed,curated,nl_research_orgs.*} + assets/ into apps/public/
uvx marimo run apps/dashboard.py
```

For the interactive curation tool (refreshing sources, editing membership lists), use
`notebook.py` as described above — that one has to run locally since it writes to disk
and calls external APIs that a static GitHub Pages site can't support.

## Headless / CLI

```bash
uvx marimo run pipeline.py -- --source all
uvx marimo run pipeline.py -- --source ror --force-refresh true
```

## API keys

Copy `.env.example` to `.env` and fill in your keys:

```bash
cp .env.example .env
```

See `.env.example` for all available options including LLM provider configuration.
All keys are optional — every stage runs and reports zero new records without its
key rather than failing.

| Variable(s) | Stage | How to obtain |
|---|---|---|
| `OPENALEX_API_KEY`, `OPENALEX_MAILTO` | OpenAlex | No signup — a `mailto` is enough to join OpenAlex's ["polite pool"](https://docs.openalex.org/how-to-use-the-api/rate-limits-and-authentication) for higher rate limits. An API key is only needed for premium/higher-volume access. |
| `OPENAIRE_CLIENT_ID`, `OPENAIRE_CLIENT_SECRET` | OpenAIRE | Optional — the Graph API is public without auth, at a lower rate limit. Register an application at the [OpenAIRE APIs & SDKs portal](https://graph.openaire.eu/docs/apis-sdks/graph-api/get-started/authentication) for a `client_credentials` pair. |
| `EU_LOGIN_CLIENT_ID`, `EU_LOGIN_CLIENT_SECRET` | EU PIC | Requires an [EU Login](https://webgate.ec.europa.eu/cas/eim/external/register.cgi) account with **Participant Register API** access, granted through your organisation's LEAR (Legal Entity Appointed Representative) or your project coordinator — see the [Funding & Tenders Participant Register](https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/how-to-participate/participant-register) and the [API webservices docs](https://webgate.ec.europa.eu/funding-tenders-opportunities/display/OM/Webservices). This module is unverified against the live API — see `src/pic_fetcher.py`'s docstring. |
| `OVERHEID_IO_API_KEY` | ALEI / KVK | Free account at [overheid.io/register](https://overheid.io/register); generate a key from your dashboard. Docs: [overheid.io/documentatie/openkvk](https://overheid.io/documentatie/openkvk). This module is unverified against the live API — see `src/alei_fetcher.py`'s docstring. |

## Updating membership lists

Open the notebook (`uvx marimo run notebook.py`) and scroll to **Curate Data → Membership Curation**. Each membership source shows an editable table and an "LLM Auto-update" button. Configure your LLM provider first in **Curate Data → LLM Configuration**, just above it.

## Column reference

| Column | Source | Type |
|--------|--------|------|
| `name` | ROR | string |
| `acronym` | ROR | string |
| `aliases` | ROR | string (pipe-separated) |
| `ror_id` | ROR | string |
| `ror_id_url` | ROR | string |
| `org_type` | ROR | string |
| `status` | ROR | string |
| `established_year` | ROR | int |
| `country_code` | ROR | string |
| `location_name` | ROR | string |
| `lat` | ROR | float |
| `lng` | ROR | float |
| `geonames_id` | ROR | int |
| `website_url` | ROR | string |
| `wikipedia_url` | ROR | string |
| `isni_id` | ROR, falls back to OpenAIRE | string |
| `wikidata_id` | ROR, falls back to OpenAIRE | string |
| `grid_id` | ROR, falls back to OpenAIRE | string |
| `fundref_id` | ROR, falls back to OpenAIRE | string |
| `viaf_id` | OpenAIRE | string |
| `ringgold_id` | OpenAIRE | string |
| `orgref_id` | OpenAIRE | string |
| `orgreg_id` | OpenAIRE | string |
| `rrid_id` | OpenAIRE | string |
| `linkedin_url` | OpenAIRE | string |
| `mag_id` | OpenAIRE (Microsoft Academic Graph) | string |
| `ori_base_org` | Zenodo | bool |
| `openalex_institution_id` | OpenAlex | string |
| `openalex_institution_id_url` | OpenAlex | string |
| `openaire_org_id` | OpenAIRE | string |
| `openaire_org_id_url` | OpenAIRE org-search URL, falls back to a ROR-filtered OpenAIRE Explore search when there's no `openaire_org_id` | string |
| `alei_id` | ALEI/KVK | string (empty) |
| `pic_id` | EU PIC, falls back to OpenAIRE | string (empty) |
| `is_barcelona_signatory` | Barcelona Decl. | bool |
| `is_duo_institute` | DUO HO/MBO address lists (exact name/alias match; HO and MBO combined) | bool |
| `duo_institution_code` | DUO HO/MBO address lists | string |
| `duo_institute_type` | DUO HO/MBO address lists (HO's "SOORT HO" or MBO's "MBO INSTELLINGSSOORT - CODE" — different vocabularies, so the value itself tells you which) | string |
| `duo_straatnaam` | DUO HO/MBO address lists | string |
| `duo_huisnummer` | DUO HO/MBO address lists (combined house number + addition, e.g. "12a") | string |
| `duo_postcode` | DUO HO/MBO address lists | string |
| `duo_plaatsnaam` | DUO HO/MBO address lists | string |
| `is_surf_member` | curated | bool |
| `surf_member_type` | curated | string |
| `is_ukb` | curated | bool |
| `is_shb` | curated | bool |
| `is_unl` | curated | bool |
| `is_umcnl` | curated | bool |
| `is_vh` | curated | bool |
| `is_knaw_institute` | curated | bool |
| `is_nwoi_institute` | curated | bool |
| `is_openaire_member` | curated | bool |

## Contributing

Pull requests welcome. To add a new data source, implement the module contract in `src/`:

```python
def fetch(force_refresh: bool = False) -> dict:
    return {"record_count": int, "fetched_at": str, "source_url": str}
```

Data-fetching stages return `source_url`. The assembler (`src/assembler.py`) is the exception: it returns `output_path` (the path to the written parquet file) instead of `source_url`.

See `agents.md` for the full module contract.

## License

[European Union Public Licence (EUPL) v1.2](https://eupl.eu/1.2/en/) — see `LICENSE`.
