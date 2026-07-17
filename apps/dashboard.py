# /// script
# requires-python = ">=3.11"
# dependencies = ["marimo", "polars", "pyarrow"]
# ///
import marimo

__generated_with = "0.23.14"
app = marimo.App(width="full")


@app.cell(hide_code=True)
def imports():
    # Imports — read-only viewer has no LLM/curation dependencies.
    # Uses polars, not pandas: marimo's WASM runtime has fallback I/O patches for
    # polars' read_csv/read_parquet/read_ndjson (fetches bytes itself and decodes via
    # pyarrow, since pyodide has no working fsspec/network layer for polars' own I/O)
    # but no equivalent patch for pandas — pd.read_csv/read_parquet/read_json over a
    # URL silently fail in the browser. See preview_loaders below for the NDJSON-only
    # detail that also matters here.
    import marimo as mo
    import polars as pl
    return mo, pl


@app.cell(hide_code=True)
def shared_state(mo, pl):
    # Shared constants — all data is read from the public/ folder bundled alongside this
    # app, via mo.notebook_location(), so paths resolve both locally and on GitHub Pages
    PUBLIC_DIR = mo.notebook_location() / "public"
    OUT_PARQUET = PUBLIC_DIR / "nl_research_orgs.parquet"
    # GitHub Pages serves static files only (no directory listing over HTTP, and no
    # WASM support for xlsx/many-small-JSON-files at all) — data/raw/ itself isn't
    # even committed to the repo (bronze, gitignored). src/processor.py converts
    # everything currently cached into one committed Parquet file per source under
    # data/processed/, which this app reads directly.
    PROCESSED_DIR = PUBLIC_DIR / "processed"
    LOGO_PATH = PUBLIC_DIR / "assets" / "surf-logo.svg"

    # One entry per pipeline stage: display label + canonical source URL
    STAGE_META = {
        "ror":         {"label": "ROR",             "source_url": "https://api.ror.org/v2/organizations"},
        "zenodo":      {"label": "Zenodo Baseline", "source_url": "https://zenodo.org/records/18957154"},
        "openalex":    {"label": "OpenAlex",        "source_url": "https://api.openalex.org/institutions"},
        "openaire":    {"label": "OpenAIRE",        "source_url": "https://api.openaire.eu/graph/v1/organizations"},
        "alei":        {"label": "ALEI / KVK",      "source_url": "https://overheid.io/documentatie/openkvk"},
        "pic":         {"label": "EU PIC",          "source_url": "https://ec.europa.eu/info/funding-tenders/"},
        "barcelona":   {"label": "Barcelona Decl.", "source_url": "https://barcelona-declaration.org"},
        "duo":         {"label": "DUO HO/MBO",      "source_url": "https://data.overheid.nl/dataset/adressen_ho"},
        "memberships": {"label": "Memberships",     "source_url": "data/curated/"},
        "nbn":         {"label": "NBN Prefixes",    "source_url": "https://www.kb.nl/.../nbn-catalogus"},
        "assembler":   {"label": "Assembly",        "source_url": "data/nl_research_orgs.parquet"},
    }

    def read_meta(stage: str) -> dict | None:
        # Read the bundled <stage>_metadata.json for a pipeline stage; None if it
        # wasn't published. read_ndjson (not read_json) — a single bare JSON object is
        # trivially valid one-line NDJSON, and marimo's WASM patch only covers
        # read_csv/read_parquet/read_ndjson (read_json shares the same fallback, but
        # being explicit about the actual file shape avoids relying on that).
        path = PROCESSED_DIR / f"{stage}_metadata.json"
        try:
            return pl.read_ndjson(str(path)).to_dicts()[0]
        except Exception:
            return None

    return LOGO_PATH, OUT_PARQUET, PROCESSED_DIR, STAGE_META, read_meta


@app.cell(hide_code=True)
def dashboard_header(mo, LOGO_PATH):
    # Header — title + intro, with the SURF logo top right
    dashboard_header = mo.hstack(
        [
            mo.md(
                "# NL Research Organisations\n"
                "[![DOI](https://zenodo.org/badge/doi/10.5281/zenodo.21416468.svg)]"
                "(https://doi.org/10.5281/zenodo.21416468)\n\n"
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
def dashboard_section(STAGE_META, mo, read_meta, OUT_PARQUET, pl):
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
        total = pl.read_parquet(str(OUT_PARQUET)).height
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
def preview_loaders(pl, OUT_PARQUET, PROCESSED_DIR):
    # Preview loaders — the assembled output, plus every processed (silver) source:
    # each pipeline stage's data/processed/<name>.parquet, built locally by
    # src/processor.py and committed to git (data/raw/ itself is gitignored — bronze,
    # too big/slow to commit — and GitHub Pages can't read it anyway: no directory
    # listing over HTTP, no WASM support for xlsx or DUO's field/records JSON shape).
    # A single loader works for every entry since everything is already Parquet —
    # marimo's WASM fallback patches polars' read_parquet to work over HTTP in Pyodide
    # (pandas has no equivalent patch; see notebook.py's own note on this).
    _PROCESSED_FILES = [
        ("ROR",                  "ror"),
        ("Zenodo Baseline",      "zenodo"),
        ("OpenAlex",             "openalex"),
        ("OpenAIRE",             "openaire"),
        ("ALEI / KVK",           "alei"),
        ("EU PIC",               "pic"),
        ("DUO HO",               "duo_ho"),
        ("DUO MBO",              "duo_mbo"),
        ("Barcelona Declaration","barcelona"),
        ("Memberships (joined)", "memberships"),
        ("SURF Members",         "surf_members"),
        ("UKB",                  "ukb_members"),
        ("SHB",                  "shb_members"),
        ("UNL",                  "unl_members"),
        ("UMCNL",                "umcnl_members"),
        ("VH",                   "vh_members"),
        ("KNAW Institutes",      "knaw_institutes"),
        ("NWO-i",                "nwoi_institutes"),
        ("OpenAIRE Members",     "openaire_members"),
        ("NBN Prefixes",         "nbn_prefixes"),
    ]

    def _load_assembled():
        try:
            return pl.read_parquet(str(OUT_PARQUET))
        except Exception:
            return None

    def _load_processed(name: str):
        def _loader():
            try:
                return pl.read_parquet(str(PROCESSED_DIR / f"{name}.parquet"))
            except Exception:
                return None
        return _loader

    PREVIEW_SOURCES = {"Assembled Output": _load_assembled}
    for _label, _name in _PROCESSED_FILES:
        PREVIEW_SOURCES[_label] = _load_processed(_name)

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
    with mo.status.spinner(title=f"Loading {dataset_dropdown.value}…", remove_on_exit=True):
        _df = PREVIEW_SOURCES[dataset_dropdown.value]()
    if _df is None:
        _table = mo.callout(mo.md("Not available in this published snapshot."), kind="warn")
    else:
        _table = mo.vstack([
            mo.md(f"{_df.height} rows · {len(_df.columns)} columns"),
            mo.ui.table(_df),
        ])

    dataset_preview_section = mo.vstack([
        mo.md(
            "## Dataset Preview\n"
            "Pick any dataset to inspect it directly — the final assembled output, "
            "a raw pipeline source, or any curated membership/prefix list. Defaults "
            "to the assembled output."
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
