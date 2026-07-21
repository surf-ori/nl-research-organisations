# /// script
# requires-python = ">=3.11"
# dependencies = ["marimo", "duckdb", "pandas", "pyarrow", "requests", "openpyxl", "openai", "python-dotenv"]
# ///

import marimo

__generated_with = "0.23.14"
app = marimo.App(width="full")


@app.cell(hide_code=True)
def imports():
    # Imports — load all dependencies and read environment variables from .env
    import marimo as mo
    import os
    import json
    import pandas as pd
    from pathlib import Path
    from datetime import datetime, timezone
    from dotenv import load_dotenv
    load_dotenv()
    return Path, datetime, json, mo, os, pd, timezone


@app.cell(hide_code=True)
def shared_state(Path, json):
    # Shared constants — paths and per-stage metadata used throughout the notebook
    OUT_PARQUET = Path("data/nl_research_orgs.parquet")
    CURATED_DIR = Path("data/curated")
    # data/processed/ is the committed silver tier (src/processor.py) — freshness
    # cards and Dataset Preview read from here rather than data/raw/ directly, since
    # data/raw/ is gitignored (bronze, reproducible via fetch()) and this way local
    # runs and a fresh clone behave the same.
    PROCESSED_DIR = Path("data/processed")
    LOGO_PATH = Path("assets/surf-logo.svg")

    # One entry per pipeline stage: display label, canonical source URL, and
    # whether the stage is a placeholder (not yet implemented)
    STAGE_META = {
        "ror":         {"label": "ROR",             "source_url": "https://api.ror.org/v2/organizations",           "placeholder": False},
        "zenodo":      {"label": "Zenodo Baseline", "source_url": "https://zenodo.org/records/18957154",            "placeholder": False},
        "openalex":    {"label": "OpenAlex",        "source_url": "https://api.openalex.org/institutions",          "placeholder": False},
        "openaire":    {"label": "OpenAIRE",        "source_url": "https://api.openaire.eu/graph/v3/organizations", "placeholder": False},
        "alei":        {"label": "ALEI / KVK",      "source_url": "https://overheid.io/documentatie/openkvk",       "placeholder": False},
        "pic":         {"label": "EU PIC",          "source_url": "https://ec.europa.eu/info/funding-tenders/",     "placeholder": False},
        "barcelona":   {"label": "Barcelona Decl.", "source_url": "https://barcelona-declaration.org",              "placeholder": False},
        "duo":         {"label": "DUO HO/MBO",      "source_url": "https://data.overheid.nl/dataset/adressen_ho",   "placeholder": False},
        "memberships": {"label": "Memberships",     "source_url": "data/curated/",                                  "placeholder": False},
        "nbn":         {"label": "NBN Prefixes",    "source_url": "https://www.kb.nl/.../nbn-catalogus",            "placeholder": False},
        "assembler":   {"label": "Assembly",        "source_url": "data/nl_research_orgs.parquet",                  "placeholder": False},
    }

    def read_meta(stage: str) -> dict | None:
        # Read the processed <stage>_metadata.json for a pipeline stage; returns None
        # if src.processor.fetch() hasn't been run since that stage last fetched.
        p = PROCESSED_DIR / f"{stage}_metadata.json"
        return json.loads(p.read_text()) if p.exists() else None

    return CURATED_DIR, LOGO_PATH, OUT_PARQUET, PROCESSED_DIR, STAGE_META, read_meta


@app.cell(hide_code=True)
def preview_loaders(pd, OUT_PARQUET, PROCESSED_DIR):
    # Preview loaders — one entry per pipeline dataset, used by the Dataset Preview
    # dropdown. Everything except the assembled output reads data/processed/<name>.parquet
    # (silver, built by src.processor.fetch()) rather than data/raw/ directly — a single
    # Parquet read is instant regardless of how many per-org files the source fetched,
    # unlike the old approach of re-parsing OpenAlex/OpenAIRE's ~1700 raw JSON files on
    # every preview (which needed an artificial 300-file cap to stay responsive).
    _PROCESSED_FILES = [
        ("ROR",                  "ror"),
        ("Zenodo Baseline",      "zenodo"),
        ("OpenAlex",             "openalex"),
        ("OpenAIRE",             "openaire"),
        ("ALEI / KVK",           "alei"),
        ("EU PIC",               "pic"),
        ("DUO Institutes",       "duo_institutes"),
        ("Barcelona Declaration","barcelona"),
        ("Memberships (joined)", "memberships"),
        ("SURF Members (curated)",     "surf_members"),
        ("UKB (curated)",              "ukb_members"),
        ("SHB (curated)",              "shb_members"),
        ("UNL (curated)",              "unl_members"),
        ("UMCNL (curated)",            "umcnl_members"),
        ("VH (curated)",               "vh_members"),
        ("KNAW Institutes (curated)",  "knaw_institutes"),
        ("NWO-i (curated)",            "nwoi_institutes"),
        ("OpenAIRE Members (curated)", "openaire_members"),
        ("NBN Prefixes (curated)",     "nbn_prefixes"),
    ]

    def _load_assembled():
        return pd.read_parquet(OUT_PARQUET) if OUT_PARQUET.exists() else None

    def _load_processed(name: str):
        def _loader():
            path = PROCESSED_DIR / f"{name}.parquet"
            return pd.read_parquet(path) if path.exists() else None
        return _loader

    PREVIEW_SOURCES = {"Assembled Output": _load_assembled}
    for _label, _name in _PROCESSED_FILES:
        PREVIEW_SOURCES[_label] = _load_processed(_name)

    return (PREVIEW_SOURCES,)


@app.cell(hide_code=True)
def refresh_state(mo):
    # Refresh results state — accumulates per-stage fetch outcomes across button clicks
    # mo.state() persists values across reactive re-runs of this cell
    get_refresh_results, set_refresh_results = mo.state({})
    return get_refresh_results, set_refresh_results


@app.cell(hide_code=True)
def save_state(mo):
    # Save status state — tracks membership CSV save and LLM-update outcomes per file
    get_save_status, set_save_status = mo.state({})
    return get_save_status, set_save_status


@app.cell(hide_code=True)
def llm_config(mo, os):
    # LLM configuration widgets — pre-populated from .env, editable within the session
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


@app.cell(hide_code=True)
def llm_test_result(llm_api_key, llm_base_url, llm_model, mo, test_btn):
    # LLM connection test — shows a spinner while the request is in flight, result appears after
    if test_btn.value:
        from src.llm_curator import test_connection, fetch_models
        with mo.status.spinner(title="Testing connection…", remove_on_exit=False):
            ok, msg = test_connection(llm_base_url.value, llm_api_key.value, llm_model.value)
        conn_status = mo.callout(mo.md(f"{'✓' if ok else '✗'} {msg}"), kind="success" if ok else "danger")
        with mo.status.spinner(title="Fetching available models…", remove_on_exit=False):
            model_ids = fetch_models(llm_base_url.value, llm_api_key.value)
    else:
        conn_status = mo.md("")
        model_ids = None
    return conn_status, model_ids


@app.cell(hide_code=True)
def llm_model_live(llm_model, mo, model_ids, os):
    # Live model dropdown — rebuilds with API results after a successful connection test
    # llm_model.options returns a dict in marimo 0.23+; use iter() to get the first key safely
    options = model_ids if model_ids else llm_model.options
    first_option = next(iter(options)) if options else ""
    llm_model_live = mo.ui.dropdown(
        options=options,
        value=os.getenv("LLM_MODEL", first_option),
        label="Model",
    )
    return (llm_model_live,)


@app.cell(hide_code=True)
def dashboard_header(mo, LOGO_PATH):
    # Dashboard header — title + intro, with the SURF logo top right
    dashboard_header = mo.hstack(
        [
            mo.md(
                "# NL Research Organisations\n"
                "[![DOI](https://zenodo.org/badge/doi/10.5281/zenodo.21416468.svg)]"
                "(https://doi.org/10.5281/zenodo.21416468)\n\n"
                "A reference table of research organisations in the Kingdom of the "
                "Netherlands, assembled from ROR plus several enrichment sources and "
                "curated membership lists."
            ),
            mo.image(src=str(LOGO_PATH), alt="SURF logo", width=140),
        ],
        justify="space-between",
        align="start",
    )
    return (dashboard_header,)


@app.cell(hide_code=True)
def dashboard_section(OUT_PARQUET, STAGE_META, datetime, mo, pd, read_meta, timezone):
    # Dashboard — freshness cards per pipeline stage and overall organisation count
    def freshness_badge(fetched_at: str | None) -> str:
        # Translate an ISO timestamp into a human-readable age label
        if not fetched_at:
            return "no data"
        try:
            dt = datetime.fromisoformat(fetched_at.replace("Z", "+00:00"))
            age_days = (datetime.now(timezone.utc) - dt).days
            if age_days < 7:
                return f"{age_days}d ago (fresh)"
            elif age_days < 30:
                return f"{age_days}d ago (aging)"
            return f"{age_days}d ago (stale)"
        except Exception:
            return "unknown"

    # Build one stat card per pipeline stage
    cards = []
    for _stage, _info in STAGE_META.items():
        _meta = read_meta(_stage)
        _badge = freshness_badge(_meta.get("fetched_at") if _meta else None)
        _count = _meta.get("record_count", "—") if _meta else "—"
        _ts = _meta.get("fetched_at", "never") if _meta else "never"
        _label = "placeholder" if _info["placeholder"] else _badge
        cards.append(mo.stat(
            label=_info["label"],
            value=str(_count),
            caption=f"{_label} · {_ts[:19] if _ts != 'never' else 'never'}",
        ))

    # Total organisations in the assembled parquet (if it exists)
    total = "—"
    if OUT_PARQUET.exists():
        try:
            total = len(pd.read_parquet(OUT_PARQUET))
        except Exception:
            pass

    dashboard_section = mo.vstack([
        mo.md(
            "Each card below is one pipeline source. **Value** is the record count "
            "last fetched; the caption shows how fresh that cache is — **fresh** "
            "(under 7 days), **aging** (under 30 days), or **stale** (30+ days) — "
            "followed by the exact timestamp of the last fetch. `placeholder` "
            "sources aren't implemented yet.\n\n"
            f"Total organisations in the current output: **{total}**.\n\n"
            "The file this pipeline produces (`data/nl_research_orgs.parquet`) "
            "feeds the Dutch Open Research Information data lake, and is archived "
            "at the [SURF Zenodo community](https://zenodo.org/communities/surf/) "
            "where it gets fetched for further processing. See the "
            "[live dashboard](https://surf-ori.github.io/nl-research-organisations/) "
            "for a published, read-only view of this same data."
        ),
        mo.hstack(cards, wrap=True),
    ])
    return (dashboard_section,)


@app.cell(hide_code=True)
def curate_data_intro(mo):
    # Curate Data — explains this section and the logical order of what follows
    curate_data_intro = mo.md(
        "## Curate Data\n"
        "This is where the output file gets (re)built. The sections below run in a "
        "logical order:\n\n"
        "1. **LLM Configuration** — optional, but required if you plan to use any "
        "\"LLM Auto-update\" button further down.\n"
        "2. **Membership Curation** — review and edit the curated membership CSVs "
        "(SURF, UKB, SHB, …) that feed the membership flags in the output.\n"
        "3. **Pipeline Stages** — fetch or refresh each raw data source "
        "individually.\n\n"
        "Or click **Full Refresh** below to run all pipeline stages in order and "
        "reassemble the output in one click. It re-fetches every source with "
        "`force_refresh=True`, re-runs the assembler, and finishes by rebuilding "
        "`data/processed/` — the committed Parquet snapshot that feeds Dataset "
        "Preview above and the published dashboard — so everything ends up "
        "reflecting `data/curated/` plus freshly-fetched raw data. This can take a "
        "while and calls every external API."
    )
    return (curate_data_intro,)


@app.cell(hide_code=True)
def full_refresh_button(mo):
    # Full Refresh button — see the explanation in the Curate Data section above
    full_refresh_btn = mo.ui.button(label="Full Refresh", kind="success")
    return (full_refresh_btn,)


@app.cell(hide_code=True)
def full_refresh(full_refresh_btn, mo):
    # Full pipeline refresh — runs all stages in dependency order; shows progress bar while running
    if full_refresh_btn.value:
        import importlib
        log_lines = []
        _stages = [
            "src.ror_fetcher", "src.zenodo_baseline", "src.openalex", "src.openaire",
            "src.alei_fetcher", "src.pic_fetcher", "src.barcelona", "src.duo_ho_mbo",
            "src.memberships", "src.nbn_fetcher", "src.assembler", "src.processor",
        ]
        for _mod in mo.status.progress_bar(
            _stages, title="Full Refresh", subtitle="Running all pipeline stages…", remove_on_exit=False,
        ):
            try:
                m = importlib.import_module(_mod)
                # openalex and openaire need the ROR URL list as input; pic and alei
                # search by organisation name, so they need the full org dicts instead
                if _mod in ("src.openalex", "src.openaire"):
                    rf = importlib.import_module("src.ror_fetcher")
                    ror_urls = [o["ror_id_url"] for o in rf.load_orgs()]
                    r = m.fetch(ror_urls, force_refresh=True)
                elif _mod in ("src.pic_fetcher", "src.alei_fetcher"):
                    rf = importlib.import_module("src.ror_fetcher")
                    r = m.fetch(rf.load_orgs(), force_refresh=True)
                else:
                    r = m.fetch(force_refresh=True)
                log_lines.append(f"✓ {_mod.split('.')[-1]}: {r.get('record_count', '?')} records")
            except Exception as e:
                log_lines.append(f"✗ {_mod.split('.')[-1]}: {e}")
        refresh_output = mo.callout(mo.md("\n".join(log_lines)), kind="info")
    else:
        refresh_output = mo.md("")
    return (refresh_output,)


@app.cell(hide_code=True)
def pipeline_section(
    STAGE_META,
    get_refresh_results,
    mo,
    read_meta,
    set_refresh_results,
):
    # Pipeline stages — accordion with one collapsible section per data source
    import importlib as _il

    _STAGE_MODULES = {
        "ror": "src.ror_fetcher", "zenodo": "src.zenodo_baseline",
        "alei": "src.alei_fetcher", "pic": "src.pic_fetcher",
        "duo": "src.duo_ho_mbo", "nbn": "src.nbn_fetcher",
    }

    def _refresh_fn(stage, label):
        # Build an on_click handler that fetches the given stage and stores the result in state
        def _handler(_):
            try:
                with mo.status.spinner(title=f"Refreshing {label}…", remove_on_exit=False):
                    m = _il.import_module(_STAGE_MODULES.get(stage, f"src.{stage}"))
                    if stage in ("openalex", "openaire"):
                        rf = _il.import_module("src.ror_fetcher")
                        ror_urls = [o["ror_id_url"] for o in rf.load_orgs()]
                        result = m.fetch(ror_urls, force_refresh=True)
                    elif stage in ("pic", "alei"):
                        # PIC and ALEI/KVK search by organisation name, not ROR ID
                        rf = _il.import_module("src.ror_fetcher")
                        result = m.fetch(rf.load_orgs(), force_refresh=True)
                    else:
                        result = m.fetch(force_refresh=True)
                    # Keep data/processed/ (freshness cards, Dataset Preview) in sync
                    # with the fetch that just ran
                    _il.import_module("src.processor").fetch()
                set_refresh_results(lambda d, r=result, s=stage: {**d, s: r})
            except Exception as e:
                set_refresh_results(lambda d, s=stage, err=str(e): {**d, s: {"error": err}})
        return _handler

    refresh_results = get_refresh_results()

    def _make_section(stage, info):
        meta = read_meta(stage)
        ts = meta.get("fetched_at", "never") if meta else "never"
        count = meta.get("record_count", "—") if meta else "—"

        if info["placeholder"]:
            return info["label"], mo.vstack([
                mo.md(f"**Source:** [{info['source_url']}]({info['source_url']})"),
                mo.callout(mo.md("Not yet implemented — awaiting API access."), kind="warn"),
            ])

        # Show the outcome of the most recent in-session refresh for this stage
        last = refresh_results.get(stage)
        status_md = mo.md("")
        if last:
            if "error" in last:
                status_md = mo.callout(mo.md(f"Error: {last['error']}"), kind="danger")
            else:
                status_md = mo.callout(mo.md(f"✓ {last.get('record_count', '?')} records fetched"), kind="success")

        btn = mo.ui.button(label=f"Refresh {info['label']}", on_click=_refresh_fn(stage, info["label"]))

        body = mo.vstack([
            mo.md(
                f"**Source:** [{info['source_url']}]({info['source_url']})  \n"
                f"**Last updated:** {ts}  \n**Records:** {count}"
            ),
            btn,
            mo.md(
                f"Clicking this re-fetches **{info['label']}** from its source and "
                "updates the cached data — see the result in **Dataset Preview** above."
            ),
            status_md,
        ])
        return info["label"], body

    accordion_items = dict(_make_section(s, i) for s, i in STAGE_META.items())
    pipeline_section = mo.vstack([
        mo.md(
            "## Pipeline Stages\n"
            "One section per raw data source. **Refresh `<Source>`** re-fetches "
            "that source only, then rebuilds `data/processed/` for it; freshness "
            "shown here also drives the Dashboard cards above and the processed "
            "entries in Dataset Preview."
        ),
        mo.accordion(accordion_items),
    ])
    return (pipeline_section,)


@app.cell(hide_code=True)
def llm_section(
    conn_status,
    llm_api_key,
    llm_base_url,
    llm_model_live,
    mo,
    test_btn,
):
    # LLM configuration — configure any OpenAI-compatible endpoint for membership curation
    llm_section = mo.vstack([
        mo.md(
            "## LLM Configuration\n"
            "Configure any OpenAI-compatible endpoint here. This is only needed if "
            "you plan to use one of the **LLM Auto-update** buttons in Membership "
            "Curation below — everything else on this page works without it. "
            "Settings are session-only — add to `.env` to persist across restarts."
        ),
        llm_base_url,
        llm_api_key,
        llm_model_live,
        test_btn,
        mo.md(
            "Clicking **Test connection** checks the endpoint above and, on "
            "success, populates the Model dropdown with whatever models it reports."
        ),
        conn_status,
        mo.md(
            "**Provider examples:**\n"
            "- SURF WillMa: `https://willma.surf.nl/api/v0`\n"
            "- Anthropic: `https://api.anthropic.com/v1`\n"
            "- Ollama (local): `http://localhost:11434/v1`"
        ),
    ])
    return (llm_section,)


@app.cell(hide_code=True)
def membership_curation(
    CURATED_DIR,
    get_save_status,
    llm_api_key,
    llm_base_url,
    llm_model_live,
    mo,
    pd,
    set_save_status,
):
    # Membership curation — editable tables for each curated CSV file
    # Each section has a Save button (writes to disk) and an LLM button (suggests additions)
    MEMBERSHIP_SOURCES = {
        "surf_members.csv":     ("SURF Members",     "https://www.surf.nl/en/about/members-of-surf"),
        "ukb_members.csv":      ("UKB",              "https://ukb.nl/en/about-ukb/participating-members/"),
        "shb_members.csv":      ("SHB",              "https://www.shb-online.nl/directory/"),
        "unl_members.csv":      ("UNL",              "https://www.universiteitenvannederland.nl/wie-wij-zijn/onze-leden"),
        "umcnl_members.csv":    ("UMCNL",            "https://www.umcnl.nl/over-de-umcs/"),
        "vh_members.csv":       ("VH",               "https://www.vereniginghogescholen.nl/over-ons"),
        "knaw_institutes.csv":  ("KNAW Institutes",  "https://www.knaw.nl/en/academy-institutes"),
        "nwoi_institutes.csv":  ("NWO-i",            "https://www.nwo.nl/en/nwoi"),
        "openaire_members.csv": ("OpenAIRE Members", "https://www.openaire.eu/members"),
    }

    save_status = get_save_status()

    def _make_membership_section(csv_file, label, source_url):
        path = CURATED_DIR / csv_file
        df_cur = pd.read_csv(path) if path.exists() else pd.DataFrame(columns=["ror_id_url", "name"])
        editor = mo.ui.data_editor(df_cur, label=label)

        def _save_handler(_, _editor=editor, _path=path, _csv=csv_file):
            # Write the edited dataframe back to the curated CSV file on disk
            with mo.status.spinner(title="Saving…", remove_on_exit=False):
                _editor.value.to_csv(_path, index=False)
            set_save_status(lambda d, f=_csv: {**d, f: "saved"})

        def _llm_handler(_, _editor=editor, _path=path, _csv=csv_file, _url=source_url):
            # Ask the LLM to suggest additions to this membership list based on the source URL
            try:
                import io as _io
                import csv as _csv_mod
                from src.llm_curator import curate_csv as _curate_csv
                current = _path.read_text() if _path.exists() else ""
                with mo.status.spinner(title="Asking LLM to update membership list…", remove_on_exit=False):
                    updated = _curate_csv(_url, current, llm_base_url.value, llm_api_key.value, llm_model_live.value)
                # Validate the LLM output has the required columns before writing to disk
                reader = _csv_mod.DictReader(_io.StringIO(updated))
                fieldnames = reader.fieldnames or []
                if "ror_id_url" not in fieldnames or "name" not in fieldnames:
                    set_save_status(lambda d, f=_csv: {**d, f: "error: LLM output missing required columns"})
                else:
                    _path.write_text(updated)
                    set_save_status(lambda d, f=_csv: {**d, f: "llm-updated"})
            except Exception as e:
                set_save_status(lambda d, f=_csv, err=str(e): {**d, f: f"error: {err}"})

        last_status = save_status.get(csv_file, "")
        status_md = mo.md(f"*{last_status}*") if last_status else mo.md("")

        save_btn = mo.ui.button(label="Save changes", on_click=_save_handler)
        llm_btn = mo.ui.button(label=f"LLM Auto-update {label}", on_click=_llm_handler)

        return label, mo.vstack([
            mo.md(f"**Source:** [{source_url}]({source_url})"),
            editor,
            mo.hstack([save_btn, llm_btn]),
            status_md,
        ])

    sections = dict(
        _make_membership_section(f, lbl, url)
        for f, (lbl, url) in MEMBERSHIP_SOURCES.items()
    )
    membership_section = mo.vstack([
        mo.md(
            "## Membership Curation\n"
            "One editable table per curated membership CSV. Edit cells directly, "
            "then **Save changes** to write your edits back to the CSV on disk. "
            "**LLM Auto-update** asks the LLM configured above to compare the "
            "linked source URL against the current list and suggest additions, "
            "overwriting the CSV on success (requires LLM Configuration above)."
        ),
        mo.accordion(sections),
    ])
    return (membership_section,)


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
    _loader = PREVIEW_SOURCES.get(dataset_dropdown.value)
    if _loader is None:
        _table = mo.callout(mo.md("Not yet implemented — awaiting API access."), kind="warn")
    else:
        with mo.status.spinner(title=f"Loading {dataset_dropdown.value}…", remove_on_exit=True):
            _df = _loader()
        if _df is None:
            _table = mo.callout(
                mo.md(
                    "No data yet for this source — run its Refresh button in "
                    "**Pipeline Stages** below (or **Full Refresh**), which also "
                    "rebuilds `data/processed/` for this preview."
                ),
                kind="warn",
            )
        else:
            _table = mo.vstack([
                mo.md(f"{len(_df)} rows · {len(_df.columns)} columns"),
                mo.ui.table(_df),
            ])

    dataset_preview_section = mo.vstack([
        mo.md(
            "## Dataset Preview\n"
            "Pick any dataset to inspect it directly — the final assembled output, "
            "a processed pipeline source, or a curated membership list. Defaults to "
            "the assembled output. Every other view reads its `data/processed/` "
            "Parquet snapshot (see **Pipeline Stages** below), so the full dataset "
            "loads instantly regardless of source size."
        ),
        dataset_dropdown,
        _table,
    ])
    return (dataset_preview_section,)


@app.cell(hide_code=True)
def page(
    curate_data_intro,
    dashboard_header,
    dashboard_section,
    dataset_preview_section,
    full_refresh_btn,
    llm_section,
    membership_section,
    mo,
    pipeline_section,
    refresh_output,
):
    # Main layout — single scrolling page, no tabs
    page_ui = mo.vstack([
        dashboard_header,
        dashboard_section,
        dataset_preview_section,
        curate_data_intro,
        full_refresh_btn,
        refresh_output,
        llm_section,
        membership_section,
        pipeline_section,
    ])
    page_ui
    return


if __name__ == "__main__":
    app.run()
