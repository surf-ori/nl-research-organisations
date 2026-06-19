# /// script
# requires-python = ">=3.11"
# dependencies = ["marimo", "duckdb", "python-dotenv"]
# ///
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import marimo as mo

__generated_with = "0.13.0"
app = mo.App(width="wide")

CURATED_DIR = Path("data/curated")

# Each entry: (csv_file, bool_flag_key, result_type_key, csv_type_column)
# result_type_key and csv_type_column are None when there is no type column.
SOURCES = [
    ("surf_members.csv", "is_surf_member", "surf_member_type", "member_type"),
    ("ukb_members.csv", "is_ukb", None, None),
    ("shb_members.csv", "is_shb", None, None),
    ("unl_members.csv", "is_unl", None, None),
    ("umcnl_members.csv", "is_umcnl", None, None),
    ("vh_members.csv", "is_vh", None, None),
    ("knaw_institutes.csv", "is_knaw_institute", None, None),
    ("nwoi_institutes.csv", "is_nwoi_institute", None, None),
    ("openaire_members.csv", "is_openaire_member", None, None),
]


def load_memberships(ror_urls: list[str]) -> dict[str, dict]:
    """Returns dict mapping ror_id_url -> membership flags dict.

    Keys: is_surf_member (bool), surf_member_type (str|None),
          is_ukb (bool), is_shb (bool), is_unl (bool), is_umcnl (bool),
          is_vh (bool), is_knaw_institute (bool), is_nwoi_institute (bool),
          is_openaire_member (bool).
    All ror_urls appear as keys in the output (with False/None defaults).
    """
    conn = duckdb.connect()
    result = {
        url: {
            "is_surf_member": False,
            "surf_member_type": None,
            "is_ukb": False,
            "is_shb": False,
            "is_unl": False,
            "is_umcnl": False,
            "is_vh": False,
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
        rel = conn.execute(f"SELECT * FROM read_csv_auto('{path}')")
        columns = [desc[0] for desc in rel.description]
        rows = rel.fetchall()
        ror_idx = columns.index("ror_id_url") if "ror_id_url" in columns else None
        type_idx = columns.index(csv_type_col) if csv_type_col and csv_type_col in columns else None
        if ror_idx is None:
            continue
        for row in rows:
            rid = str(row[ror_idx]).strip()
            if rid in result:
                result[rid][bool_col] = True
                if result_type_key and type_idx is not None:
                    result[rid][result_type_key] = row[type_idx]

    return result


def fetch(force_refresh: bool = False) -> dict:
    """Returns {"record_count": int, "fetched_at": str, "source_url": str}."""
    conn = duckdb.connect()
    counts = {}
    for csv_file, bool_col, _, __ in SOURCES:
        path = CURATED_DIR / csv_file
        if path.exists():
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
