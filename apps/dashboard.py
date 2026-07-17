# /// script
# requires-python = ">=3.11"
# dependencies = ["marimo", "pandas", "pyarrow"]
# ///
import marimo

__generated_with = "0.23.14"
app = marimo.App(width="wide")


@app.cell(hide_code=True)
def imports():
    # Imports — read-only viewer has no LLM/curation dependencies
    import marimo as mo
    import pandas as pd
    return mo, pd


@app.cell(hide_code=True)
def shared_state(mo, pd):
    # Shared constants — all data is read from the public/ folder bundled alongside this
    # app, via mo.notebook_location(), so paths resolve both locally and on GitHub Pages
    PUBLIC_DIR = mo.notebook_location() / "public"
    OUT_PARQUET = PUBLIC_DIR / "nl_research_orgs.parquet"
    CURATED_DIR = PUBLIC_DIR / "curated"
    RAW_DIR = PUBLIC_DIR / "raw"
    LOGO_PATH = PUBLIC_DIR / "assets" / "surf-logo.svg"

    # One entry per pipeline stage: display label + canonical source URL
    STAGE_META = {
        "ror":         {"label": "ROR",             "source_url": "https://api.ror.org/v2/organizations"},
        "zenodo":      {"label": "Zenodo Baseline", "source_url": "https://zenodo.org/records/18957154"},
        "openalex":    {"label": "OpenAlex",        "source_url": "https://api.openalex.org/institutions"},
        "openaire":    {"label": "OpenAIRE",        "source_url": "https://api.openaire.eu/graph/v1/organizations"},
        "alei":        {"label": "ALEI / KVK",      "source_url": "https://developers.kvk.nl/documentation"},
        "pic":         {"label": "EU PIC",          "source_url": "https://ec.europa.eu/info/funding-tenders/"},
        "barcelona":   {"label": "Barcelona Decl.", "source_url": "https://barcelona-declaration.org"},
        "memberships": {"label": "Memberships",     "source_url": "data/curated/"},
        "nbn":         {"label": "NBN Prefixes",    "source_url": "https://www.kb.nl/.../nbn-catalogus"},
        "assembler":   {"label": "Assembly",        "source_url": "data/nl_research_orgs.parquet"},
    }

    def read_meta(stage: str) -> dict | None:
        # Read the bundled _metadata.json for a pipeline stage; None if it wasn't published
        path = (
            RAW_DIR / "_assembly_metadata.json"
            if stage == "assembler"
            else RAW_DIR / stage / "_metadata.json"
        )
        try:
            return pd.read_json(str(path), typ="series").to_dict()
        except Exception:
            return None

    return CURATED_DIR, LOGO_PATH, OUT_PARQUET, STAGE_META, read_meta


@app.cell(hide_code=True)
def dashboard_header(mo, LOGO_PATH):
    # Header — title + intro, with the SURF logo top right
    dashboard_header = mo.hstack(
        [
            mo.md(
                "# NL Research Organisations\n"
                "A read-only public view of the reference table of research "
                "organisations in the Kingdom of the Netherlands, assembled from "
                "ROR plus several enrichment sources and curated membership lists. "
                "This snapshot reflects the data committed to "
                "[the source repository](https://github.com/surf-ori/nl-research-organisations) "
                "as of its last publish — for the interactive curation tool "
                "(refreshing sources, editing membership lists), run `notebook.py` "
                "from that repository locally."
            ),
            mo.image(src=str(LOGO_PATH), alt="SURF logo", width=140),
        ],
        justify="space-between",
        align="start",
    )
    return (dashboard_header,)


@app.cell(hide_code=True)
def dashboard_section(STAGE_META, mo, read_meta, OUT_PARQUET, pd):
    # Dashboard — freshness cards per pipeline stage, as of the last publish
    def freshness_badge(fetched_at: str | None) -> str:
        if not fetched_at:
            return "no data"
        try:
            from datetime import datetime, timezone
            dt = datetime.fromisoformat(fetched_at.replace("Z", "+00:00"))
            age_days = (datetime.now(timezone.utc) - dt).days
            if age_days < 7:
                return f"{age_days}d ago (fresh)"
            elif age_days < 30:
                return f"{age_days}d ago (aging)"
            return f"{age_days}d ago (stale)"
        except Exception:
            return "unknown"

    cards = []
    for _stage, _info in STAGE_META.items():
        _meta = read_meta(_stage)
        _badge = freshness_badge(_meta.get("fetched_at") if _meta else None)
        _count = _meta.get("record_count", "—") if _meta else "—"
        _ts = _meta.get("fetched_at", "never") if _meta else "never"
        cards.append(mo.stat(
            label=_info["label"],
            value=str(_count),
            caption=f"{_badge} · {_ts[:19] if _ts != 'never' else 'never'}",
        ))

    total = "—"
    try:
        total = len(pd.read_parquet(str(OUT_PARQUET)))
    except Exception:
        pass

    dashboard_section = mo.vstack([
        mo.md(
            "Each card is one pipeline source, as of the data last published to "
            "this app. **Value** is the record count at that publish; the caption "
            "shows how fresh it was then — **fresh** (under 7 days), **aging** "
            "(under 30 days), or **stale** (30+ days) — followed by the exact "
            "fetch timestamp.\n\n"
            f"Total organisations in the current output: **{total}**.\n\n"
            "This file feeds the Dutch Open Research Information data lake, and "
            "is archived at the "
            "[SURF Zenodo community](https://zenodo.org/communities/surf/) where "
            "it gets fetched for further processing."
        ),
        mo.hstack(cards, wrap=True),
    ])
    return (dashboard_section,)


@app.cell(hide_code=True)
def preview_loaders(pd, OUT_PARQUET, CURATED_DIR):
    # Preview loaders — the assembled output plus every curated membership/prefix CSV
    _CURATED_FILES = [
        ("SURF Members",      "surf_members.csv"),
        ("UKB",               "ukb_members.csv"),
        ("SHB",               "shb_members.csv"),
        ("UNL",               "unl_members.csv"),
        ("UMCNL",             "umcnl_members.csv"),
        ("VH",                "vh_members.csv"),
        ("KNAW Institutes",   "knaw_institutes.csv"),
        ("NWO-i",             "nwoi_institutes.csv"),
        ("OpenAIRE Members",  "openaire_members.csv"),
        ("NBN Prefixes",      "nbn_prefixes.csv"),
    ]

    def _load_assembled():
        try:
            return pd.read_parquet(str(OUT_PARQUET))
        except Exception:
            return None

    def _load_curated_csv(filename: str):
        def _loader():
            try:
                return pd.read_csv(str(CURATED_DIR / filename))
            except Exception:
                return None
        return _loader

    PREVIEW_SOURCES = {"Assembled Output": _load_assembled}
    for _label, _filename in _CURATED_FILES:
        PREVIEW_SOURCES[_label] = _load_curated_csv(_filename)

    return (PREVIEW_SOURCES,)


@app.cell(hide_code=True)
def dataset_preview_dropdown(mo, PREVIEW_SOURCES):
    # Dataset preview dropdown — defaults to the final assembled output
    dataset_dropdown = mo.ui.dropdown(
        options=list(PREVIEW_SOURCES.keys()),
        value="Assembled Output",
        label="Dataset",
    )
    return (dataset_dropdown,)


@app.cell(hide_code=True)
def dataset_preview_table(mo, dataset_dropdown, PREVIEW_SOURCES):
    # Dataset preview table — renders whichever dataset is selected above
    _df = PREVIEW_SOURCES[dataset_dropdown.value]()
    if _df is None:
        _table = mo.callout(mo.md("Not available in this published snapshot."), kind="warn")
    else:
        _table = mo.vstack([
            mo.md(f"{len(_df)} rows · {len(_df.columns)} columns"),
            mo.ui.table(_df),
        ])

    dataset_preview_section = mo.vstack([
        mo.md(
            "## Dataset Preview\n"
            "Pick any dataset to inspect it directly — the final assembled "
            "output, or any curated membership/prefix list. Defaults to the "
            "assembled output."
        ),
        dataset_dropdown,
        _table,
    ])
    return (dataset_preview_section,)


@app.cell(hide_code=True)
def page(dashboard_header, dashboard_section, dataset_preview_section, mo):
    # Main layout — single scrolling page, read-only
    page_ui = mo.vstack([
        dashboard_header,
        dashboard_section,
        dataset_preview_section,
    ])
    page_ui
    return


if __name__ == "__main__":
    app.run()
