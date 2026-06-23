# /// script
# requires-python = ">=3.11"
# dependencies = ["marimo", "duckdb", "python-dotenv"]
# ///

import marimo

__generated_with = "0.23.10"
app = marimo.App(width="wide")


with app.setup:
    # Setup — imports and membership source table definitions
    import marimo as mo
    import json
    from datetime import datetime, timezone
    from pathlib import Path

    import duckdb

    # Metadata directory for the dashboard's read_meta() function
    MEMBERSHIPS_META_DIR = Path("data/raw/memberships")

    # Directory where the curated membership CSV files live
    CURATED_DIR = Path("data/curated")

    # Each tuple: (csv_filename, output_bool_key, output_type_key, csv_type_column)
    # output_type_key and csv_type_column are None when the CSV has no type column.
    SOURCES = [
        ("surf_members.csv",      "is_surf_member",      "surf_member_type", "member_type"),
        ("ukb_members.csv",       "is_ukb",               None,              None),
        ("shb_members.csv",       "is_shb",               None,              None),
        ("unl_members.csv",       "is_unl",               None,              None),
        ("umcnl_members.csv",     "is_umcnl",             None,              None),
        ("vh_members.csv",        "is_vh",                None,              None),
        ("knaw_institutes.csv",   "is_knaw_institute",    None,              None),
        ("nwoi_institutes.csv",   "is_nwoi_institute",    None,              None),
        ("openaire_members.csv",  "is_openaire_member",   None,              None),
    ]


@app.function
def load_memberships(ror_urls: list[str]) -> dict[str, dict]:
    """Return a mapping of ror_id_url → membership flags dict for every given ROR URL.

    All nine membership sources are queried via DuckDB. Every URL in ror_urls appears
    as a key, with False/None defaults for all flags even when not found in any CSV.
    Keys: is_surf_member, surf_member_type, is_ukb, is_shb, is_unl, is_umcnl,
          is_vh, is_knaw_institute, is_nwoi_institute, is_openaire_member.
    """
    conn = duckdb.connect()
    result: dict[str, dict] = {
        url: {
            "is_surf_member":    False,
            "surf_member_type":  None,
            "is_ukb":            False,
            "is_shb":            False,
            "is_unl":            False,
            "is_umcnl":          False,
            "is_vh":             False,
            "is_knaw_institute": False,
            "is_nwoi_institute": False,
            "is_openaire_member": False,
        }
        for url in ror_urls
    }

    for csv_file, bool_col, result_type_key, csv_type_col in SOURCES:
        path = CURATED_DIR / csv_file
        if not path.exists():
            continue
        rel  = conn.execute(f"SELECT * FROM read_csv_auto('{path}')")
        cols = [desc[0] for desc in rel.description]
        rows = rel.fetchall()
        ror_idx  = cols.index("ror_id_url") if "ror_id_url" in cols else None
        type_idx = cols.index(csv_type_col) if csv_type_col and csv_type_col in cols else None
        if ror_idx is None:
            continue
        for row in rows:
            rid = str(row[ror_idx]).strip()
            if rid in result:
                result[rid][bool_col] = True
                if result_type_key and type_idx is not None:
                    result[rid][result_type_key] = row[type_idx]

    return result


@app.function
def fetch(force_refresh: bool = False) -> dict:
    """Count rows across all curated membership CSVs.

    Returns {"record_count": int, "fetched_at": str, "source_url": str}.
    """
    conn = duckdb.connect()
    total = 0
    for csv_file, _, __, ___ in SOURCES:
        path = CURATED_DIR / csv_file
        if path.exists():
            n = conn.execute(f"SELECT count(*) FROM read_csv_auto('{path}')").fetchone()[0]
            total += n
    meta = {
        "fetched_at":   datetime.now(timezone.utc).isoformat(),
        "record_count": total,
        "source_url":   str(CURATED_DIR),
    }
    MEMBERSHIPS_META_DIR.mkdir(parents=True, exist_ok=True)
    (MEMBERSHIPS_META_DIR / "_metadata.json").write_text(json.dumps(meta))
    return meta


@app.cell(hide_code=True)
def header():
    # Header — memberships module description and list of curated sources
    mo.md("""
    ## Memberships — Curated Membership Lists

    Joins curated CSV files (one per membership type) against the ROR universe to
    set boolean and type flags on each organisation. All CSVs must have a
    `ror_id_url` column; `surf_members.csv` additionally has a `member_type` column.

    Sources in `data/curated/`:
    | CSV | Flag |
    |-----|------|
    | surf_members.csv | is_surf_member |
    | ukb_members.csv | is_ukb |
    | shb_members.csv | is_shb |
    | unl_members.csv | is_unl |
    | umcnl_members.csv | is_umcnl |
    | vh_members.csv | is_vh |
    | knaw_institutes.csv | is_knaw_institute |
    | nwoi_institutes.csv | is_nwoi_institute |
    | openaire_members.csv | is_openaire_member |
    """)
    return


@app.cell(hide_code=True)
def summary():
    # Summary — total membership entries across all curated CSVs
    conn = duckdb.connect()
    rows = []
    for csv_file, bool_col, _, __ in SOURCES:
        path = CURATED_DIR / csv_file
        if path.exists():
            n = conn.execute(f"SELECT count(*) FROM read_csv_auto('{path}')").fetchone()[0]
            rows.append({"source": csv_file, "flag": bool_col, "count": n})
        else:
            rows.append({"source": csv_file, "flag": bool_col, "count": "—"})
    import pandas as pd
    mo.vstack([
        mo.md(f"**{sum(r['count'] for r in rows if isinstance(r['count'], int))} total** membership entries"),
        mo.ui.table(pd.DataFrame(rows)),
    ])
    return


if __name__ == "__main__":
    app.run()
