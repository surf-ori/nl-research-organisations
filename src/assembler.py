# /// script
# requires-python = ">=3.11"
# dependencies = ["marimo", "duckdb", "pandas", "pyarrow", "openpyxl", "requests", "python-dotenv"]
# ///
import json
from datetime import datetime, timezone
from pathlib import Path

import marimo as mo
import pandas as pd

__generated_with = "0.23.10"
app = mo.App(width="wide")

RAW_DIR = Path("data/raw")
CURATED_DIR = Path("data/curated")
OUT_PARQUET = Path("data/nl_research_orgs.parquet")
OUT_CSV = Path("data/nl_research_orgs.csv")

COLUMN_ORDER = [
    "name", "acronym", "aliases", "ror_id", "ror_id_url",
    "org_type", "status", "established_year", "country_code", "location_name",
    "lat", "lng", "geonames_id", "website_url", "wikipedia_url",
    "isni_id", "wikidata_id", "grid_id", "fundref_id",
    "ori_base_org", "openalex_institution_id", "openaire_org_id",
    "alei_id", "pic_id",
    "is_barcelona_signatory",
    "is_surf_member", "surf_member_type",
    "is_ukb", "is_shb", "is_unl", "is_umcnl", "is_vh",
    "is_knaw_institute", "is_nwoi_institute", "is_openaire_member",
]


def fetch(force_refresh: bool = False) -> dict:
    """Import and call load_* from all stage modules, assemble 35-column DataFrame,
    write OUT_PARQUET and OUT_CSV.

    Returns {"record_count": int, "fetched_at": str, "output_path": str}
    """
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
        return {
            "record_count": 0,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "output_path": str(OUT_PARQUET),
        }

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
            "name": org.get("name"),
            "acronym": org.get("acronym"),
            "aliases": org.get("aliases"),
            "ror_id": org.get("ror_id"),
            "ror_id_url": url,
            "org_type": org.get("org_type"),
            "status": org.get("status"),
            "established_year": org.get("established_year"),
            "country_code": org.get("country_code"),
            "location_name": org.get("location_name"),
            "lat": org.get("lat"),
            "lng": org.get("lng"),
            "geonames_id": org.get("geonames_id"),
            "website_url": org.get("website_url"),
            "wikipedia_url": org.get("wikipedia_url"),
            "isni_id": org.get("isni_id"),
            "wikidata_id": org.get("wikidata_id"),
            "grid_id": org.get("grid_id"),
            "fundref_id": org.get("fundref_id"),
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

    df = pd.DataFrame(rows)[COLUMN_ORDER]
    OUT_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT_PARQUET, index=False)
    df.to_csv(OUT_CSV, index=False)

    meta = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "record_count": len(df),
        "output_path": str(OUT_PARQUET),
    }
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    (RAW_DIR / "_assembly_metadata.json").write_text(json.dumps(meta))
    return meta


@app.cell(hide_code=True)
def setup():
    # Imports — make marimo available for the interactive cell below
    import marimo as mo
    return (mo,)


@app.cell(hide_code=True)
def summary(mo):
    # Assembler summary — run the full assembly and report how many organisations were written
    result = fetch()
    mo.md(f"## Assembler\nAssembled **{result['record_count']}** organisations → `{result['output_path']}`")
    return


if __name__ == "__main__":
    app.run()
