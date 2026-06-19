# /// script
# requires-python = ">=3.11"
# dependencies = ["marimo", "duckdb", "pandas", "pyarrow", "requests", "openpyxl", "openai", "python-dotenv"]
# ///
import marimo

__generated_with = "0.13.0"
app = marimo.App(width="wide")


@app.cell
def _imports():
    """Load all standard library and third-party imports, load .env"""
    import marimo as mo
    import os
    import json
    import pandas as pd
    from pathlib import Path
    from datetime import datetime, timezone
    from dotenv import load_dotenv
    load_dotenv()
    return datetime, json, mo, os, pd, Path, timezone


@app.cell
def _shared_state(Path, json):
    """Define shared paths and stage metadata used across all tabs"""
    RAW_DIR = Path("data/raw")
    OUT_PARQUET = Path("data/nl_research_orgs.parquet")
    CURATED_DIR = Path("data/curated")

    STAGE_META = {
        "ror":         {"label": "ROR",             "source_url": "https://api.ror.org/v2/organizations",          "placeholder": False},
        "zenodo":      {"label": "Zenodo Baseline", "source_url": "https://zenodo.org/records/18957154",           "placeholder": False},
        "openalex":    {"label": "OpenAlex",        "source_url": "https://api.openalex.org/institutions",         "placeholder": False},
        "openaire":    {"label": "OpenAIRE",        "source_url": "https://api.openaire.eu/graph/v1/organizations","placeholder": False},
        "alei":        {"label": "ALEI / KVK",      "source_url": "https://developers.kvk.nl/documentation",       "placeholder": True},
        "pic":         {"label": "EU PIC",          "source_url": "https://ec.europa.eu/info/funding-tenders/",    "placeholder": True},
        "barcelona":   {"label": "Barcelona Decl.", "source_url": "https://barcelona-declaration.org",             "placeholder": False},
        "memberships": {"label": "Memberships",     "source_url": "data/curated/",                                 "placeholder": False},
        "assembler":   {"label": "Assembly",        "source_url": "data/nl_research_orgs.parquet",                 "placeholder": False},
    }

    def read_meta(stage: str) -> dict | None:
        """Read cached metadata JSON for a pipeline stage, or None if absent."""
        p = RAW_DIR / stage / "_metadata.json"
        if p.exists():
            return json.loads(p.read_text())
        if stage == "assembler":
            p2 = RAW_DIR / "_assembly_metadata.json"
            if p2.exists():
                return json.loads(p2.read_text())
        return None

    return CURATED_DIR, OUT_PARQUET, RAW_DIR, STAGE_META, read_meta


@app.cell
def _refresh_state(mo):
    """Accumulated state for per-stage refresh results — updated via on_click callbacks."""
    get_refresh_results, set_refresh_results = mo.state({})
    return get_refresh_results, set_refresh_results


@app.cell
def _save_state(mo):
    """Accumulated state for membership CSV save results — updated via on_click callbacks."""
    get_save_status, set_save_status = mo.state({})
    return get_save_status, set_save_status


@app.cell
def _llm_config(mo, os):
    """LLM endpoint configuration widgets — reads defaults from .env, session-only unless persisted."""
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


@app.cell
def _llm_test_result(mo, llm_base_url, llm_api_key, llm_model, test_btn):
    """Run connection test when button is clicked; fetch available models for dropdown update."""
    _ = test_btn.value  # reactive trigger
    if test_btn.value:
        from src.llm_curator import test_connection, fetch_models
        ok, msg = test_connection(llm_base_url.value, llm_api_key.value, llm_model.value)
        conn_status = mo.callout(mo.md(f"{'✓' if ok else '✗'} {msg}"), kind="success" if ok else "danger")
        model_ids = fetch_models(llm_base_url.value, llm_api_key.value)
    else:
        conn_status = mo.md("")
        model_ids = None
    return conn_status, model_ids


@app.cell
def _llm_model_live(mo, llm_model, model_ids, os):
    """Update model dropdown with live model list after a successful connection test."""
    options = model_ids if model_ids else llm_model.options
    llm_model_live = mo.ui.dropdown(
        options=options,
        value=os.getenv("LLM_MODEL", options[0] if options else ""),
        label="Model",
    )
    return (llm_model_live,)


# ── Dashboard ──────────────────────────────────────────────────────────────────

@app.cell
def _dashboard(mo, pd, datetime, timezone, OUT_PARQUET, STAGE_META, read_meta):
    """
    Tab 1 - Dashboard
    Shows a freshness card for each pipeline stage and the total org count from the
    assembled parquet. Green/yellow/red badges indicate data age.
    """
    def freshness_badge(fetched_at: str | None) -> str:
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


@app.cell
def _full_refresh(mo, full_refresh_btn):
    """Run all pipeline stages in order when Full Refresh is clicked."""
    _ = full_refresh_btn.value  # reactive trigger
    if full_refresh_btn.value:
        import importlib
        log_lines = []
        for _mod in ["src.ror_fetcher", "src.zenodo_baseline", "src.openalex", "src.openaire",
                     "src.alei_fetcher", "src.pic_fetcher", "src.barcelona", "src.memberships", "src.assembler"]:
            try:
                m = importlib.import_module(_mod)
                if _mod in ("src.openalex", "src.openaire"):
                    rf = importlib.import_module("src.ror_fetcher")
                    ror_urls = [o["ror_id_url"] for o in rf.load_orgs()]
                    r = m.fetch(ror_urls, force_refresh=True)
                else:
                    r = m.fetch(force_refresh=True)
                log_lines.append(f"OK {_mod.split('.')[-1]}: {r.get('record_count', '?')} records")
            except Exception as e:
                log_lines.append(f"FAIL {_mod.split('.')[-1]}: {e}")
        refresh_output = mo.callout(mo.md("\n".join(log_lines)), kind="info")
    else:
        refresh_output = mo.md("")
    return (refresh_output,)


# ── Pipeline Stages ────────────────────────────────────────────────────────────

@app.cell
def _pipeline_stages(mo, pd, STAGE_META, read_meta, get_refresh_results, set_refresh_results):
    """
    Tab 2 - Pipeline Stages
    Accordion with one section per data source. Each section shows last-updated metadata,
    a Refresh button (wired via on_click -> mo.state), and a 10-row preview for ROR.
    Placeholder stages show a warning callout instead.
    """
    import importlib as _il

    def _refresh_fn(stage):
        """Return an on_click handler that fetches the given stage and stores the result in state."""
        def _handler(_):
            try:
                m = _il.import_module(f"src.{stage}")
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

        # Show last refresh result if available
        last = refresh_results.get(stage)
        status_md = mo.md("")
        if last:
            if "error" in last:
                status_md = mo.callout(mo.md(f"Error: {last['error']}"), kind="danger")
            else:
                status_md = mo.callout(mo.md(f"OK: {last.get('record_count', '?')} records fetched"), kind="success")

        btn = mo.ui.button(label=f"Refresh {info['label']}", on_click=_refresh_fn(stage))

        # ROR-only live preview (first 10 rows)
        preview = mo.md("")
        if stage == "ror":
            try:
                m = _il.import_module("src.ror_fetcher")
                rows = m.load_orgs()[:10]
                preview = mo.ui.table(pd.DataFrame(rows)) if rows else mo.md("No data cached yet.")
            except Exception:
                preview = mo.md("Run Refresh to load data.")

        body = mo.vstack([
            mo.md(f"**Source:** [{info['source_url']}]({info['source_url']})  \n"
                  f"**Last updated:** {ts}  \n**Records:** {count}"),
            btn,
            status_md,
            preview,
        ])
        return info["label"], body

    accordion_items = dict(_make_section(s, i) for s, i in STAGE_META.items())
    pipeline_tab = mo.ui.accordion(accordion_items)
    return (pipeline_tab,)


# ── LLM Configuration ──────────────────────────────────────────────────────────

@app.cell
def _llm_tab(mo, llm_base_url, llm_api_key, llm_model_live, test_btn, conn_status):
    """
    Tab 3 - LLM Configuration
    Configure any OpenAI-compatible endpoint. The model dropdown updates dynamically
    after a successful test. Settings are session-only unless saved to .env.
    """
    llm_tab = mo.vstack([
        mo.md("## LLM Configuration\n"
              "Configure any OpenAI-compatible endpoint. Settings are session-only — "
              "add to `.env` to persist."),
        llm_base_url,
        llm_api_key,
        llm_model_live,
        test_btn,
        conn_status,
        mo.md("**Provider examples:**\n"
              "- SURF WillMa: `https://willma.surf.nl/api/v0`\n"
              "- Anthropic: `https://api.anthropic.com/v1`\n"
              "- Ollama (local): `http://localhost:11434/v1`"),
    ])
    return (llm_tab,)


# ── Membership Curation ────────────────────────────────────────────────────────

@app.cell
def _membership_curation(mo, pd, CURATED_DIR, llm_base_url, llm_api_key, llm_model_live,
                          get_save_status, set_save_status):
    """
    Tab 4 - Membership Curation
    Editable tables for each curated membership CSV. Save writes the edited dataframe
    back to disk. LLM Auto-update calls the curate_csv function to suggest additions
    based on the source URL.
    """
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
            """Write edited dataframe back to the curated CSV file."""
            _editor.value.to_csv(_path, index=False)
            set_save_status(lambda d, f=_csv: {**d, f: "saved"})

        def _llm_handler(_, _editor=editor, _path=path, _csv=csv_file, _url=source_url):
            """Ask the configured LLM to suggest updates to this membership list."""
            try:
                import io as _io
                import csv as _csv_mod
                from src.llm_curator import curate_csv as _curate_csv
                current = _path.read_text() if _path.exists() else ""
                updated = _curate_csv(_url, current, llm_base_url.value, llm_api_key.value, llm_model_live.value)
                # Validate the LLM output parses as CSV with required columns before writing
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
    membership_tab = mo.ui.accordion(sections)
    return (membership_tab,)


# ── Output Preview ─────────────────────────────────────────────────────────────

@app.cell
def _output_preview(mo, pd, OUT_PARQUET):
    """
    Tab 5 - Output Preview
    Loads the assembled parquet and shows it in marimo's interactive table (sortable,
    filterable, paginated out of the box). Prompts to run Full Refresh if file absent.
    """
    if OUT_PARQUET.exists():
        df_out = pd.read_parquet(OUT_PARQUET)
        output_tab = mo.vstack([
            mo.md(f"## Output: `{OUT_PARQUET}`\n"
                  f"{len(df_out)} organisations · {len(df_out.columns)} columns"),
            mo.ui.table(df_out),
        ])
    else:
        output_tab = mo.callout(
            mo.md("No output file yet. Run **Full Refresh** from the Dashboard tab."),
            kind="warn",
        )
    return (output_tab,)


# ── Assemble tabs ──────────────────────────────────────────────────────────────

@app.cell
def _tabs(mo, dashboard_tab, refresh_output, pipeline_tab, llm_tab, membership_tab, output_tab):
    """Compose all five tabs into the final notebook UI."""
    mo.ui.tabs({
        "Dashboard":           mo.vstack([dashboard_tab, refresh_output]),
        "Pipeline Stages":     pipeline_tab,
        "LLM Configuration":   llm_tab,
        "Membership Curation": membership_tab,
        "Output Preview":      output_tab,
    })
    return


if __name__ == "__main__":
    app.run()
