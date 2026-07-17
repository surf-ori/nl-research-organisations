# /// script
# requires-python = ">=3.11"
# dependencies = ["marimo", "pandas", "requests", "python-dotenv", "openpyxl"]
# ///
"""Flatten/convert multi-file or non-WASM-readable raw pipeline sources for the
published app.

GitHub Pages serves static files only — there's no directory listing over HTTP, so
apps/dashboard.py can't glob() a folder of per-org JSON files the way the local
pipeline does, and it can't read an .xlsx or DUO's field/records-list JSON shape at
all (no WASM support in polars for arbitrary formats). This runs once at build time,
where the real filesystem (and the src/ package) are available, and writes one file
per source under apps/public/raw_flat/ for the WASM app to fetch directly:

- ROR/OpenAlex/OpenAIRE/ALEI (many per-org JSON files) -> one NDJSON file each
- Zenodo baseline (.xlsx) -> one CSV file
- DUO HO/MBO (field/records-list JSON) -> one CSV file each

NDJSON (one JSON object per line), not a JSON array and not parquet, for the first
three:
- These API responses are semi-structured and vary in shape row to row — pyarrow's
  strict schema inference chokes on a single parquet file for that (e.g.
  empty/childless struct fields).
- marimo's WASM fallback for polars' read_json/read_ndjson (pyodide has no working
  fsspec/network layer for polars' own I/O, so marimo fetches bytes itself and
  decodes via pyarrow) always calls `pyarrow.json.read_json`, which only accepts
  NDJSON — a plain JSON array makes it fail with "Column() changed from object to
  array in row 0". `apps/dashboard.py` must use `pl.read_ndjson` (not `pd.read_json`,
  which has no WASM support at all — see that module's `preview_loaders` docstring)
  to read these files back.
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


def _flatten_alei() -> pd.DataFrame:
    """Flatten data/raw/alei/<ror_id>.json (each a bare list of OpenKvK matches)
    into one row per match, tagged with the ROR URL it was found for."""
    rows = []
    for path in sorted((REPO_ROOT / "data" / "raw" / "alei").glob("*.json")):
        if path.name == "_metadata.json":
            continue
        matches = json.loads(path.read_text())
        for match in matches:
            rows.append({"ror_id_url": f"https://ror.org/{path.stem}", **match})
    return pd.DataFrame(rows)


def _read_duo_dump(filename: str) -> pd.DataFrame:
    """Read a DUO dump (records are field-order lists, not dicts) into a DataFrame."""
    path = REPO_ROOT / "data" / "raw" / "duo" / filename
    if not path.exists():
        return pd.DataFrame()
    data = json.loads(path.read_text())
    field_ids = [f["id"] for f in data.get("fields", [])]
    return pd.DataFrame(data.get("records", []), columns=field_ids)


def _stringify_object_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Coerce every object-dtype column to str-or-None.

    ROR's own raw data isn't perfectly consistent — e.g. one organisation's
    fundref_id comes through as a bare int while every other row has it as a string
    or None. A column like that writes out as NDJSON with a mix of number/null/string
    values, which polars' own schema inference (used when apps/dashboard.py runs
    outside Pyodide, where marimo's pyarrow-based WASM fallback doesn't apply) can't
    resolve — it commits to a type from the first rows and then errors on a later
    row that doesn't match. Normalizing to str avoids depending on any one field
    happening to be clean.
    """
    df = df.copy()
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].apply(lambda v: v if v is None or isinstance(v, (dict, list)) else str(v))
    return df


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    ror = _stringify_object_columns(pd.DataFrame(load_orgs()))
    ror.to_json(OUT_DIR / "ror.ndjson", orient="records", lines=True)

    openalex = _flatten_per_org_json("openalex", "results")
    openalex = openalex.drop(columns=_OPENALEX_DROP_COLUMNS, errors="ignore")
    openalex = _stringify_object_columns(openalex)
    openalex.to_json(OUT_DIR / "openalex.ndjson", orient="records", lines=True)

    openaire = _stringify_object_columns(_flatten_per_org_json("openaire", "results"))
    openaire.to_json(OUT_DIR / "openaire.ndjson", orient="records", lines=True)

    zenodo_xlsx = REPO_ROOT / "data" / "raw" / "zenodo" / "nl-orgs-baseline.xlsx"
    if zenodo_xlsx.exists():
        pd.read_excel(zenodo_xlsx).to_csv(OUT_DIR / "zenodo.csv", index=False)

    alei = _stringify_object_columns(_flatten_alei())
    if not alei.empty:
        alei.to_json(OUT_DIR / "alei.ndjson", orient="records", lines=True)

    _read_duo_dump("ho.json").to_csv(OUT_DIR / "duo_ho.csv", index=False)
    _read_duo_dump("mbo.json").to_csv(OUT_DIR / "duo_mbo.csv", index=False)

    print(f"Flattened raw previews written to {OUT_DIR}")


if __name__ == "__main__":
    main()
