# /// script
# requires-python = ">=3.11"
# dependencies = ["marimo", "duckdb", "pandas", "pyarrow", "openpyxl", "requests", "python-dotenv"]
# ///

import marimo

__generated_with = "0.23.10"
app = marimo.App(width="wide")


with app.setup:
    # Setup — imports and output constants
    import marimo as mo
    import json
    from datetime import datetime, timezone
    from pathlib import Path

    import pandas as pd

    # Output paths and the canonical 35-column order for the assembled dataset
    RAW_DIR    = Path("data/raw")
    CURATED_DIR = Path("data/curated")
    OUT_PARQUET = Path("data/nl_research_orgs.parquet")
    OUT_CSV     = Path("data/nl_research_orgs.csv")

    COLUMN_ORDER = [
        "name", "acronym", "aliases", "ror_id", "ror_id_url",
        "org_type", "status", "established_year", "country_code", "location_name",
        "lat", "lng", "geonames_id", "website_url", "wikipedia_url",
        "isni_id", "wikidata_id", "grid_id", "fundref_id",
        "ori_base_org", "openalex_institution_id", "openaire_org_id",
        "alei_id", "pic_id",
        "nbn_prefix",
        "is_barcelona_signatory",
        "is_surf_member", "surf_member_type",
        "is_ukb", "is_shb", "is_unl", "is_umcnl", "is_vh",
        "is_knaw_institute", "is_nwoi_institute", "is_openaire_member",
    ]


@app.function
def fetch(force_refresh: bool = False) -> dict:
    """Assemble all pipeline stage outputs into a single 35-column Parquet + CSV dataset.

    Imports load_* from every pipeline stage module, joins on ror_id_url, and writes
    OUT_PARQUET and OUT_CSV. Local imports prevent circular dependencies at module level.
    Returns {"record_count": int, "fetched_at": str, "output_path": str}.
    """
    # Local imports avoid circular dependencies when stages import each other
    from src.ror_fetcher   import load_orgs
    from src.zenodo_baseline import load_ror_ids
    from src.openalex      import load_results as load_openalex
    from src.openaire      import load_results as load_openaire
    from src.alei_fetcher  import load_results as load_alei
    from src.pic_fetcher   import load_results as load_pic
    from src.barcelona     import load_results as load_barcelona
    from src.memberships   import load_memberships
    from src.nbn_fetcher   import load_results as load_nbn

    orgs = load_orgs()
    if not orgs:
        return {
            "record_count": 0,
            "fetched_at":   datetime.now(timezone.utc).isoformat(),
            "output_path":  str(OUT_PARQUET),
        }

    ror_urls     = [o["ror_id_url"] for o in orgs]
    baseline_ids = load_ror_ids()
    openalex     = load_openalex()
    openaire     = load_openaire()
    alei         = load_alei()
    pic          = load_pic()
    barcelona    = load_barcelona(orgs)
    memberships  = load_memberships(ror_urls)
    nbn          = load_nbn()

    rows = []
    for org in orgs:
        url = org["ror_id_url"]
        m   = memberships.get(url, {})
        rows.append({
            "name":                    org.get("name"),
            "acronym":                 org.get("acronym"),
            "aliases":                 org.get("aliases"),
            "ror_id":                  org.get("ror_id"),
            "ror_id_url":              url,
            "org_type":                org.get("org_type"),
            "status":                  org.get("status"),
            "established_year":        org.get("established_year"),
            "country_code":            org.get("country_code"),
            "location_name":           org.get("location_name"),
            "lat":                     org.get("lat"),
            "lng":                     org.get("lng"),
            "geonames_id":             org.get("geonames_id"),
            "website_url":             org.get("website_url"),
            "wikipedia_url":           org.get("wikipedia_url"),
            "isni_id":                 org.get("isni_id"),
            "wikidata_id":             org.get("wikidata_id"),
            "grid_id":                 org.get("grid_id"),
            "fundref_id":              org.get("fundref_id"),
            "ori_base_org":            url in baseline_ids,
            "openalex_institution_id": openalex.get(url),
            "openaire_org_id":         openaire.get(url),
            "alei_id":                 alei.get(url) or "",
            "pic_id":                  pic.get(url) or "",
            "nbn_prefix":              nbn.get(url, ""),
            "is_barcelona_signatory":  barcelona.get(url, False),
            "is_surf_member":          m.get("is_surf_member", False),
            "surf_member_type":        m.get("surf_member_type"),
            "is_ukb":                  m.get("is_ukb", False),
            "is_shb":                  m.get("is_shb", False),
            "is_unl":                  m.get("is_unl", False),
            "is_umcnl":                m.get("is_umcnl", False),
            "is_vh":                   m.get("is_vh", False),
            "is_knaw_institute":       m.get("is_knaw_institute", False),
            "is_nwoi_institute":       m.get("is_nwoi_institute", False),
            "is_openaire_member":      m.get("is_openaire_member", False),
        })

    df = pd.DataFrame(rows)[COLUMN_ORDER]
    OUT_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT_PARQUET, index=False)
    df.to_csv(OUT_CSV, index=False)

    meta = {
        "fetched_at":   datetime.now(timezone.utc).isoformat(),
        "record_count": len(df),
        "output_path":  str(OUT_PARQUET),
    }
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    (RAW_DIR / "_assembly_metadata.json").write_text(json.dumps(meta))
    return meta


@app.cell(hide_code=True)
def header():
    # Header — assembler module description and output file overview
    mo.md("""
    ## Assembler — Dataset Assembly

    Joins all pipeline stage outputs into a single 35-column dataset:

    - **Input**: cached JSON/CSV files produced by each `src/*.py` stage
    - **Output**: `data/nl_research_orgs.parquet` and `data/nl_research_orgs.csv`

    Call `fetch()` to rebuild the dataset from the current cached stage outputs.
    Call each stage's `fetch()` first if you want to refresh the source data too.
    """)
    return


@app.cell(hide_code=True)
def preview():
    # Data preview — show the first 20 rows of the assembled Parquet if it exists
    content = (
        mo.vstack([
            mo.md(f"**{len(pd.read_parquet(OUT_PARQUET))} organisations** · `{OUT_PARQUET}`"),
            mo.ui.table(pd.read_parquet(OUT_PARQUET).head(20)),
        ])
        if OUT_PARQUET.exists()
        else mo.callout(
            mo.md("No assembled dataset yet — run `fetch()` or use the Pipeline Stages tab."),
            kind="warn",
        )
    )
    content
    return


if __name__ == "__main__":
    app.run()
