# /// script
# requires-python = ">=3.11"
# dependencies = ["marimo", "pandas", "pyarrow", "openpyxl"]
# ///
"""
Processor — bronze (data/raw/) + curated (data/curated/) -> silver (data/processed/)

data/raw/ is gitignored (bronze — regenerate any time via each stage's fetch()) and
data/curated/ is hand-authored and committed as-is, but neither is a convenient format
for the Dataset Preview in notebook.py or the published apps/dashboard.py: raw sources
are many small per-org JSON files (slow to re-parse on every preview) or non-parquet
formats (xlsx has no WASM support at all), and apps/dashboard.py can't read data/raw/
once it's gitignored (GitHub Pages serves static files only, no directory listing).

This stage converts everything currently cached into one parquet file per source under
data/processed/ — committed to git, small, and uniformly readable via read_parquet in
both pandas and polars/WASM. It also copies each stage's own data/raw/<stage>/_metadata.json
(bronze, gitignored) into data/processed/<name>_metadata.json (silver, committed), so
freshness info (fetched_at/record_count/source_url) survives even though the raw
directory it originally lived in isn't tracked in git.

Pure local re-formatting, no network calls — run any time after fetching/curating to
refresh the committed snapshot.
"""

import marimo

__generated_with = "0.23.10"
app = marimo.App(width="full")


with app.setup:
    # Setup — imports and internal helpers
    import marimo as mo
    import json
    from datetime import datetime, timezone
    from pathlib import Path

    import pandas as pd

    RAW_DIR       = Path("data/raw")
    CURATED_DIR   = Path("data/curated")
    PROCESSED_DIR = Path("data/processed")

    # OpenAlex records carry a few very verbose analytical fields (per-org research
    # topic breakdowns, year-by-year citation counts, ...) that bloat the preview
    # without helping anyone eyeball what the source returned. Full-fidelity data is
    # always available in the committed data/raw/openalex/*.json — this is a lighter view.
    _OPENALEX_DROP_COLUMNS = [
        "topics", "topic_share", "counts_by_year", "associated_institutions", "repositories",
    ]

    def _stringify_object_columns(df: pd.DataFrame) -> pd.DataFrame:
        """Coerce every object-dtype column to str-or-None, JSON-encoding dict/list values.

        Upstream raw data isn't perfectly consistent — e.g. ROR's own fundref_id comes
        through as a bare int for one organisation while every other row has it as a
        string or None, and OpenAlex's "international" field is an empty dict for some
        institutions and a populated one for others. Both fail pyarrow's schema
        inference on to_parquet() (mixed scalar types, or a struct with no child field
        inferred from an all-empty column); normalizing every object column to plain
        strings avoids depending on any one field being clean or structurally uniform.
        """
        df = df.copy()
        for col in df.columns:
            if df[col].dtype == object:
                df[col] = df[col].apply(
                    lambda v: v if v is None else (json.dumps(v) if isinstance(v, (dict, list)) else str(v))
                )
        return df

    def _flatten_per_org_json(stage: str, list_key: str) -> pd.DataFrame:
        """Flatten data/raw/<stage>/<ror_id>.json (each an API response envelope) into
        one row per result, tagged implicitly via the envelope's own fields."""
        rows = []
        for path in sorted((RAW_DIR / stage).glob("*.json")):
            if path.name == "_metadata.json":
                continue
            data = json.loads(path.read_text())
            rows.extend(data.get(list_key, []))
        return pd.DataFrame(rows)

    def _flatten_matches(stage: str) -> pd.DataFrame:
        """Flatten data/raw/<stage>/<ror_id>.json (each a bare list of name-search
        matches) into one row per match, tagged with the ROR URL it was found for.
        Shared shape between alei (OpenKvK) and pic (EU Participant Register)."""
        rows = []
        for path in sorted((RAW_DIR / stage).glob("*.json")):
            if path.name == "_metadata.json":
                continue
            matches = json.loads(path.read_text())
            for match in matches:
                rows.append({"ror_id_url": f"https://ror.org/{path.stem}", **match})
        return pd.DataFrame(rows)

    def _read_duo_dump(filename: str) -> pd.DataFrame:
        """Read a DUO dump (records are field-order lists, not dicts) into a DataFrame."""
        path = RAW_DIR / "duo" / filename
        if not path.exists():
            return pd.DataFrame()
        data = json.loads(path.read_text())
        field_ids = [f["id"] for f in data.get("fields", [])]
        return pd.DataFrame(data.get("records", []), columns=field_ids)

    def _copy_meta(stage: str, name: str) -> None:
        """Copy a stage's raw _metadata.json into data/processed/<name>_metadata.json."""
        src = RAW_DIR / stage / "_metadata.json"
        if src.exists():
            (PROCESSED_DIR / f"{name}_metadata.json").write_text(src.read_text())

    def _write_parquet(name: str, df: pd.DataFrame) -> int:
        """Write a DataFrame as data/processed/<name>.parquet; skip if empty. Returns
        the row count written (0 if skipped)."""
        if df.empty:
            return 0
        df = _stringify_object_columns(df)
        df.to_parquet(PROCESSED_DIR / f"{name}.parquet", index=False)
        return len(df)


@app.function
def fetch(force_refresh: bool = False) -> dict:
    """Rebuild data/processed/ from whatever data/raw/ and data/curated/ currently hold.

    No network calls — this is pure local re-formatting, so force_refresh has no effect
    and is only accepted for dispatch consistency with the other pipeline stages. Like
    the assembler, this stage produces files rather than fetching from a URL, so it
    returns output_path instead of source_url.
    Returns {"record_count": int, "fetched_at": str, "output_path": str}.
    """
    from src.ror_fetcher import load_orgs

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    total = 0

    orgs = load_orgs()
    if orgs:
        total += _write_parquet("ror", pd.DataFrame(orgs))
    _copy_meta("ror", "ror")

    zenodo_xlsx = RAW_DIR / "zenodo" / "nl-orgs-baseline.xlsx"
    if zenodo_xlsx.exists():
        total += _write_parquet("zenodo", pd.read_excel(zenodo_xlsx))
    _copy_meta("zenodo", "zenodo")

    openalex = _flatten_per_org_json("openalex", "results").drop(columns=_OPENALEX_DROP_COLUMNS, errors="ignore")
    total += _write_parquet("openalex", openalex)
    _copy_meta("openalex", "openalex")

    total += _write_parquet("openaire", _flatten_per_org_json("openaire", "results"))
    _copy_meta("openaire", "openaire")

    total += _write_parquet("alei", _flatten_matches("alei"))
    _copy_meta("alei", "alei")

    total += _write_parquet("pic", _flatten_matches("pic"))
    _copy_meta("pic", "pic")

    barcelona_csv = RAW_DIR / "barcelona" / "signatories.csv"
    if barcelona_csv.exists():
        total += _write_parquet("barcelona", pd.read_csv(barcelona_csv))
    _copy_meta("barcelona", "barcelona")

    total += _write_parquet("duo_ho", _read_duo_dump("ho.json"))
    total += _write_parquet("duo_mbo", _read_duo_dump("mbo.json"))
    _copy_meta("duo", "duo")

    _copy_meta("nbn", "nbn")
    _copy_meta("memberships", "memberships")
    if orgs:
        from src.memberships import load_memberships
        ror_urls = [o["ror_id_url"] for o in orgs]
        joined = pd.DataFrame.from_dict(load_memberships(ror_urls), orient="index").reset_index()
        joined = joined.rename(columns={"index": "ror_id_url"})
        total += _write_parquet("memberships", joined)

    # The assembler writes its own metadata to data/raw/_assembly_metadata.json
    assembly_meta = RAW_DIR / "_assembly_metadata.json"
    if assembly_meta.exists():
        (PROCESSED_DIR / "assembler_metadata.json").write_text(assembly_meta.read_text())

    if CURATED_DIR.exists():
        for csv_path in sorted(CURATED_DIR.glob("*.csv")):
            total += _write_parquet(csv_path.stem, pd.read_csv(csv_path))

    meta = {
        "fetched_at":   datetime.now(timezone.utc).isoformat(),
        "record_count": total,
        "output_path":  str(PROCESSED_DIR),
    }
    return meta


@app.cell(hide_code=True)
def header():
    # Header — processor module description
    mo.md("""
    ## Processor — Bronze/Curated to Silver Parquet

    Converts every currently-cached raw (`data/raw/`) and curated (`data/curated/`)
    source into one uniform Parquet file per source under `data/processed/` —
    committed to git, small, and readable directly by `notebook.py`'s Dataset Preview
    and the published `apps/dashboard.py`.

    Pure local re-formatting, no network calls. Call `fetch()` any time after
    fetching/curating to refresh the committed snapshot.
    """)
    return


@app.cell(hide_code=True)
def summary():
    # Summary — list currently processed files
    files = sorted(PROCESSED_DIR.glob("*.parquet")) if PROCESSED_DIR.exists() else []
    content = (
        mo.md(f"**{len(files)} processed files** in `{PROCESSED_DIR}`")
        if files
        else mo.callout(mo.md("No processed data yet — run `fetch()`."), kind="warn")
    )
    content
    return


if __name__ == "__main__":
    app.run()
