# /// script
# requires-python = ">=3.11"
# dependencies = ["marimo", "duckdb", "pandas", "pyarrow", "requests", "openpyxl", "openai", "python-dotenv"]
# ///
import marimo as mo

__generated_with = "0.13.0"
app = mo.App(width="wide")


@app.cell
def _():
    import marimo as mo
    import os
    import json
    import pandas as pd
    from pathlib import Path
    from datetime import datetime, timezone
    from dotenv import load_dotenv
    load_dotenv()
    return datetime, json, mo, os, pd, Path, timezone


# ── shared state ──────────────────────────────────────────────────────────────

@app.cell
def _(Path, json):
    RAW_DIR = Path("data/raw")
    OUT_PARQUET = Path("data/nl_research_orgs.parquet")
    CURATED_DIR = Path("data/curated")

    STAGE_META = {
        "ror":         {"label": "ROR",                "source_url": "https://api.ror.org/v2/organizations", "placeholder": False},
        "zenodo":      {"label": "Zenodo Baseline",    "source_url": "https://zenodo.org/records/18957154", "placeholder": False},
        "openalex":    {"label": "OpenAlex",           "source_url": "https://api.openalex.org/institutions", "placeholder": False},
        "openaire":    {"label": "OpenAIRE",           "source_url": "https://api.openaire.eu/graph/v1/organizations", "placeholder": False},
        "alei":        {"label": "ALEI / KVK",         "source_url": "https://developers.kvk.nl/documentation", "placeholder": True},
        "pic":         {"label": "EU PIC",             "source_url": "https://ec.europa.eu/info/funding-tenders/", "placeholder": True},
        "barcelona":   {"label": "Barcelona Decl.",    "source_url": "https://barcelona-declaration.org", "placeholder": False},
        "memberships": {"label": "Memberships",        "source_url": "data/curated/", "placeholder": False},
        "assembler":   {"label": "Assembly",           "source_url": "data/nl_research_orgs.parquet", "placeholder": False},
    }

    def read_meta(stage: str) -> dict | None:
        p = RAW_DIR / stage / "_metadata.json"
        if p.exists():
            return json.loads(p.read_text())
        if stage == "assembler":
            p2 = RAW_DIR / "_assembly_metadata.json"
            if p2.exists():
                return json.loads(p2.read_text())
        return None

    return CURATED_DIR, OUT_PARQUET, RAW_DIR, STAGE_META, read_meta


# ── LLM config state (session-level) ─────────────────────────────────────────

@app.cell
def _(mo, os):
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


# ── LLM: test connection result ───────────────────────────────────────────────

@app.cell
def _(llm_api_key, llm_base_url, llm_model, mo, test_btn):
    test_btn  # reactive dependency
    conn_result = mo.state(None)

    if test_btn.value:
        from src.llm_curator import test_connection, fetch_models
        ok, msg = test_connection(llm_base_url.value, llm_api_key.value, llm_model.value)
        conn_status = mo.callout(mo.md(f"{'✓' if ok else '✗'} {msg}"), kind="success" if ok else "danger")
        model_ids = fetch_models(llm_base_url.value, llm_api_key.value)
    else:
        conn_status = mo.md("")
        model_ids = None
    return conn_status, model_ids


# ── LLM model dropdown update ─────────────────────────────────────────────────

@app.cell
def _(llm_model, mo, model_ids, os):
    options = model_ids if model_ids else llm_model.options
    llm_model_live = mo.ui.dropdown(
        options=options,
        value=os.getenv("LLM_MODEL", options[0] if options else ""),
        label="Model",
    )
    return (llm_model_live,)


# ── Tab 1: Dashboard ──────────────────────────────────────────────────────────

@app.cell
def _(OUT_PARQUET, STAGE_META, mo, pd, read_meta):
    from datetime import datetime, timezone

    def freshness_badge(fetched_at: str | None) -> str:
        if not fetched_at:
            return "🔴 no data"
        try:
            dt = datetime.fromisoformat(fetched_at.replace("Z", "+00:00"))
            age_days = (datetime.now(timezone.utc) - dt).days
            if age_days < 7:
                return f"🟢 {age_days}d ago"
            elif age_days < 30:
                return f"🟡 {age_days}d ago"
            else:
                return f"🔴 {age_days}d ago"
        except Exception:
            return "🔴 unknown"

    cards = []
    for stage, info in STAGE_META.items():
        meta = read_meta(stage)
        badge = freshness_badge(meta.get("fetched_at") if meta else None)
        count = meta.get("record_count", "—") if meta else "—"
        ts = meta.get("fetched_at", "never") if meta else "never"
        label = "⚠️ placeholder" if info["placeholder"] else badge
        cards.append(mo.stat(
            label=info["label"],
            value=str(count),
            caption=f"{label} · {ts[:19] if ts != 'never' else 'never'}",
        ))

    total = "—"
    if OUT_PARQUET.exists():
        try:
            total = len(pd.read_parquet(OUT_PARQUET))
        except Exception:
            pass

    full_refresh_btn = mo.ui.button(label="⟳ Full Refresh", kind="success")
    dashboard_tab = mo.vstack([
        mo.md(f"# NL Research Organisations\nTotal organisations in output: **{total}**"),
        mo.hstack(cards, wrap=True),
        full_refresh_btn,
    ])
    return dashboard_tab, full_refresh_btn, freshness_badge


# ── Full refresh action ───────────────────────────────────────────────────────

@app.cell
def _(full_refresh_btn, mo):
    full_refresh_btn  # dependency
    refresh_log = mo.state("")
    if full_refresh_btn.value:
        import importlib
        log_lines = []
        for stage_mod in ["src.ror_fetcher","src.zenodo_baseline","src.openalex","src.openaire",
                          "src.alei_fetcher","src.pic_fetcher","src.barcelona","src.memberships","src.assembler"]:
            try:
                m = importlib.import_module(stage_mod)
                if stage_mod in ("src.openalex","src.openaire"):
                    rf = importlib.import_module("src.ror_fetcher")
                    orgs = rf.load_orgs()
                    r = m.fetch([o["ror_id_url"] for o in orgs], force_refresh=True)
                else:
                    r = m.fetch(force_refresh=True)
                log_lines.append(f"✓ {stage_mod.split('.')[-1]}: {r.get('record_count','?')} records")
            except Exception as e:
                log_lines.append(f"✗ {stage_mod.split('.')[-1]}: {e}")
        refresh_output = mo.callout(mo.md("\n".join(log_lines)), kind="info")
    else:
        refresh_output = mo.md("")
    return (refresh_output,)


# ── Tab 2: Pipeline Stages ────────────────────────────────────────────────────

@app.cell
def _(STAGE_META, mo, pd, read_meta):
    import importlib

    def make_stage_section(stage: str, info: dict):
        meta = read_meta(stage)
        ts = meta.get("fetched_at", "never") if meta else "never"
        count = meta.get("record_count", "—") if meta else "—"

        if info["placeholder"]:
            body = mo.vstack([
                mo.md(f"**Source:** [{info['source_url']}]({info['source_url']})"),
                mo.callout(mo.md("Not yet implemented — awaiting API access."), kind="warn"),
            ])
        else:
            refresh_stage_btn = mo.ui.button(label=f"Refresh {info['label']}")

            preview = mo.md("")
            try:
                if stage == "ror":
                    m = importlib.import_module("src.ror_fetcher")
                    rows = m.load_orgs()[:10]
                    preview = mo.ui.table(pd.DataFrame(rows)) if rows else mo.md("No data cached yet.")
            except Exception:
                preview = mo.md("Run refresh to load data.")

            body = mo.vstack([
                mo.md(f"**Source:** [{info['source_url']}]({info['source_url']})  \n**Last updated:** {ts}  \n**Records:** {count}"),
                refresh_stage_btn,
                preview,
            ])
        return (info["label"], body)

    accordion_items = {label: body for label, body in [make_stage_section(s, i) for s, i in STAGE_META.items()]}
    pipeline_tab = mo.ui.accordion(accordion_items)
    return (pipeline_tab,)


# ── Tab 3: LLM Configuration ──────────────────────────────────────────────────

@app.cell
def _(conn_status, llm_api_key, llm_base_url, llm_model_live, mo, test_btn):
    llm_tab = mo.vstack([
        mo.md("## LLM Configuration\nConfigure any OpenAI-compatible endpoint. Settings are session-only — add to `.env` to persist."),
        llm_base_url,
        llm_api_key,
        llm_model_live,
        test_btn,
        conn_status,
        mo.md("**Examples:**\n- SURF WillMa: `https://willma.surf.nl/api/v0`\n- Anthropic: `https://api.anthropic.com/v1`\n- Ollama: `http://localhost:11434/v1`"),
    ])
    return (llm_tab,)


# ── Tab 4: Membership Curation ────────────────────────────────────────────────

@app.cell
def _(CURATED_DIR, llm_api_key, llm_base_url, llm_model_live, mo, pd):
    import difflib as _difflib

    MEMBERSHIP_SOURCES = {
        "surf_members.csv":    ("SURF Members", "https://www.surf.nl/en/about/members-of-surf"),
        "ukb_members.csv":     ("UKB", "https://ukb.nl/en/about-ukb/participating-members/"),
        "shb_members.csv":     ("SHB", "https://www.shb-online.nl/directory/"),
        "unl_members.csv":     ("UNL", "https://www.universiteitenvannederland.nl/wie-wij-zijn/onze-leden"),
        "umcnl_members.csv":   ("UMCNL", "https://www.umcnl.nl/over-de-umcs/"),
        "vh_members.csv":      ("VH", "https://www.vereniginghogescholen.nl/over-ons"),
        "knaw_institutes.csv": ("KNAW Institutes", "https://www.knaw.nl/en/academy-institutes"),
        "nwoi_institutes.csv": ("NWO-i", "https://www.nwo.nl/en/nwoi"),
        "openaire_members.csv":("OpenAIRE Members", "https://www.openaire.eu/members"),
    }

    sections = {}
    for csv_file, (label, source_url) in MEMBERSHIP_SOURCES.items():
        path = CURATED_DIR / csv_file
        df_cur = pd.read_csv(path) if path.exists() else pd.DataFrame(columns=["ror_id_url", "name"])
        editor = mo.ui.data_editor(df_cur, label=label)
        llm_btn = mo.ui.button(label=f"LLM Auto-update {label}")
        save_btn = mo.ui.button(label="Save changes")
        sections[label] = mo.vstack([
            mo.md(f"**Source:** [{source_url}]({source_url})"),
            editor,
            mo.hstack([save_btn, llm_btn]),
        ])

    membership_tab = mo.ui.accordion(sections)
    return (membership_tab,)


# ── Tab 5: Output Preview ─────────────────────────────────────────────────────

@app.cell
def _(OUT_PARQUET, mo, pd):
    if OUT_PARQUET.exists():
        df_out = pd.read_parquet(OUT_PARQUET)
        output_tab = mo.vstack([
            mo.md(f"## Output: `{OUT_PARQUET}`\n{len(df_out)} organisations · {len(df_out.columns)} columns"),
            mo.ui.table(df_out),
        ])
    else:
        output_tab = mo.callout(mo.md("No output file yet. Run **Full Refresh** from the Dashboard tab."), kind="warn")
    return (output_tab,)


# ── Assemble tabs ─────────────────────────────────────────────────────────────

@app.cell
def _(dashboard_tab, llm_tab, membership_tab, mo, output_tab, pipeline_tab, refresh_output):
    mo.ui.tabs({
        "Dashboard": mo.vstack([dashboard_tab, refresh_output]),
        "Pipeline Stages": pipeline_tab,
        "LLM Configuration": llm_tab,
        "Membership Curation": membership_tab,
        "Output Preview": output_tab,
    })
    return


if __name__ == "__main__":
    app.run()
