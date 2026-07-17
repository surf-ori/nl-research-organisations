# /// script
# requires-python = ">=3.11"
# dependencies = ["marimo", "pandas", "requests", "python-dotenv"]
# ///
"""Flatten multi-file raw pipeline sources into single JSON files.

GitHub Pages serves static files only — there's no directory listing over HTTP, so
apps/dashboard.py can't glob() a folder of per-org JSON files the way the local
pipeline does. This runs once at build time, where the real filesystem (and the
src/ package) are available, and writes one JSON file per source under
apps/public/raw_flat/ for the WASM app to fetch directly. JSON (not parquet) because
these API responses are semi-structured and vary in shape row to row — pyarrow's
strict schema inference chokes on that (e.g. empty/childless struct fields).
"""

import json
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.ror_fetcher import load_orgs  # noqa: E402

OUT_DIR = Path(__file__).resolve().parent / "public" / "raw_flat"


# OpenAlex records carry a few very verbose analytical fields (per-org research topic
# breakdowns, year-by-year citation counts, ...) that bloat the preview file without
# helping anyone eyeball what the source returned. Full-fidelity data is always
# available in the committed data/raw/openalex/*.json — this is just a lighter view.
_OPENALEX_DROP_COLUMNS = [
    "topics", "topic_share", "counts_by_year", "associated_institutions", "repositories",
]


def _flatten_per_org_json(stage: str, list_key: str) -> pd.DataFrame:
    rows = []
    for path in sorted((REPO_ROOT / "data" / "raw" / stage).glob("*.json")):
        if path.name == "_metadata.json":
            continue
        data = json.loads(path.read_text())
        rows.extend(data.get(list_key, []))
    return pd.DataFrame(rows)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    pd.DataFrame(load_orgs()).to_json(OUT_DIR / "ror.json", orient="records")

    openalex = _flatten_per_org_json("openalex", "results")
    openalex = openalex.drop(columns=_OPENALEX_DROP_COLUMNS, errors="ignore")
    openalex.to_json(OUT_DIR / "openalex.json", orient="records")

    _flatten_per_org_json("openaire", "results").to_json(OUT_DIR / "openaire.json", orient="records")

    print(f"Flattened raw previews written to {OUT_DIR}")


if __name__ == "__main__":
    main()
