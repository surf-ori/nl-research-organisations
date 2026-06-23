# /// script
# requires-python = ">=3.11"
# dependencies = ["marimo", "duckdb", "pandas", "pyarrow", "requests", "openpyxl", "openai", "python-dotenv"]
# ///
import marimo

__generated_with = "0.23.10"
app = marimo.App(width="wide")


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
    return datetime, json, mo, os, pd, Path, timezone


@app.cell(hide_code=True)
def shared_state(Path, json):
    # Shared constants — paths and per-stage metadata used throughout all tabs
    RAW_DIR = Path("data/raw")
    OUT_PARQUET = Path("data/nl_research_orgs.parquet")
    CURATED_DIR = Path("data/curated")

    # One entry per pipeline stage: display label, canonical source URL, and
    # whether the stage is a placeholder (not yet implemented)
    STAGE_META = {
        "ror":         {"label": "ROR",             "source_url": "https://api.ror.org/v2/organizations",           "placeholder": False},
        "zenodo":      {"label": "Zenodo Baseline", "source_url": "https://zenodo.org/records/18957154",            "placeholder": False},
        "openalex":    {"label": "OpenAlex",        "source_url": "https://api.openalex.org/institutions",          "placeholder": False},
        "openaire":    {"label": "OpenAIRE",        "source_url": "https://api.openaire.eu/graph/v1/organizations", "placeholder": False},
        "alei":        {"label": "ALEI / KVK",      "source_url": "https://developers.kvk.nl/documentation",        "placeholder": True},
        "pic":         {"label": "EU PIC",          "source_url": "https://ec.europa.eu/info/funding-tenders/",     "placeholder": True},
        "barcelona":   {"label": "Barcelona Decl.", "source_url": "https://barcelona-declaration.org",              "placeholder": False},
        "memberships": {"label": "Memberships",     "source_url": "data/curated/",                                  "placeholder": False},
        "nbn":         {"label": "NBN Prefixes",    "source_url": "https://www.kb.nl/.../nbn-catalogus",            "placeholder": False},
        "assembler":   {"label": "Assembly",        "source_url": "data/nl_research_orgs.parquet",                  "placeholder": False},
    }

    def read_meta(stage: str) -> dict | None:
        # Read the cached _metadata.json for a pipeline stage; returns None if not yet run
        p = RAW_DIR / stage / "_metadata.json"
        if p.exists():
            return json.loads(p.read_text())
        # The assembler writes its metadata one level up
        if stage == "assembler":
            p2 = RAW_DIR / "_assembly_metadata.json"
            if p2.exists():
                return json.loads(p2.read_text())
        return None

    return CURATED_DIR, OUT_PARQUET, RAW_DIR, STAGE_META, read_meta


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
def llm_test_result(mo, llm_base_url, llm_api_key, llm_model, test_btn):
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
def llm_model_live(mo, llm_model, model_ids, os):
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


# ── Dashboard ──────────────────────────────────────────────────────────────────


@app.cell(hide_code=True)
def dashboard(mo, pd, datetime, timezone, OUT_PARQUET, STAGE_META, read_meta):
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

    full_refresh_btn = mo.ui.button(label="Full Refresh", kind="success")
    dashboard_tab = mo.vstack([
        mo.md(f"# NL Research Organisations\nTotal organisations in output: **{total}**"),
        mo.hstack(cards, wrap=True),
        full_refresh_btn,
    ])
    return dashboard_tab, full_refresh_btn, freshness_badge


@app.cell(hide_code=True)
def full_refresh(mo, full_refresh_btn):
    # Full pipeline refresh — runs all stages in dependency order; shows progress bar while running
    if full_refresh_btn.value:
        import importlib
        log_lines = []
        _stages = [
            "src.ror_fetcher", "src.zenodo_baseline", "src.openalex", "src.openaire",
            "src.alei_fetcher", "src.pic_fetcher", "src.barcelona", "src.memberships", "src.nbn_fetcher", "src.assembler",
        ]
        for _mod in mo.status.progress_bar(
            _stages, title="Full Refresh", subtitle="Running all pipeline stages…", remove_on_exit=False,
        ):
            try:
                m = importlib.import_module(_mod)
                # openalex and openaire need the ROR URL list as input
                if _mod in ("src.openalex", "src.openaire"):
                    rf = importlib.import_module("src.ror_fetcher")
                    ror_urls = [o["ror_id_url"] for o in rf.load_orgs()]
                    r = m.fetch(ror_urls, force_refresh=True)
                else:
                    r = m.fetch(force_refresh=True)
                log_lines.append(f"✓ {_mod.split('.')[-1]}: {r.get('record_count', '?')} records")
            except Exception as e:
                log_lines.append(f"✗ {_mod.split('.')[-1]}: {e}")
        refresh_output = mo.callout(mo.md("\n".join(log_lines)), kind="info")
    else:
        refresh_output = mo.md("")
    return (refresh_output,)


# ── Pipeline Stages ────────────────────────────────────────────────────────────


@app.cell(hide_code=True)
def pipeline_stages(mo, pd, STAGE_META, read_meta, get_refresh_results, set_refresh_results):
    # Pipeline stages — accordion with one collapsible section per data source
    import importlib as _il

    _STAGE_MODULES = {
        "ror": "src.ror_fetcher", "zenodo": "src.zenodo_baseline",
        "alei": "src.alei_fetcher", "pic": "src.pic_fetcher",
        "nbn": "src.nbn_fetcher",
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
                    else:
                        result = m.fetch(force_refresh=True)
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

        # ROR only: show the first 10 cached rows as a preview without hitting the network
        preview = mo.md("")
        if stage == "ror":
            try:
                m = _il.import_module("src.ror_fetcher")
                rows = m.load_orgs()[:10]
                preview = mo.ui.table(pd.DataFrame(rows)) if rows else mo.md("No data cached yet.")
            except Exception:
                preview = mo.md("Run Refresh to load data.")

        body = mo.vstack([
            mo.md(
                f"**Source:** [{info['source_url']}]({info['source_url']})  \n"
                f"**Last updated:** {ts}  \n**Records:** {count}"
            ),
            btn,
            status_md,
            preview,
        ])
        return info["label"], body

    accordion_items = dict(_make_section(s, i) for s, i in STAGE_META.items())
    pipeline_tab = mo.accordion(accordion_items)
    return (pipeline_tab,)


# ── LLM Configuration ──────────────────────────────────────────────────────────


@app.cell(hide_code=True)
def llm_tab(mo, llm_base_url, llm_api_key, llm_model_live, test_btn, conn_status):
    # LLM configuration tab — configure any OpenAI-compatible endpoint for membership curation
    llm_tab = mo.vstack([
        mo.md(
            "## LLM Configuration\n"
            "Configure any OpenAI-compatible endpoint. Settings are session-only — "
            "add to `.env` to persist."
        ),
        llm_base_url,
        llm_api_key,
        llm_model_live,
        test_btn,
        conn_status,
        mo.md(
            "**Provider examples:**\n"
            "- SURF WillMa: `https://willma.surf.nl/api/v0`\n"
            "- Anthropic: `https://api.anthropic.com/v1`\n"
            "- Ollama (local): `http://localhost:11434/v1`"
        ),
    ])
    return (llm_tab,)


# ── Membership Curation ────────────────────────────────────────────────────────


@app.cell(hide_code=True)
def membership_curation(
    mo, pd, CURATED_DIR, llm_base_url, llm_api_key, llm_model_live,
    get_save_status, set_save_status,
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
    membership_tab = mo.accordion(sections)
    return (membership_tab,)


# ── Output Preview ─────────────────────────────────────────────────────────────


@app.cell(hide_code=True)
def output_preview(mo, pd, OUT_PARQUET):
    # Output preview — interactive sortable/filterable table of the assembled parquet
    if OUT_PARQUET.exists():
        df_out = pd.read_parquet(OUT_PARQUET)
        output_tab = mo.vstack([
            mo.md(
                f"## Output: `{OUT_PARQUET}`\n"
                f"{len(df_out)} organisations · {len(df_out.columns)} columns"
            ),
            mo.ui.table(df_out),
        ])
    else:
        output_tab = mo.callout(
            mo.md("No output file yet. Run **Full Refresh** from the Dashboard tab."),
            kind="warn",
        )
    return (output_tab,)


# ── Tabs ──────────────────────────────────────────────────────────────────────


@app.cell(hide_code=True)
def tabs(mo, dashboard_tab, refresh_output, pipeline_tab, llm_tab, membership_tab, output_tab):
    # Main layout — compose all five panels into a tabbed notebook interface
    tabs_ui = mo.ui.tabs({
        "Dashboard":           mo.vstack([dashboard_tab, refresh_output]),
        "Pipeline Stages":     pipeline_tab,
        "LLM Configuration":   llm_tab,
        "Membership Curation": membership_tab,
        "Output Preview":      output_tab,
    })
    tabs_ui
    return


if __name__ == "__main__":
    app.run()
