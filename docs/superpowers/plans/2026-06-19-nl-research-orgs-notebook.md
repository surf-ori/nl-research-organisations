# NL Research Organisations Notebook — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a marimo notebook app that fetches, enriches, and maintains a 35-column reference table of all research organisations in the Kingdom of the Netherlands, writing `data/nl_research_orgs.parquet` and `.csv` as the primary outputs.

**Architecture:** Each `src/*.py` pipeline stage is a marimo notebook with a module-level `fetch()` function (importable and testable without marimo), plus marimo cells that call it for interactive display. The main `notebook.py` orchestrates all stages in a 5-tab app. `pipeline.py` is a thin marimo headless wrapper for CLI/cron use.

**Tech Stack:** Python ≥ 3.11, marimo, duckdb, requests, python-dotenv, openai (SDK), openpyxl, pytest, uv/uvx

## Global Constraints

- Python ≥ 3.11 (uses `str | None` union syntax, `match` statements)
- All `.py` files carry `# /// script` inline uv metadata declaring their own dependencies
- `fetch(force_refresh: bool = False) -> dict` is the module contract for every stage — returns `{"record_count": int, "fetched_at": str, "output_path": str}`
- `data/raw/` is gitignored; `data/curated/` and `data/nl_research_orgs.{parquet,csv}` are committed
- LLM calls use `openai.OpenAI(base_url=..., api_key=...)` — no provider-specific SDK
- ROR country codes to cover: `NL, AW, CW, SX, BQ`
- All 35 output columns exactly as named in the spec; `alei_id` and `pic_id` are empty strings

---

### Task 1: Project scaffold

**Files:**
- Create: `.gitignore`
- Create: `.env.example`
- Create: `data/curated/.gitkeep`
- Create: `data/raw/.gitkeep`
- Create: `src/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

**Interfaces:**
- Produces: project skeleton all subsequent tasks build on

- [ ] **Step 1: Create `.gitignore`**

```
.env
data/raw/
__pycache__/
*.pyc
.pytest_cache/
*.egg-info/
dist/
```

- [ ] **Step 2: Create `.env.example`**

```dotenv
# OpenAlex
OPENALEX_API_KEY=your_key_here
OPENALEX_MAILTO=your@email.com

# OpenAIRE
OPENAIRE_REFRESH_TOKEN=your_token_here

# LLM curator — any OpenAI-compatible endpoint
# SURF WillMa:  https://willma.surf.nl/api/v0   model: openai/gpt-oss-120b
# Anthropic:    https://api.anthropic.com/v1     model: claude-sonnet-4-6
# Ollama:       http://localhost:11434/v1         model: llama3
# OpenRouter:   https://openrouter.ai/api/v1     model: openai/gpt-4o
LLM_BASE_URL=https://willma.surf.nl/api/v0
LLM_API_KEY=your_key_here
LLM_MODEL=openai/gpt-oss-120b

# ALEI / KVK (placeholder — not yet implemented)
KVK_API_KEY=

# EU Participant Portal PIC (placeholder — not yet implemented)
EU_PIC_API_KEY=
```

- [ ] **Step 3: Create directory placeholders and init files**

```bash
mkdir -p data/raw data/curated src tests
touch data/raw/.gitkeep data/curated/.gitkeep src/__init__.py tests/__init__.py
```

- [ ] **Step 4: Create `tests/conftest.py`**

```python
# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest"]
# ///
import json
from pathlib import Path
import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def ror_page_nl():
    return json.loads((FIXTURES / "ror_page_NL.json").read_text())


@pytest.fixture
def tmp_raw(tmp_path):
    (tmp_path / "ror").mkdir(parents=True)
    (tmp_path / "zenodo").mkdir(parents=True)
    (tmp_path / "openalex").mkdir(parents=True)
    (tmp_path / "openaire").mkdir(parents=True)
    (tmp_path / "barcelona").mkdir(parents=True)
    return tmp_path
```

- [ ] **Step 5: Create `tests/fixtures/` with a minimal ROR page fixture**

```bash
mkdir -p tests/fixtures
```

Write `tests/fixtures/ror_page_NL.json`:

```json
{
  "items": [
    {
      "id": "https://ror.org/04dkp9463",
      "names": [
        {"value": "Vrije Universiteit Amsterdam", "types": ["ror_display", "label"], "lang": "en"},
        {"value": "VU Amsterdam", "types": ["alias"], "lang": null},
        {"value": "VU", "types": ["acronym"], "lang": null}
      ],
      "types": ["education"],
      "status": "active",
      "established": 1880,
      "locations": [
        {
          "geonames_id": 2759794,
          "geonames_details": {
            "id": 2759794,
            "name": "Amsterdam",
            "lat": 52.37403,
            "lng": 4.88969,
            "country_code": "NL",
            "country_name": "Netherlands"
          }
        }
      ],
      "links": [
        {"type": "website", "value": "https://vu.nl"},
        {"type": "wikipedia", "value": "https://en.wikipedia.org/wiki/Vrije_Universiteit_Amsterdam"}
      ],
      "external_ids": [
        {"type": "isni", "all": ["0000 0001 2248 2840"], "preferred": "0000 0001 2248 2840"},
        {"type": "wikidata", "all": ["Q1065919"], "preferred": "Q1065919"},
        {"type": "grid", "all": ["grid.12380.38"], "preferred": "grid.12380.38"},
        {"type": "fundref", "all": ["501100001833"], "preferred": "501100001833"}
      ],
      "country": {"country_code": "NL", "country_name": "Netherlands"}
    }
  ],
  "meta": {"total": 1, "page": 1, "per_page": 20}
}
```

- [ ] **Step 6: Commit**

```bash
git add .gitignore .env.example data/curated/.gitkeep data/raw/.gitkeep src/__init__.py tests/__init__.py tests/conftest.py tests/fixtures/ror_page_NL.json
git commit -m "feat: project scaffold, gitignore, env template, test fixtures"
```

---

### Task 2: `src/ror_fetcher.py`

**Files:**
- Create: `src/ror_fetcher.py`
- Create: `tests/test_ror_fetcher.py`

**Interfaces:**
- Produces: `fetch(force_refresh=False) -> {"record_count": int, "fetched_at": str, "output_path": str}`
- Produces: `load_orgs() -> list[dict]` — returns normalised flat dicts with all 20 base columns
- Raw files: `data/raw/ror/page_<CC>_<NNN>.json` + `data/raw/ror/_metadata.json`

- [ ] **Step 1: Write failing tests**

`tests/test_ror_fetcher.py`:

```python
import json
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest


def test_extract_org_fields(tmp_raw, ror_page_nl):
    with patch("src.ror_fetcher.DATA_DIR", tmp_raw / "ror"):
        (tmp_raw / "ror").mkdir(exist_ok=True)
        (tmp_raw / "ror" / "page_NL_001.json").write_text(json.dumps(ror_page_nl))
        from src.ror_fetcher import load_orgs
        orgs = load_orgs()
    assert len(orgs) == 1
    org = orgs[0]
    assert org["ror_id"] == "04dkp9463"
    assert org["ror_id_url"] == "https://ror.org/04dkp9463"
    assert org["name"] == "Vrije Universiteit Amsterdam"
    assert org["acronym"] == "VU"
    assert "VU Amsterdam" in org["aliases"]
    assert org["org_type"] == "education"
    assert org["status"] == "active"
    assert org["established_year"] == 1880
    assert org["country_code"] == "NL"
    assert org["location_name"] == "Amsterdam"
    assert org["lat"] == 52.37403
    assert org["lng"] == 4.88969
    assert org["geonames_id"] == 2759794
    assert org["website_url"] == "https://vu.nl"
    assert org["wikipedia_url"] is not None
    assert org["isni_id"] == "0000 0001 2248 2840"
    assert org["wikidata_id"] == "Q1065919"
    assert org["grid_id"] == "grid.12380.38"
    assert org["fundref_id"] == "501100001833"


def test_fetch_skips_when_cached(tmp_raw):
    ror_dir = tmp_raw / "ror"
    ror_dir.mkdir()
    (ror_dir / "page_NL_001.json").write_text('{"items":[],"meta":{"total":0}}')
    (ror_dir / "_metadata.json").write_text('{"fetched_at":"2026-01-01T00:00:00","record_count":0,"source_url":"https://api.ror.org/v2/organizations"}')
    with patch("src.ror_fetcher.DATA_DIR", ror_dir):
        with patch("src.ror_fetcher.requests.get") as mock_get:
            from src.ror_fetcher import fetch
            fetch(force_refresh=False)
            mock_get.assert_not_called()
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd /c/Users/mvn439/Code/nl-research-organisations && python -m pytest tests/test_ror_fetcher.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError` or similar — `src.ror_fetcher` does not exist yet.

- [ ] **Step 3: Implement `src/ror_fetcher.py`**

```python
# /// script
# requires-python = ">=3.11"
# dependencies = ["marimo", "requests", "python-dotenv"]
# ///
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import marimo as mo
import requests

__generated_with = "0.13.0"
app = mo.App(width="wide")

DATA_DIR = Path("data/raw/ror")
COUNTRY_CODES = ["NL", "AW", "CW", "SX", "BQ"]
BASE_URL = "https://api.ror.org/v2/organizations"


def _extract_org(item: dict) -> dict:
    names = item.get("names", [])
    name = next((n["value"] for n in names if "ror_display" in n.get("types", [])), "")
    acronym = next((n["value"] for n in names if "acronym" in n.get("types", [])), None)
    aliases = "|".join(n["value"] for n in names if "alias" in n.get("types", []))
    locations = item.get("locations", [])
    geo = locations[0].get("geonames_details", {}) if locations else {}
    geonames_id = locations[0].get("geonames_id") if locations else None
    links = item.get("links", [])
    website = next((l["value"] for l in links if l.get("type") == "website"), None)
    wikipedia = next((l["value"] for l in links if l.get("type") == "wikipedia"), None)
    ext = {e["type"]: e.get("preferred") for e in item.get("external_ids", [])}
    types = item.get("types", [])
    return {
        "ror_id_url": item["id"],
        "ror_id": item["id"].replace("https://ror.org/", ""),
        "name": name,
        "acronym": acronym,
        "aliases": aliases or None,
        "org_type": "|".join(types) if types else None,
        "status": item.get("status"),
        "established_year": item.get("established"),
        "country_code": item.get("country", {}).get("country_code"),
        "location_name": geo.get("name"),
        "lat": geo.get("lat"),
        "lng": geo.get("lng"),
        "geonames_id": geonames_id,
        "website_url": website,
        "wikipedia_url": wikipedia,
        "isni_id": ext.get("isni"),
        "wikidata_id": ext.get("wikidata"),
        "grid_id": ext.get("grid"),
        "fundref_id": ext.get("fundref"),
    }


def _fetch_country(cc: str, data_dir: Path) -> int:
    page = 1
    total_fetched = 0
    while True:
        resp = requests.get(
            BASE_URL,
            params={"query": "*", "filter": f"country.country_code:{cc}", "page": page},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        items = data.get("items", [])
        if not items:
            break
        out = data_dir / f"page_{cc}_{page:03d}.json"
        out.write_text(json.dumps(data))
        total_fetched += len(items)
        meta = data.get("meta", {})
        if page * meta.get("per_page", 20) >= meta.get("total", 0):
            break
        page += 1
        time.sleep(0.1)
    return total_fetched


def load_orgs() -> list[dict]:
    seen = set()
    orgs = []
    for path in sorted(DATA_DIR.glob("page_*.json")):
        data = json.loads(path.read_text())
        for item in data.get("items", []):
            ror_id = item.get("id", "")
            if ror_id in seen:
                continue
            seen.add(ror_id)
            orgs.append(_extract_org(item))
    return orgs


def fetch(force_refresh: bool = False) -> dict:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    meta_path = DATA_DIR / "_metadata.json"
    existing = list(DATA_DIR.glob("page_*.json"))
    if existing and not force_refresh and meta_path.exists():
        meta = json.loads(meta_path.read_text())
        return meta
    for f in DATA_DIR.glob("page_*.json"):
        f.unlink()
    total = 0
    for cc in COUNTRY_CODES:
        total += _fetch_country(cc, DATA_DIR)
    meta = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "record_count": total,
        "source_url": BASE_URL,
    }
    meta_path.write_text(json.dumps(meta))
    return meta


@app.cell
def _():
    import marimo as mo
    return (mo,)


@app.cell
def _(mo):
    result = fetch()
    orgs = load_orgs()
    import pandas as pd
    df = pd.DataFrame(orgs)
    mo.vstack([
        mo.md(f"## ROR Fetch\nFetched **{result['record_count']}** records · last updated {result['fetched_at']}"),
        mo.ui.table(df),
    ])
    return


if __name__ == "__main__":
    app.run()
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_ror_fetcher.py -v
```

Expected: both tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ror_fetcher.py tests/test_ror_fetcher.py
git commit -m "feat: ROR fetcher — paginate all 6 NL kingdom country codes, cache JSON, extract 20 columns"
```

---

### Task 3: `src/zenodo_baseline.py`

**Files:**
- Create: `src/zenodo_baseline.py`
- Create: `tests/test_zenodo_baseline.py`

**Interfaces:**
- Consumes: nothing (downloads directly)
- Produces: `fetch(force_refresh=False) -> dict`
- Produces: `load_ror_ids() -> set[str]` — set of ROR id URLs present in the baseline

- [ ] **Step 1: Write failing tests**

`tests/test_zenodo_baseline.py`:

```python
import io
from pathlib import Path
from unittest.mock import patch, MagicMock
import openpyxl
import pytest


def _make_xlsx(ror_urls: list[str]) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["name", "ROR"])
    for url in ror_urls:
        ws.append(["Test Org", url])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_load_ror_ids(tmp_path):
    xlsx_bytes = _make_xlsx(["https://ror.org/04dkp9463", "https://ror.org/abc123"])
    zenodo_dir = tmp_path / "zenodo"
    zenodo_dir.mkdir()
    (zenodo_dir / "nl-orgs-baseline.xlsx").write_bytes(xlsx_bytes)
    with patch("src.zenodo_baseline.DATA_DIR", zenodo_dir):
        from src.zenodo_baseline import load_ror_ids
        ids = load_ror_ids()
    assert "https://ror.org/04dkp9463" in ids
    assert "https://ror.org/abc123" in ids
    assert len(ids) == 2


def test_fetch_skips_when_cached(tmp_path):
    zenodo_dir = tmp_path / "zenodo"
    zenodo_dir.mkdir()
    xlsx_bytes = _make_xlsx(["https://ror.org/04dkp9463"])
    (zenodo_dir / "nl-orgs-baseline.xlsx").write_bytes(xlsx_bytes)
    import json
    (zenodo_dir / "_metadata.json").write_text(json.dumps({"fetched_at": "2026-01-01", "record_count": 1, "source_url": "x"}))
    with patch("src.zenodo_baseline.DATA_DIR", zenodo_dir):
        with patch("src.zenodo_baseline.requests.get") as mock_get:
            from src.zenodo_baseline import fetch
            fetch(force_refresh=False)
            mock_get.assert_not_called()
```

- [ ] **Step 2: Run to confirm failure**

```bash
python -m pytest tests/test_zenodo_baseline.py -v 2>&1 | head -10
```

- [ ] **Step 3: Implement `src/zenodo_baseline.py`**

```python
# /// script
# requires-python = ">=3.11"
# dependencies = ["marimo", "requests", "openpyxl", "python-dotenv"]
# ///
import json
from datetime import datetime, timezone
from pathlib import Path

import marimo as mo
import openpyxl
import requests

__generated_with = "0.13.0"
app = mo.App(width="wide")

DATA_DIR = Path("data/raw/zenodo")
ZENODO_URL = "https://zenodo.org/records/18957154/files/nl-orgs-baseline.xlsx?download=1"
XLSX_PATH = DATA_DIR / "nl-orgs-baseline.xlsx"


def load_ror_ids() -> set[str]:
    wb = openpyxl.load_workbook(XLSX_PATH, read_only=True)
    ws = wb.active
    headers = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]
    ror_col = next((i for i, h in enumerate(headers) if h and str(h).strip().upper() == "ROR"), None)
    if ror_col is None:
        return set()
    ids = set()
    for row in ws.iter_rows(min_row=2, values_only=True):
        val = row[ror_col]
        if val:
            val = str(val).strip()
            if not val.startswith("https://"):
                val = f"https://ror.org/{val}"
            ids.add(val)
    return ids


def fetch(force_refresh: bool = False) -> dict:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    meta_path = DATA_DIR / "_metadata.json"
    if XLSX_PATH.exists() and not force_refresh and meta_path.exists():
        return json.loads(meta_path.read_text())
    resp = requests.get(ZENODO_URL, timeout=60)
    resp.raise_for_status()
    XLSX_PATH.write_bytes(resp.content)
    ids = load_ror_ids()
    meta = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "record_count": len(ids),
        "source_url": ZENODO_URL,
    }
    meta_path.write_text(json.dumps(meta))
    return meta


@app.cell
def _():
    import marimo as mo
    return (mo,)


@app.cell
def _(mo):
    result = fetch()
    mo.md(f"## Zenodo Baseline\n**{result['record_count']}** ROR ids in baseline · {result['fetched_at']}")
    return


if __name__ == "__main__":
    app.run()
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_zenodo_baseline.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/zenodo_baseline.py tests/test_zenodo_baseline.py
git commit -m "feat: Zenodo baseline downloader — extracts ROR id set for ori_base_org column"
```

---

### Task 4: `src/openalex.py`

**Files:**
- Create: `src/openalex.py`
- Create: `tests/test_openalex.py`

**Interfaces:**
- Consumes: list of ROR id URLs
- Produces: `fetch(ror_urls, force_refresh=False) -> dict`
- Produces: `load_results() -> dict[str, str | None]` — maps ror_id_url → openalex_institution_id
- Raw files: `data/raw/openalex/<ror_short_id>.json` + `data/raw/openalex/_metadata.json`

- [ ] **Step 1: Write failing tests**

`tests/test_openalex.py`:

```python
import json
from unittest.mock import patch, MagicMock


def test_load_results(tmp_path):
    oa_dir = tmp_path / "openalex"
    oa_dir.mkdir()
    payload = {"results": [{"id": "https://openalex.org/I123456789"}]}
    (oa_dir / "04dkp9463.json").write_text(json.dumps(payload))
    with patch("src.openalex.DATA_DIR", oa_dir):
        from src.openalex import load_results
        results = load_results()
    assert results["https://ror.org/04dkp9463"] == "https://openalex.org/I123456789"


def test_fetch_skips_cached(tmp_path):
    oa_dir = tmp_path / "openalex"
    oa_dir.mkdir()
    (oa_dir / "04dkp9463.json").write_text('{"results":[{"id":"https://openalex.org/I1"}]}')
    with patch("src.openalex.DATA_DIR", oa_dir):
        with patch("src.openalex.requests.get") as mock_get:
            from src.openalex import fetch
            fetch(["https://ror.org/04dkp9463"])
            mock_get.assert_not_called()


def test_fetch_calls_api_for_uncached(tmp_path):
    oa_dir = tmp_path / "openalex"
    oa_dir.mkdir()
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"results": [{"id": "https://openalex.org/I999"}]}
    mock_resp.status_code = 200
    with patch("src.openalex.DATA_DIR", oa_dir):
        with patch("src.openalex.requests.get", return_value=mock_resp) as mock_get:
            from src.openalex import fetch
            fetch(["https://ror.org/newid123"])
            mock_get.assert_called_once()
```

- [ ] **Step 2: Confirm failure**

```bash
python -m pytest tests/test_openalex.py -v 2>&1 | head -10
```

- [ ] **Step 3: Implement `src/openalex.py`**

```python
# /// script
# requires-python = ">=3.11"
# dependencies = ["marimo", "requests", "python-dotenv"]
# ///
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import marimo as mo
import requests
from dotenv import load_dotenv

load_dotenv()

__generated_with = "0.13.0"
app = mo.App(width="wide")

DATA_DIR = Path("data/raw/openalex")
API_URL = "https://api.openalex.org/institutions"
API_KEY = os.getenv("OPENALEX_API_KEY", "")
MAILTO = os.getenv("OPENALEX_MAILTO", "")


def _cache_path(ror_url: str) -> Path:
    short_id = ror_url.replace("https://ror.org/", "")
    return DATA_DIR / f"{short_id}.json"


def load_results() -> dict[str, str | None]:
    out = {}
    for path in DATA_DIR.glob("*.json"):
        if path.name == "_metadata.json":
            continue
        short_id = path.stem
        ror_url = f"https://ror.org/{short_id}"
        data = json.loads(path.read_text())
        results = data.get("results", [])
        out[ror_url] = results[0].get("id") if results else None
    return out


def fetch(ror_urls: list[str], force_refresh: bool = False) -> dict:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    fetched = 0
    for ror_url in ror_urls:
        cache = _cache_path(ror_url)
        if cache.exists() and not force_refresh:
            continue
        headers = {}
        if API_KEY:
            headers["Authorization"] = f"Bearer {API_KEY}"
        params = {"filter": f"ror:{ror_url}", "mailto": MAILTO}
        resp = requests.get(API_URL, params=params, headers=headers, timeout=15)
        resp.raise_for_status()
        cache.write_text(resp.text)
        fetched += 1
        time.sleep(0.15)
    results = load_results()
    filled = sum(1 for v in results.values() if v)
    meta = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "record_count": filled,
        "source_url": API_URL,
    }
    (DATA_DIR / "_metadata.json").write_text(json.dumps(meta))
    return meta


@app.cell
def _():
    import marimo as mo
    return (mo,)


@app.cell
def _(mo):
    results = load_results()
    filled = sum(1 for v in results.values() if v)
    mo.md(f"## OpenAlex\n**{filled}** institutions matched out of {len(results)} looked up")
    return


if __name__ == "__main__":
    app.run()
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_openalex.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/openalex.py tests/test_openalex.py
git commit -m "feat: OpenAlex fetcher — per-ROR lookup with file-level caching"
```

---

### Task 5: `src/openaire.py`

**Files:**
- Create: `src/openaire.py`
- Create: `tests/test_openaire.py`

**Interfaces:**
- Consumes: list of ROR id URLs
- Produces: `fetch(ror_urls, force_refresh=False) -> dict`
- Produces: `load_results() -> dict[str, str | None]` — maps ror_id_url → openaire_org_id
- Raw files: `data/raw/openaire/<ror_short_id>.json`

- [ ] **Step 1: Write failing tests**

`tests/test_openaire.py`:

```python
import json
from unittest.mock import patch, MagicMock


def test_load_results(tmp_path):
    oa_dir = tmp_path / "openaire"
    oa_dir.mkdir()
    payload = {"content": [{"id": "openaire::abc123"}]}
    (oa_dir / "04dkp9463.json").write_text(json.dumps(payload))
    with patch("src.openaire.DATA_DIR", oa_dir):
        from src.openaire import load_results
        results = load_results()
    assert results["https://ror.org/04dkp9463"] == "openaire::abc123"


def test_get_token():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"access_token": "tok123"}
    with patch("src.openaire.requests.post", return_value=mock_resp):
        from src.openaire import _get_token
        assert _get_token("myrefresh") == "tok123"
```

- [ ] **Step 2: Confirm failure**

```bash
python -m pytest tests/test_openaire.py -v 2>&1 | head -10
```

- [ ] **Step 3: Implement `src/openaire.py`**

```python
# /// script
# requires-python = ">=3.11"
# dependencies = ["marimo", "requests", "python-dotenv"]
# ///
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import marimo as mo
import requests
from dotenv import load_dotenv

load_dotenv()

__generated_with = "0.13.0"
app = mo.App(width="wide")

DATA_DIR = Path("data/raw/openaire")
TOKEN_URL = "https://aai.openaire.eu/oidc/token"
API_URL = "https://api.openaire.eu/graph/v1/organizations"
REFRESH_TOKEN = os.getenv("OPENAIRE_REFRESH_TOKEN", "")


def _get_token(refresh_token: str) -> str:
    resp = requests.post(
        TOKEN_URL,
        data={"grant_type": "refresh_token", "refresh_token": refresh_token, "scope": "openid"},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def _cache_path(ror_url: str) -> Path:
    short_id = ror_url.replace("https://ror.org/", "")
    return DATA_DIR / f"{short_id}.json"


def load_results() -> dict[str, str | None]:
    out = {}
    for path in DATA_DIR.glob("*.json"):
        if path.name == "_metadata.json":
            continue
        short_id = path.stem
        ror_url = f"https://ror.org/{short_id}"
        data = json.loads(path.read_text())
        results = data if isinstance(data, list) else data.get("results", data.get("content", []))
        out[ror_url] = (results[0].get("id") or results[0].get("originalId")) if results else None
    return out


def fetch(ror_urls: list[str], force_refresh: bool = False) -> dict:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    uncached = [u for u in ror_urls if not _cache_path(u).exists() or force_refresh]
    if uncached and not REFRESH_TOKEN:
        print("OPENAIRE_REFRESH_TOKEN not set — skipping OpenAIRE lookups")
    elif uncached:
        token = _get_token(REFRESH_TOKEN)
        for ror_url in uncached:
            resp = requests.get(
                API_URL,
                params={"pid": ror_url},
                headers={"Authorization": f"Bearer {token}"},
                timeout=15,
            )
            resp.raise_for_status()
            _cache_path(ror_url).write_text(resp.text)
            time.sleep(0.15)
    results = load_results()
    filled = sum(1 for v in results.values() if v)
    meta = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "record_count": filled,
        "source_url": API_URL,
    }
    (DATA_DIR / "_metadata.json").write_text(json.dumps(meta))
    return meta


@app.cell
def _():
    import marimo as mo
    return (mo,)


@app.cell
def _(mo):
    results = load_results()
    filled = sum(1 for v in results.values() if v)
    mo.md(f"## OpenAIRE\n**{filled}** organisations matched out of {len(results)} looked up")
    return


if __name__ == "__main__":
    app.run()
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_openaire.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/openaire.py tests/test_openaire.py
git commit -m "feat: OpenAIRE fetcher — token refresh + per-ROR lookup with caching"
```

---

### Task 6: Placeholder fetchers (`src/alei_fetcher.py` + `src/pic_fetcher.py`)

**Files:**
- Create: `src/alei_fetcher.py`
- Create: `src/pic_fetcher.py`

**Interfaces:**
- Produces: `fetch(force_refresh=False) -> dict` — returns `{"record_count": 0, ...}` immediately
- Produces: `load_results() -> dict[str, str | None]` — returns `{}`
- No tests needed (no logic to test)

- [ ] **Step 1: Create `src/alei_fetcher.py`**

```python
# /// script
# requires-python = ">=3.11"
# dependencies = ["marimo", "python-dotenv"]
# ///
"""
ALEI / KVK / ISO 8000-116 IBRN Fetcher — PLACEHOLDER

Target API: KVK Open Data API or ekys.org EKYS Search
  KVK API docs:  https://developers.kvk.nl/documentation
  EKYS search:   https://ekys.org/ekys_search/search/
  Wikipedia:     https://en.wikipedia.org/wiki/Authoritative_Legal_Entity_Identifier

When API access is available:
  1. Set KVK_API_KEY in .env
  2. Implement _fetch_one(ror_url, name) -> str | None using the KVK API
  3. Loop over ror_urls in fetch(), cache results to data/raw/alei/<ror_id>.json
  4. Remove the NOT_IMPLEMENTED banner from the marimo cell below

Required .env key: KVK_API_KEY
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import marimo as mo

__generated_with = "0.13.0"
app = mo.App(width="wide")

DATA_DIR = Path("data/raw/alei")
NOT_IMPLEMENTED = True


def load_results() -> dict[str, str | None]:
    return {}


def fetch(force_refresh: bool = False) -> dict:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    meta = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "record_count": 0,
        "source_url": "https://developers.kvk.nl/documentation",
    }
    (DATA_DIR / "_metadata.json").write_text(json.dumps(meta))
    return meta


@app.cell
def _():
    import marimo as mo
    return (mo,)


@app.cell
def _(mo):
    mo.callout(
        mo.md("**ALEI / KVK ID fetcher — not yet implemented.** Awaiting API access. See `src/alei_fetcher.py` for implementation notes."),
        kind="warn",
    )
    return


if __name__ == "__main__":
    app.run()
```

- [ ] **Step 2: Create `src/pic_fetcher.py`**

```python
# /// script
# requires-python = ">=3.11"
# dependencies = ["marimo", "python-dotenv"]
# ///
"""
EU PIC ID Fetcher — PLACEHOLDER

Target API: EU Funding & Tenders Participant Portal
  Portal:    https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/how-to-participate/participant-register
  API docs:  https://webgate.ec.europa.eu/funding-tenders-opportunities/display/OM/Webservices
  Guide:     https://eufunds.me/how-to-find-the-pic-number-of-an-organization/

When API access is available:
  1. Set EU_PIC_API_KEY in .env
  2. Implement _fetch_one(ror_url, name) -> str | None
  3. Cache results to data/raw/pic/<ror_id>.json
  4. Remove the NOT_IMPLEMENTED banner below

Required .env key: EU_PIC_API_KEY
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import marimo as mo

__generated_with = "0.13.0"
app = mo.App(width="wide")

DATA_DIR = Path("data/raw/pic")
NOT_IMPLEMENTED = True


def load_results() -> dict[str, str | None]:
    return {}


def fetch(force_refresh: bool = False) -> dict:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    meta = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "record_count": 0,
        "source_url": "https://ec.europa.eu/info/funding-tenders/opportunities/portal/",
    }
    (DATA_DIR / "_metadata.json").write_text(json.dumps(meta))
    return meta


@app.cell
def _():
    import marimo as mo
    return (mo,)


@app.cell
def _(mo):
    mo.callout(
        mo.md("**PIC ID fetcher — not yet implemented.** Awaiting API access. See `src/pic_fetcher.py` for implementation notes."),
        kind="warn",
    )
    return


if __name__ == "__main__":
    app.run()
```

- [ ] **Step 3: Commit**

```bash
git add src/alei_fetcher.py src/pic_fetcher.py
git commit -m "feat: placeholder fetchers for ALEI/KVK and EU PIC IDs with implementation notes"
```

---

### Task 7: `src/barcelona.py`

**Files:**
- Create: `src/barcelona.py`
- Create: `tests/test_barcelona.py`

**Interfaces:**
- Produces: `fetch(force_refresh=False) -> dict`
- Produces: `load_results(ror_orgs: list[dict]) -> dict[str, bool]` — maps ror_id_url → is_barcelona_signatory
- Raw file: `data/raw/barcelona/signatories.csv`

- [ ] **Step 1: Write failing tests**

`tests/test_barcelona.py`:

```python
import csv
import io
from pathlib import Path
from unittest.mock import patch, MagicMock


SAMPLE_CSV = """ror_id,organisation_name,country
https://ror.org/04dkp9463,Vrije Universiteit Amsterdam,Netherlands
,Some Other Org Without ROR,Netherlands
"""


def test_load_results_by_ror(tmp_path):
    bdir = tmp_path / "barcelona"
    bdir.mkdir()
    (bdir / "signatories.csv").write_text(SAMPLE_CSV)
    with patch("src.barcelona.DATA_DIR", bdir):
        from src.barcelona import load_results
        orgs = [
            {"ror_id_url": "https://ror.org/04dkp9463", "name": "Vrije Universiteit Amsterdam"},
            {"ror_id_url": "https://ror.org/notinlist", "name": "Unknown Org"},
        ]
        results = load_results(orgs)
    assert results["https://ror.org/04dkp9463"] is True
    assert results["https://ror.org/notinlist"] is False


def test_load_results_fuzzy_fallback(tmp_path):
    bdir = tmp_path / "barcelona"
    bdir.mkdir()
    csv_content = "ror_id,organisation_name,country\n,Delft University of Technology,Netherlands\n"
    (bdir / "signatories.csv").write_text(csv_content)
    with patch("src.barcelona.DATA_DIR", bdir):
        from src.barcelona import load_results
        orgs = [{"ror_id_url": "https://ror.org/02w4jbg70", "name": "Delft University of Technology"}]
        results = load_results(orgs)
    assert results["https://ror.org/02w4jbg70"] is True
```

- [ ] **Step 2: Confirm failure**

```bash
python -m pytest tests/test_barcelona.py -v 2>&1 | head -10
```

- [ ] **Step 3: Implement `src/barcelona.py`**

```python
# /// script
# requires-python = ">=3.11"
# dependencies = ["marimo", "requests", "python-dotenv"]
# ///
import csv
import difflib
import json
from datetime import datetime, timezone
from pathlib import Path

import marimo as mo
import requests

__generated_with = "0.13.0"
app = mo.App(width="wide")

DATA_DIR = Path("data/raw/barcelona")
CSV_URL = "https://barcelona-declaration.org/downloads/barcelonadeclaration_signatories_supporters.csv"
CSV_PATH = DATA_DIR / "signatories.csv"
FUZZY_THRESHOLD = 0.85


def _read_signatories() -> list[dict]:
    rows = []
    with CSV_PATH.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append({k.strip().lower(): v.strip() for k, v in row.items()})
    return rows


def load_results(ror_orgs: list[dict]) -> dict[str, bool]:
    signatories = _read_signatories()
    ror_ids_in_list = {
        row.get("ror_id", "").strip()
        for row in signatories
        if row.get("ror_id", "").strip()
    }
    names_in_list = [row.get("organisation_name", "") for row in signatories]
    results = {}
    for org in ror_orgs:
        ror_url = org["ror_id_url"]
        if ror_url in ror_ids_in_list:
            results[ror_url] = True
            continue
        matches = difflib.get_close_matches(org["name"], names_in_list, n=1, cutoff=FUZZY_THRESHOLD)
        results[ror_url] = bool(matches)
    return results


def fetch(force_refresh: bool = False) -> dict:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    meta_path = DATA_DIR / "_metadata.json"
    if CSV_PATH.exists() and not force_refresh and meta_path.exists():
        return json.loads(meta_path.read_text())
    resp = requests.get(CSV_URL, timeout=30)
    resp.raise_for_status()
    CSV_PATH.write_bytes(resp.content)
    rows = _read_signatories()
    meta = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "record_count": len(rows),
        "source_url": CSV_URL,
    }
    meta_path.write_text(json.dumps(meta))
    return meta


@app.cell
def _():
    import marimo as mo
    return (mo,)


@app.cell
def _(mo):
    result = fetch()
    mo.md(f"## Barcelona Declaration\n**{result['record_count']}** signatories · {result['fetched_at']}")
    return


if __name__ == "__main__":
    app.run()
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_barcelona.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/barcelona.py tests/test_barcelona.py
git commit -m "feat: Barcelona Declaration fetcher — ROR match + fuzzy name fallback"
```

---

### Task 8: Seed curated membership CSVs + `src/memberships.py`

**Files:**
- Create: `data/curated/surf_members.csv`
- Create: `data/curated/ukb_members.csv`
- Create: `data/curated/shb_members.csv`
- Create: `data/curated/unl_members.csv`
- Create: `data/curated/umcnl_members.csv`
- Create: `data/curated/vh_members.csv`
- Create: `data/curated/knaw_institutes.csv`
- Create: `data/curated/nwoi_institutes.csv`
- Create: `data/curated/openaire_members.csv`
- Create: `src/memberships.py`
- Create: `tests/test_memberships.py`

**Interfaces:**
- Produces: `load_memberships(ror_urls: list[str]) -> dict[str, dict]` — maps ror_id_url → membership dict with boolean flags
- Each curated CSV: minimum columns `ror_id_url,name` plus source-specific columns

- [ ] **Step 1: Create curated CSVs with seed data**

`data/curated/surf_members.csv`:
```csv
ror_id_url,name,member_type
https://ror.org/04dkp9463,Vrije Universiteit Amsterdam,instelling
https://ror.org/02jz4aj89,University of Amsterdam,instelling
https://ror.org/04pp8hn57,Delft University of Technology,instelling
https://ror.org/02w4jbg70,Eindhoven University of Technology,instelling
https://ror.org/006hf6230,University of Groningen,instelling
https://ror.org/006e5kg04,Maastricht University,instelling
https://ror.org/016xsfp80,Radboud University,instelling
https://ror.org/027bh9e22,Tilburg University,instelling
https://ror.org/008xxew50,University of Twente,instelling
https://ror.org/04tte2c31,Utrecht University,instelling
https://ror.org/032894m80,Wageningen University and Research,instelling
https://ror.org/05xvt9f17,Erasmus University Rotterdam,instelling
https://ror.org/05v6zhq48,Leiden University,instelling
https://ror.org/001w7jn25,Open University of the Netherlands,instelling
https://ror.org/00f9tz983,Amsterdam UMC,instelling
https://ror.org/03cg3hw49,Erasmus MC,instelling
https://ror.org/04rsptd27,LUMC,instelling
https://ror.org/04dkp9463,VU Medical Center,instelling
https://ror.org/05wg1m734,Radboud University Medical Centre,instelling
https://ror.org/032v44r51,University Medical Centre Groningen,instelling
https://ror.org/0575yy874,Maastricht UMC+,instelling
https://ror.org/00gvr9634,University Medical Centre Utrecht,instelling
https://ror.org/01460j859,KNAW,instelling
https://ror.org/04jsz6e67,NWO,instelling
https://ror.org/027t9k082,Netherlands eScience Center,instelling
https://ror.org/001ps1o28,SURF,instelling
```

`data/curated/ukb_members.csv`:
```csv
ror_id_url,name
https://ror.org/04dkp9463,Vrije Universiteit Amsterdam
https://ror.org/02jz4aj89,University of Amsterdam
https://ror.org/04pp8hn57,Delft University of Technology
https://ror.org/02w4jbg70,Eindhoven University of Technology
https://ror.org/006hf6230,University of Groningen
https://ror.org/006e5kg04,Maastricht University
https://ror.org/016xsfp80,Radboud University
https://ror.org/027bh9e22,Tilburg University
https://ror.org/008xxew50,University of Twente
https://ror.org/04tte2c31,Utrecht University
https://ror.org/032894m80,Wageningen University and Research
https://ror.org/05xvt9f17,Erasmus University Rotterdam
https://ror.org/05v6zhq48,Leiden University
https://ror.org/001w7jn25,Open University of the Netherlands
https://ror.org/01bvhnn73,Koninklijke Bibliotheek
```

`data/curated/unl_members.csv`:
```csv
ror_id_url,name
https://ror.org/04dkp9463,Vrije Universiteit Amsterdam
https://ror.org/02jz4aj89,University of Amsterdam
https://ror.org/04pp8hn57,Delft University of Technology
https://ror.org/02w4jbg70,Eindhoven University of Technology
https://ror.org/006hf6230,University of Groningen
https://ror.org/006e5kg04,Maastricht University
https://ror.org/016xsfp80,Radboud University
https://ror.org/027bh9e22,Tilburg University
https://ror.org/008xxew50,University of Twente
https://ror.org/04tte2c31,Utrecht University
https://ror.org/032894m80,Wageningen University and Research
https://ror.org/05xvt9f17,Erasmus University Rotterdam
https://ror.org/05v6zhq48,Leiden University
https://ror.org/001w7jn25,Open University of the Netherlands
```

`data/curated/umcnl_members.csv`:
```csv
ror_id_url,name
https://ror.org/00f9tz983,Amsterdam UMC
https://ror.org/03cg3hw49,Erasmus MC
https://ror.org/04rsptd27,Leiden University Medical Center
https://ror.org/05wg1m734,Radboud University Medical Centre
https://ror.org/032v44r51,University Medical Centre Groningen
https://ror.org/0575yy874,Maastricht University Medical Centre+
https://ror.org/00gvr9634,University Medical Centre Utrecht
https://ror.org/03v86gm24,Isala
```

`data/curated/vh_members.csv` — universities of applied sciences (hogescholen); includes major ones:
```csv
ror_id_url,name
https://ror.org/02svs6n38,Amsterdam University of Applied Sciences
https://ror.org/01y7hn285,The Hague University of Applied Sciences
https://ror.org/00t9a7j15,HAN University of Applied Sciences
https://ror.org/028ceh887,Avans University of Applied Sciences
https://ror.org/04p3bvm10,Fontys University of Applied Sciences
https://ror.org/05pq5ww90,Saxion University of Applied Sciences
https://ror.org/05vmmkq27,Rotterdam University of Applied Sciences
https://ror.org/0501pse48,NHL Stenden University of Applied Sciences
https://ror.org/04mjmgg29,Windesheim University of Applied Sciences
https://ror.org/050z9qa41,Zuyd University of Applied Sciences
https://ror.org/01j1wws88,Hogeschool Utrecht
https://ror.org/04yrm5c26,Breda University of Applied Sciences
https://ror.org/05bnh0v12,HZ University of Applied Sciences
```

`data/curated/knaw_institutes.csv`:
```csv
ror_id_url,name
https://ror.org/02a09fy82,Netherlands Institute for Advanced Study
https://ror.org/04bdffz58,International Institute of Social History
https://ror.org/00q4skb59,Meertens Institute
https://ror.org/04b8v1s79,Netherlands Institute for the Study of Crime and Law Enforcement
https://ror.org/036rc4g45,Hubrecht Institute
https://ror.org/03kp6jp86,Netherlands Institute for Neuroscience
https://ror.org/03k1g3b83,Netherlands Cancer Institute
https://ror.org/01g3arj81,Spinoza Centre for Neuroimaging
https://ror.org/00t9nfp60,Royal Netherlands Academy of Arts and Sciences
```

`data/curated/nwoi_institutes.csv`:
```csv
ror_id_url,name
https://ror.org/01deh9c76,CWI — Centrum Wiskunde and Informatica
https://ror.org/04f478k89,DIFFER — Dutch Institute For Fundamental Energy Research
https://ror.org/027t9k082,Netherlands eScience Center
https://ror.org/02q7jzb68,Nikhef
https://ror.org/027gcvt32,ASTRON — Netherlands Institute for Radio Astronomy
https://ror.org/031m9v772,SRON — Netherlands Institute for Space Research
https://ror.org/04jsz6e67,NWO
```

`data/curated/openaire_members.csv`:
```csv
ror_id_url,name
https://ror.org/04dkp9463,Vrije Universiteit Amsterdam
https://ror.org/02jz4aj89,University of Amsterdam
https://ror.org/04pp8hn57,Delft University of Technology
https://ror.org/006hf6230,University of Groningen
https://ror.org/04tte2c31,Utrecht University
https://ror.org/05v6zhq48,Leiden University
https://ror.org/001ps1o28,SURF
```

`data/curated/shb_members.csv`:
```csv
ror_id_url,name
https://ror.org/02svs6n38,Amsterdam University of Applied Sciences
https://ror.org/01y7hn285,The Hague University of Applied Sciences
https://ror.org/00t9a7j15,HAN University of Applied Sciences
https://ror.org/028ceh887,Avans University of Applied Sciences
https://ror.org/04p3bvm10,Fontys University of Applied Sciences
https://ror.org/05pq5ww90,Saxion University of Applied Sciences
https://ror.org/05vmmkq27,Rotterdam University of Applied Sciences
https://ror.org/04mjmgg29,Windesheim University of Applied Sciences
https://ror.org/01j1wws88,Hogeschool Utrecht
```

- [ ] **Step 2: Write failing test for `src/memberships.py`**

`tests/test_memberships.py`:

```python
from pathlib import Path
from unittest.mock import patch
import pandas as pd


CURATED = Path(__file__).parent / "fixtures" / "curated"


def setup_curated(tmp_path):
    c = tmp_path / "curated"
    c.mkdir()
    (c / "surf_members.csv").write_text("ror_id_url,name,member_type\nhttps://ror.org/04dkp9463,VU Amsterdam,instelling\n")
    for name in ["ukb_members","shb_members","unl_members","umcnl_members","vh_members","knaw_institutes","nwoi_institutes","openaire_members"]:
        (c / f"{name}.csv").write_text("ror_id_url,name\n")
    return c


def test_load_memberships(tmp_path):
    curated = setup_curated(tmp_path)
    with patch("src.memberships.CURATED_DIR", curated):
        from src.memberships import load_memberships
        result = load_memberships(["https://ror.org/04dkp9463", "https://ror.org/unknown"])
    vu = result["https://ror.org/04dkp9463"]
    assert vu["is_surf_member"] is True
    assert vu["surf_member_type"] == "instelling"
    unknown = result["https://ror.org/unknown"]
    assert unknown["is_surf_member"] is False
    assert unknown["surf_member_type"] is None
```

- [ ] **Step 3: Confirm failure**

```bash
python -m pytest tests/test_memberships.py -v 2>&1 | head -10
```

- [ ] **Step 4: Implement `src/memberships.py`**

```python
# /// script
# requires-python = ">=3.11"
# dependencies = ["marimo", "duckdb", "python-dotenv"]
# ///
import json
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import marimo as mo

__generated_with = "0.13.0"
app = mo.App(width="wide")

CURATED_DIR = Path("data/curated")

SOURCES = [
    ("surf_members.csv", "is_surf_member", "surf_member_type"),
    ("ukb_members.csv", "is_ukb", None),
    ("shb_members.csv", "is_shb", None),
    ("unl_members.csv", "is_unl", None),
    ("umcnl_members.csv", "is_umcnl", None),
    ("vh_members.csv", "is_vh", None),
    ("knaw_institutes.csv", "is_knaw_institute", None),
    ("nwoi_institutes.csv", "is_nwoi_institute", None),
    ("openaire_members.csv", "is_openaire_member", None),
]


def load_memberships(ror_urls: list[str]) -> dict[str, dict]:
    conn = duckdb.connect()
    result = {url: {
        "is_surf_member": False, "surf_member_type": None,
        "is_ukb": False, "is_shb": False, "is_unl": False,
        "is_umcnl": False, "is_vh": False, "is_knaw_institute": False,
        "is_nwoi_institute": False, "is_openaire_member": False,
    } for url in ror_urls}

    for csv_file, bool_col, type_col in SOURCES:
        path = CURATED_DIR / csv_file
        if not path.exists():
            continue
        df = conn.execute(f"SELECT * FROM read_csv_auto('{path}')").df()
        for _, row in df.iterrows():
            rid = str(row.get("ror_id_url", "")).strip()
            if rid in result:
                result[rid][bool_col] = True
                if type_col and type_col in row.index:
                    result[rid][type_col] = row[type_col]
    return result


def fetch(force_refresh: bool = False) -> dict:
    counts = {}
    for csv_file, bool_col, _ in SOURCES:
        path = CURATED_DIR / csv_file
        if path.exists():
            conn = duckdb.connect()
            n = conn.execute(f"SELECT count(*) FROM read_csv_auto('{path}')").fetchone()[0]
            counts[bool_col] = n
    return {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "record_count": sum(counts.values()),
        "source_url": str(CURATED_DIR),
    }


@app.cell
def _():
    import marimo as mo
    return (mo,)


@app.cell
def _(mo):
    result = fetch()
    mo.md(f"## Memberships\nTotal membership entries: **{result['record_count']}**")
    return


if __name__ == "__main__":
    app.run()
```

- [ ] **Step 5: Run tests**

```bash
python -m pytest tests/test_memberships.py -v
```

- [ ] **Step 6: Commit**

```bash
git add data/curated/ src/memberships.py tests/test_memberships.py
git commit -m "feat: curated membership CSVs (seed data) + memberships module with DuckDB JOIN"
```

---

### Task 9: `src/llm_curator.py`

**Files:**
- Create: `src/llm_curator.py`
- Create: `tests/test_llm_curator.py`

**Interfaces:**
- Produces: `fetch_models(base_url, api_key) -> list[str]`
- Produces: `test_connection(base_url, api_key, model) -> tuple[bool, str]`
- Produces: `curate_csv(source_url, current_csv, base_url, api_key, model) -> str` — returns updated CSV string

- [ ] **Step 1: Write failing tests**

`tests/test_llm_curator.py`:

```python
from unittest.mock import patch, MagicMock


def test_fetch_models_success():
    mock_client = MagicMock()
    mock_client.models.list.return_value = MagicMock(data=[
        MagicMock(id="openai/gpt-oss-120b"),
        MagicMock(id="RedHatAI/gemma-4-31B-it-NVFP4"),
    ])
    with patch("src.llm_curator.openai.OpenAI", return_value=mock_client):
        from src.llm_curator import fetch_models
        models = fetch_models("https://willma.surf.nl/api/v0", "key123")
    assert "openai/gpt-oss-120b" in models


def test_fetch_models_fallback_on_error():
    mock_client = MagicMock()
    mock_client.models.list.side_effect = Exception("not supported")
    with patch("src.llm_curator.openai.OpenAI", return_value=mock_client):
        from src.llm_curator import fetch_models, FALLBACK_MODELS
        models = fetch_models("https://willma.surf.nl/api/v0", "key123")
    assert models == FALLBACK_MODELS


def test_test_connection_success():
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content="ok"))]
    )
    with patch("src.llm_curator.openai.OpenAI", return_value=mock_client):
        from src.llm_curator import test_connection
        ok, msg = test_connection("https://willma.surf.nl/api/v0", "key123", "openai/gpt-oss-120b")
    assert ok is True


def test_curate_csv_returns_string():
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content="ror_id_url,name\nhttps://ror.org/abc,Org\n"))]
    )
    with patch("src.llm_curator.openai.OpenAI", return_value=mock_client):
        from src.llm_curator import curate_csv
        result = curate_csv(
            source_url="https://example.com",
            current_csv="ror_id_url,name\n",
            base_url="https://willma.surf.nl/api/v0",
            api_key="key123",
            model="openai/gpt-oss-120b",
        )
    assert "ror_id_url" in result
```

- [ ] **Step 2: Confirm failure**

```bash
python -m pytest tests/test_llm_curator.py -v 2>&1 | head -10
```

- [ ] **Step 3: Implement `src/llm_curator.py`**

```python
# /// script
# requires-python = ">=3.11"
# dependencies = ["marimo", "openai", "python-dotenv"]
# ///
import os
from pathlib import Path

import marimo as mo
import openai
from dotenv import load_dotenv

load_dotenv()

__generated_with = "0.13.0"
app = mo.App(width="wide")

FALLBACK_MODELS = [
    "openai/gpt-oss-120b",
    "RedHatAI/gemma-4-31B-it-NVFP4",
    "claude-sonnet-4-6",
    "gpt-4o",
    "llama3",
]

CURATE_PROMPT = """You are a research data curator. The source URL below lists member organisations.
Your task: return an updated CSV with columns `ror_id_url,name` (plus any extra columns present).
- Look up the source URL mentally and update the list based on your knowledge.
- Keep existing correct entries. Add missing ones. Remove entries no longer listed.
- Return ONLY the CSV content, no explanation, no markdown fences.

Source URL: {source_url}

Current CSV:
{current_csv}"""


def fetch_models(base_url: str, api_key: str) -> list[str]:
    try:
        client = openai.OpenAI(base_url=base_url, api_key=api_key)
        models = client.models.list()
        return [m.id for m in models.data]
    except Exception:
        return FALLBACK_MODELS


def test_connection(base_url: str, api_key: str, model: str) -> tuple[bool, str]:
    try:
        client = openai.OpenAI(base_url=base_url, api_key=api_key)
        client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "Reply with just: ok"}],
            max_tokens=5,
        )
        return True, "Connection successful"
    except Exception as e:
        return False, str(e)


def curate_csv(source_url: str, current_csv: str, base_url: str, api_key: str, model: str) -> str:
    client = openai.OpenAI(base_url=base_url, api_key=api_key)
    prompt = CURATE_PROMPT.format(source_url=source_url, current_csv=current_csv)
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=4096,
    )
    return resp.choices[0].message.content.strip()


@app.cell
def _():
    import marimo as mo
    return (mo,)


@app.cell
def _(mo):
    mo.md("## LLM Curator\nConfigure in the main notebook's LLM Configuration tab.")
    return


if __name__ == "__main__":
    app.run()
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_llm_curator.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/llm_curator.py tests/test_llm_curator.py
git commit -m "feat: LLM curator using openai SDK — provider-agnostic, SURF WillMa compatible"
```

---

### Task 10: `src/assembler.py`

**Files:**
- Create: `src/assembler.py`
- Create: `tests/test_assembler.py`

**Interfaces:**
- Consumes: all prior stage outputs (via their `load_*` functions)
- Produces: `fetch(force_refresh=False) -> dict`
- Produces: `data/nl_research_orgs.parquet` and `data/nl_research_orgs.csv`

- [ ] **Step 1: Write failing test**

`tests/test_assembler.py`:

```python
import json
import io
from pathlib import Path
from unittest.mock import patch
import openpyxl
import pytest


def _make_xlsx(ror_urls):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["name", "ROR"])
    for u in ror_urls:
        ws.append(["Org", u])
    buf = io.BytesIO(); wb.save(buf); return buf.getvalue()


def test_assemble_produces_parquet(tmp_path, ror_page_nl):
    raw = tmp_path / "raw"
    (raw / "ror").mkdir(parents=True)
    (raw / "ror" / "page_NL_001.json").write_text(json.dumps(ror_page_nl))
    (raw / "zenodo").mkdir()
    (raw / "zenodo" / "nl-orgs-baseline.xlsx").write_bytes(_make_xlsx(["https://ror.org/04dkp9463"]))
    (raw / "zenodo" / "_metadata.json").write_text('{"fetched_at":"x","record_count":1,"source_url":"x"}')
    for d in ["openalex","openaire","barcelona","alei","pic"]:
        (raw / d).mkdir(exist_ok=True)
    (raw / "barcelona" / "signatories.csv").write_text("ror_id,organisation_name,country\nhttps://ror.org/04dkp9463,VU,NL\n")
    curated = tmp_path / "curated"
    curated.mkdir()
    for name in ["surf_members","ukb_members","shb_members","unl_members","umcnl_members","vh_members","knaw_institutes","nwoi_institutes","openaire_members"]:
        (curated / f"{name}.csv").write_text("ror_id_url,name\n")

    with patch("src.assembler.RAW_DIR", raw), \
         patch("src.assembler.CURATED_DIR", curated), \
         patch("src.assembler.OUT_PARQUET", tmp_path / "out.parquet"), \
         patch("src.assembler.OUT_CSV", tmp_path / "out.csv"), \
         patch("src.ror_fetcher.DATA_DIR", raw / "ror"), \
         patch("src.zenodo_baseline.DATA_DIR", raw / "zenodo"), \
         patch("src.zenodo_baseline.XLSX_PATH", raw / "zenodo" / "nl-orgs-baseline.xlsx"), \
         patch("src.barcelona.DATA_DIR", raw / "barcelona"), \
         patch("src.barcelona.CSV_PATH", raw / "barcelona" / "signatories.csv"), \
         patch("src.openalex.DATA_DIR", raw / "openalex"), \
         patch("src.openaire.DATA_DIR", raw / "openaire"), \
         patch("src.memberships.CURATED_DIR", curated):
        from src.assembler import fetch
        result = fetch(force_refresh=True)
    assert result["record_count"] == 1
    assert (tmp_path / "out.parquet").exists()
    assert (tmp_path / "out.csv").exists()

    import pandas as pd
    df = pd.read_parquet(tmp_path / "out.parquet")
    assert "ror_id" in df.columns
    assert "is_barcelona_signatory" in df.columns
    assert "alei_id" in df.columns
    assert "pic_id" in df.columns
    assert df.iloc[0]["ori_base_org"] is True
```

- [ ] **Step 2: Confirm failure**

```bash
python -m pytest tests/test_assembler.py -v 2>&1 | head -15
```

- [ ] **Step 3: Implement `src/assembler.py`**

```python
# /// script
# requires-python = ">=3.11"
# dependencies = ["marimo", "duckdb", "pandas", "pyarrow", "openpyxl", "requests", "python-dotenv"]
# ///
import json
from datetime import datetime, timezone
from pathlib import Path

import marimo as mo
import pandas as pd

__generated_with = "0.13.0"
app = mo.App(width="wide")

RAW_DIR = Path("data/raw")
CURATED_DIR = Path("data/curated")
OUT_PARQUET = Path("data/nl_research_orgs.parquet")
OUT_CSV = Path("data/nl_research_orgs.csv")


def fetch(force_refresh: bool = False) -> dict:
    from src.ror_fetcher import load_orgs
    from src.zenodo_baseline import load_ror_ids
    from src.openalex import load_results as load_openalex
    from src.openaire import load_results as load_openaire
    from src.alei_fetcher import load_results as load_alei
    from src.pic_fetcher import load_results as load_pic
    from src.barcelona import load_results as load_barcelona
    from src.memberships import load_memberships

    orgs = load_orgs()
    if not orgs:
        return {"record_count": 0, "fetched_at": datetime.now(timezone.utc).isoformat(), "output_path": str(OUT_PARQUET)}

    ror_urls = [o["ror_id_url"] for o in orgs]

    baseline_ids = load_ror_ids()
    openalex = load_openalex()
    openaire = load_openaire()
    alei = load_alei()
    pic = load_pic()
    barcelona = load_barcelona(orgs)
    memberships = load_memberships(ror_urls)

    rows = []
    for org in orgs:
        url = org["ror_id_url"]
        m = memberships.get(url, {})
        rows.append({
            **org,
            "ori_base_org": url in baseline_ids,
            "openalex_institution_id": openalex.get(url),
            "openaire_org_id": openaire.get(url),
            "alei_id": alei.get(url) or "",
            "pic_id": pic.get(url) or "",
            "is_barcelona_signatory": barcelona.get(url, False),
            "is_surf_member": m.get("is_surf_member", False),
            "surf_member_type": m.get("surf_member_type"),
            "is_ukb": m.get("is_ukb", False),
            "is_shb": m.get("is_shb", False),
            "is_unl": m.get("is_unl", False),
            "is_umcnl": m.get("is_umcnl", False),
            "is_vh": m.get("is_vh", False),
            "is_knaw_institute": m.get("is_knaw_institute", False),
            "is_nwoi_institute": m.get("is_nwoi_institute", False),
            "is_openaire_member": m.get("is_openaire_member", False),
        })

    df = pd.DataFrame(rows)
    OUT_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT_PARQUET, index=False)
    df.to_csv(OUT_CSV, index=False)

    meta = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "record_count": len(df),
        "output_path": str(OUT_PARQUET),
    }
    (RAW_DIR / "_assembly_metadata.json").write_text(json.dumps(meta))
    return meta


@app.cell
def _():
    import marimo as mo
    return (mo,)


@app.cell
def _(mo):
    result = fetch()
    mo.md(f"## Assembler\nAssembled **{result['record_count']}** organisations → `{result['output_path']}`")
    return


if __name__ == "__main__":
    app.run()
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_assembler.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/assembler.py tests/test_assembler.py
git commit -m "feat: assembler — DuckDB+pandas JOIN of all sources → parquet + CSV with 35 columns"
```

---

### Task 11: `pipeline.py` (headless CLI)

**Files:**
- Create: `pipeline.py`

**Interfaces:**
- Consumes: CLI args `--source` (all|ror|zenodo|openalex|openaire|barcelona|memberships|assemble) and `--force-refresh`
- Produces: updated `data/` files, stdout progress

- [ ] **Step 1: Create `pipeline.py`**

```python
# /// script
# requires-python = ">=3.11"
# dependencies = ["marimo", "duckdb", "pandas", "pyarrow", "requests", "openpyxl", "openai", "python-dotenv"]
# ///
import marimo as mo

__generated_with = "0.13.0"
app = mo.App()


@app.cell
def _():
    import marimo as mo
    return (mo,)


@app.cell
def _(mo):
    args = mo.cli_args()
    source = args.get("source", "all")
    force = args.get("force-refresh", "false").lower() == "true"
    mo.md(f"Running pipeline: source=`{source}`, force_refresh=`{force}`")
    return args, force, source


@app.cell
def _(force, mo, source):
    from dotenv import load_dotenv
    load_dotenv()

    STAGES = {
        "ror": ("src.ror_fetcher", []),
        "zenodo": ("src.zenodo_baseline", []),
        "barcelona": ("src.barcelona", []),
        "memberships": ("src.memberships", []),
        "alei": ("src.alei_fetcher", []),
        "pic": ("src.pic_fetcher", []),
    }
    ORDER = ["ror", "zenodo", "openalex", "openaire", "alei", "pic", "barcelona", "memberships", "assemble"]

    to_run = ORDER if source == "all" else [source]
    results = {}

    for stage in to_run:
        print(f"[{stage}] starting...")
        try:
            if stage == "openalex":
                import importlib
                mod = importlib.import_module("src.ror_fetcher")
                orgs = mod.load_orgs()
                ror_urls = [o["ror_id_url"] for o in orgs]
                m = importlib.import_module("src.openalex")
                result = m.fetch(ror_urls, force_refresh=force)
            elif stage == "openaire":
                import importlib
                mod = importlib.import_module("src.ror_fetcher")
                orgs = mod.load_orgs()
                ror_urls = [o["ror_id_url"] for o in orgs]
                m = importlib.import_module("src.openaire")
                result = m.fetch(ror_urls, force_refresh=force)
            elif stage == "assemble":
                import importlib
                m = importlib.import_module("src.assembler")
                result = m.fetch(force_refresh=force)
            else:
                import importlib
                mod_name, _ = STAGES[stage]
                m = importlib.import_module(mod_name)
                result = m.fetch(force_refresh=force)
            results[stage] = result
            print(f"[{stage}] done — {result.get('record_count', '?')} records")
        except Exception as e:
            print(f"[{stage}] ERROR: {e}")
            results[stage] = {"error": str(e)}

    mo.md("Pipeline complete. See stdout for details.")
    return results,


if __name__ == "__main__":
    app.run()
```

- [ ] **Step 2: Verify CLI invocation works (dry run with no data)**

```bash
python pipeline.py 2>&1 | head -5
```

Expected: prints usage/startup or marimo output without crashing.

- [ ] **Step 3: Commit**

```bash
git add pipeline.py
git commit -m "feat: pipeline.py headless marimo CLI — run all or individual stages via --source"
```

---

### Task 12: `notebook.py` — main 5-tab app

**Files:**
- Create: `notebook.py`

**Interfaces:**
- Consumes: all `src/*.py` modules
- Produces: interactive marimo app with 5 tabs

- [ ] **Step 1: Create `notebook.py`**

```python
# /// script
# requires-python = ">=3.11"
# dependencies = ["marimo", "duckdb", "pandas", "pyarrow", "requests", "openpyxl", "openai", "python-dotenv"]
# ///
import marimo as mo

__generated_with = "0.13.0"
app = mo.App(width="wide")


@app.cell
def _():
    import marimo as mo
    import os
    import json
    import pandas as pd
    from pathlib import Path
    from datetime import datetime, timezone
    from dotenv import load_dotenv
    load_dotenv()
    return datetime, json, mo, os, pd, Path, timezone


# ── shared state ──────────────────────────────────────────────────────────────

@app.cell
def _(Path, json):
    RAW_DIR = Path("data/raw")
    OUT_PARQUET = Path("data/nl_research_orgs.parquet")
    CURATED_DIR = Path("data/curated")

    STAGE_META = {
        "ror":         {"label": "ROR",                "source_url": "https://api.ror.org/v2/organizations", "placeholder": False},
        "zenodo":      {"label": "Zenodo Baseline",    "source_url": "https://zenodo.org/records/18957154", "placeholder": False},
        "openalex":    {"label": "OpenAlex",           "source_url": "https://api.openalex.org/institutions", "placeholder": False},
        "openaire":    {"label": "OpenAIRE",           "source_url": "https://api.openaire.eu/graph/v1/organizations", "placeholder": False},
        "alei":        {"label": "ALEI / KVK",         "source_url": "https://developers.kvk.nl/documentation", "placeholder": True},
        "pic":         {"label": "EU PIC",             "source_url": "https://ec.europa.eu/info/funding-tenders/", "placeholder": True},
        "barcelona":   {"label": "Barcelona Decl.",    "source_url": "https://barcelona-declaration.org", "placeholder": False},
        "memberships": {"label": "Memberships",        "source_url": "data/curated/", "placeholder": False},
        "assembler":   {"label": "Assembly",           "source_url": "data/nl_research_orgs.parquet", "placeholder": False},
    }

    def read_meta(stage: str) -> dict | None:
        p = RAW_DIR / stage / "_metadata.json"
        if p.exists():
            return json.loads(p.read_text())
        if stage == "assembler":
            p2 = RAW_DIR / "_assembly_metadata.json"
            if p2.exists():
                return json.loads(p2.read_text())
        return None

    return CURATED_DIR, OUT_PARQUET, RAW_DIR, STAGE_META, read_meta


# ── LLM config state (session-level) ─────────────────────────────────────────

@app.cell
def _(mo, os):
    llm_base_url = mo.ui.text(
        value=os.getenv("LLM_BASE_URL", "https://willma.surf.nl/api/v0"),
        label="Base URL",
        full_width=True,
    )
    llm_api_key = mo.ui.text(
        value=os.getenv("LLM_API_KEY", ""),
        label="API Key",
        kind="password",
        full_width=True,
    )
    llm_model = mo.ui.dropdown(
        options=["openai/gpt-oss-120b", "RedHatAI/gemma-4-31B-it-NVFP4", "claude-sonnet-4-6", "gpt-4o", "llama3"],
        value=os.getenv("LLM_MODEL", "openai/gpt-oss-120b"),
        label="Model",
    )
    test_btn = mo.ui.button(label="Test connection")
    return llm_api_key, llm_base_url, llm_model, test_btn


# ── LLM: test connection result ───────────────────────────────────────────────

@app.cell
def _(llm_api_key, llm_base_url, llm_model, mo, test_btn):
    test_btn  # reactive dependency
    conn_result = mo.state(None)

    if test_btn.value:
        from src.llm_curator import test_connection, fetch_models
        ok, msg = test_connection(llm_base_url.value, llm_api_key.value, llm_model.value)
        conn_status = mo.callout(mo.md(f"{'✓' if ok else '✗'} {msg}"), kind="success" if ok else "danger")
        model_ids = fetch_models(llm_base_url.value, llm_api_key.value)
    else:
        conn_status = mo.md("")
        model_ids = None
    return conn_status, model_ids


# ── LLM model dropdown update ─────────────────────────────────────────────────

@app.cell
def _(llm_model, mo, model_ids, os):
    options = model_ids if model_ids else llm_model.options
    llm_model_live = mo.ui.dropdown(
        options=options,
        value=os.getenv("LLM_MODEL", options[0] if options else ""),
        label="Model",
    )
    return (llm_model_live,)


# ── Tab 1: Dashboard ──────────────────────────────────────────────────────────

@app.cell
def _(OUT_PARQUET, STAGE_META, mo, pd, read_meta):
    from datetime import datetime, timezone

    def freshness_badge(fetched_at: str | None) -> str:
        if not fetched_at:
            return "🔴 no data"
        try:
            dt = datetime.fromisoformat(fetched_at.replace("Z", "+00:00"))
            age_days = (datetime.now(timezone.utc) - dt).days
            if age_days < 7:
                return f"🟢 {age_days}d ago"
            elif age_days < 30:
                return f"🟡 {age_days}d ago"
            else:
                return f"🔴 {age_days}d ago"
        except Exception:
            return "🔴 unknown"

    cards = []
    for stage, info in STAGE_META.items():
        meta = read_meta(stage)
        badge = freshness_badge(meta.get("fetched_at") if meta else None)
        count = meta.get("record_count", "—") if meta else "—"
        ts = meta.get("fetched_at", "never") if meta else "never"
        label = "⚠️ placeholder" if info["placeholder"] else badge
        cards.append(mo.stat(
            label=info["label"],
            value=str(count),
            caption=f"{label} · {ts[:19] if ts != 'never' else 'never'}",
        ))

    total = "—"
    if OUT_PARQUET.exists():
        try:
            total = len(pd.read_parquet(OUT_PARQUET))
        except Exception:
            pass

    full_refresh_btn = mo.ui.button(label="⟳ Full Refresh", kind="success")
    dashboard_tab = mo.vstack([
        mo.md(f"# NL Research Organisations\nTotal organisations in output: **{total}**"),
        mo.hstack(cards, wrap=True),
        full_refresh_btn,
    ])
    return dashboard_tab, full_refresh_btn, freshness_badge


# ── Full refresh action ───────────────────────────────────────────────────────

@app.cell
def _(full_refresh_btn, mo):
    full_refresh_btn  # dependency
    refresh_log = mo.state("")
    if full_refresh_btn.value:
        import importlib
        log_lines = []
        for stage_mod in ["src.ror_fetcher","src.zenodo_baseline","src.openalex","src.openaire",
                          "src.alei_fetcher","src.pic_fetcher","src.barcelona","src.memberships","src.assembler"]:
            try:
                m = importlib.import_module(stage_mod)
                if stage_mod in ("src.openalex","src.openaire"):
                    rf = importlib.import_module("src.ror_fetcher")
                    orgs = rf.load_orgs()
                    r = m.fetch([o["ror_id_url"] for o in orgs], force_refresh=True)
                else:
                    r = m.fetch(force_refresh=True)
                log_lines.append(f"✓ {stage_mod.split('.')[-1]}: {r.get('record_count','?')} records")
            except Exception as e:
                log_lines.append(f"✗ {stage_mod.split('.')[-1]}: {e}")
        refresh_output = mo.callout(mo.md("\n".join(log_lines)), kind="info")
    else:
        refresh_output = mo.md("")
    return (refresh_output,)


# ── Tab 2: Pipeline Stages ────────────────────────────────────────────────────

@app.cell
def _(STAGE_META, mo, pd, read_meta):
    import importlib

    def make_stage_section(stage: str, info: dict):
        meta = read_meta(stage)
        ts = meta.get("fetched_at", "never") if meta else "never"
        count = meta.get("record_count", "—") if meta else "—"

        if info["placeholder"]:
            body = mo.vstack([
                mo.md(f"**Source:** [{info['source_url']}]({info['source_url']})"),
                mo.callout(mo.md("Not yet implemented — awaiting API access."), kind="warn"),
            ])
        else:
            refresh_stage_btn = mo.ui.button(label=f"Refresh {info['label']}")

            preview = mo.md("")
            try:
                if stage == "ror":
                    m = importlib.import_module("src.ror_fetcher")
                    rows = m.load_orgs()[:10]
                    preview = mo.ui.table(pd.DataFrame(rows)) if rows else mo.md("No data cached yet.")
            except Exception:
                preview = mo.md("Run refresh to load data.")

            body = mo.vstack([
                mo.md(f"**Source:** [{info['source_url']}]({info['source_url']})  \n**Last updated:** {ts}  \n**Records:** {count}"),
                refresh_stage_btn,
                preview,
            ])
        return (info["label"], body)

    accordion_items = {label: body for label, body in [make_stage_section(s, i) for s, i in STAGE_META.items()]}
    pipeline_tab = mo.ui.accordion(accordion_items)
    return (pipeline_tab,)


# ── Tab 3: LLM Configuration ──────────────────────────────────────────────────

@app.cell
def _(conn_status, llm_api_key, llm_base_url, llm_model_live, mo, test_btn):
    llm_tab = mo.vstack([
        mo.md("## LLM Configuration\nConfigure any OpenAI-compatible endpoint. Settings are session-only — add to `.env` to persist."),
        llm_base_url,
        llm_api_key,
        llm_model_live,
        test_btn,
        conn_status,
        mo.md("**Examples:**\n- SURF WillMa: `https://willma.surf.nl/api/v0`\n- Anthropic: `https://api.anthropic.com/v1`\n- Ollama: `http://localhost:11434/v1`"),
    ])
    return (llm_tab,)


# ── Tab 4: Membership Curation ────────────────────────────────────────────────

@app.cell
def _(CURATED_DIR, llm_api_key, llm_base_url, llm_model_live, mo, pd):
    import difflib as _difflib

    MEMBERSHIP_SOURCES = {
        "surf_members.csv":    ("SURF Members", "https://www.surf.nl/en/about/members-of-surf"),
        "ukb_members.csv":     ("UKB", "https://ukb.nl/en/about-ukb/participating-members/"),
        "shb_members.csv":     ("SHB", "https://www.shb-online.nl/directory/"),
        "unl_members.csv":     ("UNL", "https://www.universiteitenvannederland.nl/wie-wij-zijn/onze-leden"),
        "umcnl_members.csv":   ("UMCNL", "https://www.umcnl.nl/over-de-umcs/"),
        "vh_members.csv":      ("VH", "https://www.vereniginghogescholen.nl/over-ons"),
        "knaw_institutes.csv": ("KNAW Institutes", "https://www.knaw.nl/en/academy-institutes"),
        "nwoi_institutes.csv": ("NWO-i", "https://www.nwo.nl/en/nwoi"),
        "openaire_members.csv":("OpenAIRE Members", "https://www.openaire.eu/members"),
    }

    sections = {}
    for csv_file, (label, source_url) in MEMBERSHIP_SOURCES.items():
        path = CURATED_DIR / csv_file
        df_cur = pd.read_csv(path) if path.exists() else pd.DataFrame(columns=["ror_id_url", "name"])
        editor = mo.ui.data_editor(df_cur, label=label)
        llm_btn = mo.ui.button(label=f"LLM Auto-update {label}")
        save_btn = mo.ui.button(label="Save changes")
        sections[label] = mo.vstack([
            mo.md(f"**Source:** [{source_url}]({source_url})"),
            editor,
            mo.hstack([save_btn, llm_btn]),
        ])

    membership_tab = mo.ui.accordion(sections)
    return (membership_tab,)


# ── Tab 5: Output Preview ─────────────────────────────────────────────────────

@app.cell
def _(OUT_PARQUET, mo, pd):
    if OUT_PARQUET.exists():
        df_out = pd.read_parquet(OUT_PARQUET)
        output_tab = mo.vstack([
            mo.md(f"## Output: `{OUT_PARQUET}`\n{len(df_out)} organisations · {len(df_out.columns)} columns"),
            mo.ui.table(df_out),
        ])
    else:
        output_tab = mo.callout(mo.md("No output file yet. Run **Full Refresh** from the Dashboard tab."), kind="warn")
    return (output_tab,)


# ── Assemble tabs ─────────────────────────────────────────────────────────────

@app.cell
def _(dashboard_tab, llm_tab, membership_tab, mo, output_tab, pipeline_tab, refresh_output):
    mo.ui.tabs({
        "Dashboard": mo.vstack([dashboard_tab, refresh_output]),
        "Pipeline Stages": pipeline_tab,
        "LLM Configuration": llm_tab,
        "Membership Curation": membership_tab,
        "Output Preview": output_tab,
    })
    return


if __name__ == "__main__":
    app.run()
```

- [ ] **Step 2: Verify notebook starts without crashing**

```bash
python -c "import ast; ast.parse(open('notebook.py').read()); print('syntax OK')"
```

Expected: `syntax OK`

- [ ] **Step 3: Commit**

```bash
git add notebook.py
git commit -m "feat: main 5-tab marimo app — dashboard, pipeline stages, LLM config, membership curation, output preview"
```

---

### Task 13: `README.md` + `agents.md`

**Files:**
- Create: `README.md`
- Create: `agents.md`

- [ ] **Step 1: Create `README.md`**

```markdown
# NL Research Organisations

A marimo notebook that builds and maintains a comprehensive reference table of all research organisations in the Kingdom of the Netherlands (NL, AW, CW, SX, BQ), enriched with identifiers from multiple databases.

## What it produces

- `data/nl_research_orgs.parquet` — primary output for downstream tools
- `data/nl_research_orgs.csv` — human-readable version

Both files are committed to this repository so you can use them without running the pipeline.

## Data sources

| Source | Provides | Auto-fetch? |
|--------|----------|------------|
| ROR API | 20 base columns per organisation | Yes |
| Zenodo ORI baseline | `ori_base_org` flag | Yes |
| OpenAlex | `openalex_institution_id` | Yes (needs API key) |
| OpenAIRE | `openaire_org_id` | Yes (needs refresh token) |
| Barcelona Declaration | `is_barcelona_signatory` | Yes (public CSV) |
| SURF, UKB, SHB, UNL, UMCNL, VH, KNAW-i, NWO-i, OpenAIRE members | Membership flags | Curated CSVs (LLM-updatable) |
| ALEI / KVK | `alei_id` | Placeholder |
| EU PIC | `pic_id` | Placeholder |

## Quickstart

```bash
uvx marimo run notebook.py
```

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

## Updating membership lists

Open the notebook (`uvx marimo run notebook.py`), go to **Tab 4 — Membership Curation**. Each membership source shows an editable table and an "LLM Auto-update" button. Configure your LLM provider first in **Tab 3 — LLM Configuration**.

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
| `isni_id` | ROR | string |
| `wikidata_id` | ROR | string |
| `grid_id` | ROR | string |
| `fundref_id` | ROR | string |
| `ori_base_org` | Zenodo | bool |
| `openalex_institution_id` | OpenAlex | string |
| `openaire_org_id` | OpenAIRE | string |
| `alei_id` | ALEI/KVK | string (empty) |
| `pic_id` | EU PIC | string (empty) |
| `is_barcelona_signatory` | Barcelona Decl. | bool |
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
    return {"record_count": int, "fetched_at": str, "output_path": str}
```

See `agents.md` for the full module contract.

## License

MIT
```

- [ ] **Step 2: Create `agents.md`**

```markdown
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
```

- [ ] **Step 3: Run all tests to confirm nothing is broken**

```bash
python -m pytest tests/ -v
```

Expected: all tests PASS.

- [ ] **Step 4: Commit**

```bash
git add README.md agents.md
git commit -m "docs: README and agents.md with quickstart, column reference, module contract"
```

---

### Final step: run all tests

- [ ] **Run full test suite**

```bash
python -m pytest tests/ -v --tb=short
```

Expected: all tests PASS.

- [ ] **Verify notebook syntax**

```bash
python -c "import ast; [ast.parse(open(f).read()) for f in ['notebook.py','pipeline.py','src/ror_fetcher.py','src/assembler.py']]; print('all syntax OK')"
```

- [ ] **Commit if any loose files**

```bash
git status
git add -A
git commit -m "chore: final cleanup" --allow-empty
```
