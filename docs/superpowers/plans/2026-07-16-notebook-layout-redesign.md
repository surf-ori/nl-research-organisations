# Notebook Layout Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `notebook.py`'s 5-tab layout with a single scrolling page (no `mo.ui.tabs` anywhere), add a SURF logo + explanatory copy to the Dashboard, add a comprehensive dataset-preview dropdown, and add a "Curate Data" section (with Full Refresh moved into it) ahead of LLM Configuration / Membership Curation / Pipeline Stages.

**Architecture:** `notebook.py` stays a marimo notebook (one `@app.cell`-decorated function per reactive unit; marimo resolves the dependency graph from parameter names and return-tuple names — cell *function* names are not semantically significant, only params/returns are). Each task keeps the file in a fully loadable state, verified by running the notebook headlessly via `marimo export html`.

**Tech Stack:** marimo 0.23.10, pandas, duckdb (already a project dependency, unused directly by this change), existing `src/*.py` fetcher modules (untouched).

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-16-notebook-layout-redesign-design.md` — every requirement there must map to a task below.
- No changes to `src/*.py` fetch/save logic or to `pipeline.py` (the headless CLI). This is a `notebook.py` layout + copy pass, plus one new static asset.
- No `mo.ui.tabs` anywhere in the final file. Sections are plain headings stacked with `mo.vstack`.
- Keep `mo.accordion` for Pipeline Stages (10 items) and Membership Curation (9 items) — accordions are not tabs.
- After **every** task, run `marimo export html notebook.py -o /tmp/claude-1000/nb_check.html -f` and confirm exit code 0 with no traceback in the output. This is the primary correctness gate — marimo statically resolves cross-cell variable names, and a mismatch (wrong param name, stale return tuple) fails loudly here.
- This repo has **no existing tests for `notebook.py`** (only `src/*.py` modules are covered under `tests/`). Follow that precedent — do not invent new pytest files for marimo cell bodies. Do run the existing suite (`pytest tests/ -q`) once at the end to confirm no `src/*.py` regressions.
- Raw per-organisation JSON sources (OpenAlex, OpenAIRE) contain ~1700+ tiny files each; parsing all of them takes 2+ minutes (measured). Cap these two preview loaders at the first 300 files (sorted, deterministic) so the dropdown stays responsive — same "small sample, not everything" precedent the old ROR-only preview already used (it showed only the first 10 rows).
- Follow this repo's established ship pattern: feature branch → commits as you go → push → `gh pr create` → squash merge into `master` → `git checkout master && git pull --ff-only`.

---

### Task 1: SURF logo asset + `LOGO_PATH` constant

**Files:**
- Create: `assets/surf-logo.svg`
- Modify: `notebook.py:25-59` (`shared_state` cell)

**Interfaces:**
- Produces: `LOGO_PATH: Path` — added to `shared_state`'s return tuple, consumed by Task 2's `dashboard_header` cell.

- [ ] **Step 1: Fetch the logo and save it locally**

```bash
mkdir -p assets
curl -sL -o assets/surf-logo.svg https://www.surf.nl/themes/surf/logo.svg
```

- [ ] **Step 2: Verify it's a real SVG, not an error page**

```bash
head -c 200 assets/surf-logo.svg
file assets/surf-logo.svg
```

Expected: output contains `<svg` or `<?xml` near the start, and `file` reports SVG/XML, not HTML.

- [ ] **Step 3: Add `LOGO_PATH` to `shared_state`**

In `notebook.py`, the `shared_state` cell currently reads (lines 25-59):

```python
@app.cell(hide_code=True)
def shared_state(Path, json):
    # Shared constants — paths and per-stage metadata used throughout all tabs
    RAW_DIR = Path("data/raw")
    OUT_PARQUET = Path("data/nl_research_orgs.parquet")
    CURATED_DIR = Path("data/curated")
```

Change the comment (no longer "tabs") and add `LOGO_PATH`, and update the return line at the end of the same cell:

```python
@app.cell(hide_code=True)
def shared_state(Path, json):
    # Shared constants — paths and per-stage metadata used throughout the notebook
    RAW_DIR = Path("data/raw")
    OUT_PARQUET = Path("data/nl_research_orgs.parquet")
    CURATED_DIR = Path("data/curated")
    LOGO_PATH = Path("assets/surf-logo.svg")
```

...and change the final `return` line of this cell from:

```python
    return CURATED_DIR, OUT_PARQUET, RAW_DIR, STAGE_META, read_meta
```

to:

```python
    return CURATED_DIR, LOGO_PATH, OUT_PARQUET, RAW_DIR, STAGE_META, read_meta
```

(Everything else in this cell — `STAGE_META`, `read_meta` — is unchanged.)

- [ ] **Step 4: Verify the notebook still loads**

```bash
marimo export html notebook.py -o /tmp/claude-1000/nb_check.html -f
echo "exit: $?"
```

Expected: `exit: 0`, no traceback printed.

- [ ] **Step 5: Commit**

```bash
git add assets/surf-logo.svg notebook.py
git commit -m "feat: add SURF logo asset and LOGO_PATH constant"
```

---

### Task 2: Replace `dashboard` with `dashboard_header` + `dashboard_section`; move Full Refresh button out; introduce the no-tabs `page` cell

This is the task that removes `mo.ui.tabs` entirely. To keep the file loadable, every section that doesn't have its final content yet (LLM/Membership/Pipeline/Output) is referenced by its **current** cell/variable name in `page`, and gets swapped out one at a time in later tasks.

**Files:**
- Modify: `notebook.py:133-179` (`dashboard` cell) — split into `dashboard_header` and `dashboard_section`
- Modify: `notebook.py:423-434` (`tabs` cell) — replaced by `page`

**Interfaces:**
- Consumes (from `shared_state`, unchanged): `Path, json` → `CURATED_DIR, LOGO_PATH, OUT_PARQUET, RAW_DIR, STAGE_META, read_meta`
- Produces: `dashboard_header: Html`, `dashboard_section: Html`, `full_refresh_btn: mo.ui.button` (now built in its own cell) — all consumed by `page`.

- [ ] **Step 1: Replace the `dashboard` cell**

Replace the whole cell at `notebook.py:133-179`:

```python
@app.cell(hide_code=True)
def dashboard_header(mo, LOGO_PATH):
    # Dashboard header — title + intro, with the SURF logo top right
    dashboard_header = mo.hstack(
        [
            mo.md(
                "# NL Research Organisations\n"
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
def dashboard_section(mo, pd, datetime, timezone, OUT_PARQUET, STAGE_META, read_meta):
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
            "where it gets fetched for further processing."
        ),
        mo.hstack(cards, wrap=True),
    ])
    return (dashboard_section,)


@app.cell(hide_code=True)
def full_refresh_button(mo):
    # Full Refresh button — lives in the Curate Data section below; see its explanation there
    full_refresh_btn = mo.ui.button(label="Full Refresh", kind="success")
    return (full_refresh_btn,)
```

Note: the `full_refresh` cell (currently `notebook.py:182-210`) is **unchanged** — it already takes `full_refresh_btn` as a parameter, and marimo resolves that from whichever cell now defines it. Leave it exactly as-is.

- [ ] **Step 2: Replace the `tabs` cell with `page`**

Replace the whole cell at `notebook.py:423-434`:

```python
@app.cell(hide_code=True)
def page(
    mo, dashboard_header, dashboard_section, full_refresh_btn, refresh_output,
    pipeline_tab, llm_tab, membership_tab, output_tab,
):
    # Main layout — single scrolling page, no tabs
    page_ui = mo.vstack([
        dashboard_header,
        dashboard_section,
        full_refresh_btn,
        refresh_output,
        output_tab,
        llm_tab,
        membership_tab,
        pipeline_tab,
    ])
    page_ui
    return
```

This intentionally still references `pipeline_tab`, `llm_tab`, `membership_tab`, `output_tab` by their current (pre-existing, unmodified) names — those cells haven't been touched yet. `full_refresh_btn` and `refresh_output` are placed here as an interim position; Task 4 moves them to their final spot once the Curate Data heading exists.

- [ ] **Step 3: Verify**

```bash
marimo export html notebook.py -o /tmp/claude-1000/nb_check.html -f
echo "exit: $?"
grep -c "mo.ui.tabs\|ui-tabs" notebook.py
```

Expected: `exit: 0`; the `grep` for `mo.ui.tabs` in `notebook.py` itself returns `0` (the literal string no longer appears in the source).

- [ ] **Step 4: Commit**

```bash
git add notebook.py
git commit -m "feat: replace tabs with single-page layout, add dashboard header and logo"
```

---

### Task 3: Comprehensive dataset preview (replaces `output_preview` / `output_tab`)

**Files:**
- Create (new cells in `notebook.py`, appended after `shared_state`/before `dashboard_header`, exact position doesn't matter to marimo): `preview_loaders`, `dataset_preview_dropdown`, `dataset_preview_table`
- Delete: `notebook.py:400-417` (`output_preview` cell)
- Modify: `notebook.py`'s `page` cell (from Task 2) — swap `output_tab` for `dataset_preview_section`

**Interfaces:**
- Consumes: `pd, json, OUT_PARQUET, CURATED_DIR, RAW_DIR` (all already available from `imports`/`shared_state`)
- Produces: `PREVIEW_SOURCES: dict[str, Callable[[], pd.DataFrame | None] | None]`, `dataset_dropdown: mo.ui.dropdown`, `dataset_preview_section: Html` — the last one consumed by `page`.

- [ ] **Step 1: Add the `preview_loaders` cell**

Add this new cell anywhere after `shared_state` in the file (e.g. right after it, before the `refresh_state` cell):

```python
@app.cell(hide_code=True)
def preview_loaders(pd, json, OUT_PARQUET, CURATED_DIR, RAW_DIR):
    # Preview loaders — one entry per pipeline dataset, used by the Dataset Preview dropdown
    _CURATED_FILES = [
        ("SURF Members (curated)",      "surf_members.csv"),
        ("UKB (curated)",               "ukb_members.csv"),
        ("SHB (curated)",               "shb_members.csv"),
        ("UNL (curated)",               "unl_members.csv"),
        ("UMCNL (curated)",             "umcnl_members.csv"),
        ("VH (curated)",                "vh_members.csv"),
        ("KNAW Institutes (curated)",   "knaw_institutes.csv"),
        ("NWO-i (curated)",             "nwoi_institutes.csv"),
        ("OpenAIRE Members (curated)",  "openaire_members.csv"),
        ("NBN Prefixes (curated)",      "nbn_prefixes.csv"),
    ]

    def _load_assembled():
        return pd.read_parquet(OUT_PARQUET) if OUT_PARQUET.exists() else None

    def _load_ror_raw():
        from src.ror_fetcher import load_orgs
        rows = load_orgs()
        return pd.DataFrame(rows) if rows else None

    def _load_zenodo_raw():
        path = RAW_DIR / "zenodo" / "nl-orgs-baseline.xlsx"
        return pd.read_excel(path) if path.exists() else None

    def _flatten_per_org_json(stage: str, list_key: str, limit: int = 300):
        # OpenAlex/OpenAIRE cache one small JSON file per organisation (1700+ files) —
        # parsing all of them takes minutes, so this samples the first `limit` files.
        def _loader():
            paths = sorted((RAW_DIR / stage).glob("*.json"))
            paths = [p for p in paths if p.name != "_metadata.json"][:limit]
            rows = []
            for p in paths:
                data = json.loads(p.read_text())
                rows.extend(data.get(list_key, []))
            return pd.DataFrame(rows) if rows else None
        return _loader

    def _load_barcelona_raw():
        path = RAW_DIR / "barcelona" / "signatories.csv"
        return pd.read_csv(path) if path.exists() else None

    def _load_memberships_joined():
        from src.ror_fetcher import load_orgs
        from src.memberships import load_memberships
        ror_urls = [o["ror_id_url"] for o in load_orgs()]
        if not ror_urls:
            return None
        result = load_memberships(ror_urls)
        df = pd.DataFrame.from_dict(result, orient="index").reset_index()
        return df.rename(columns={"index": "ror_id_url"})

    def _load_curated_csv(filename: str):
        def _loader():
            path = CURATED_DIR / filename
            return pd.read_csv(path) if path.exists() else None
        return _loader

    PREVIEW_SOURCES = {
        "Assembled Output": _load_assembled,
        "ROR (raw)": _load_ror_raw,
        "Zenodo Baseline (raw)": _load_zenodo_raw,
        "OpenAlex (raw, first 300 files)": _flatten_per_org_json("openalex", "results"),
        "OpenAIRE (raw, first 300 files)": _flatten_per_org_json("openaire", "results"),
        "Barcelona Declaration (raw)": _load_barcelona_raw,
        "ALEI / KVK": None,
        "EU PIC": None,
        "Memberships (joined)": _load_memberships_joined,
    }
    for _label, _filename in _CURATED_FILES:
        PREVIEW_SOURCES[_label] = _load_curated_csv(_filename)

    return (PREVIEW_SOURCES,)
```

- [ ] **Step 2: Sanity-check the loaders in isolation before wiring them into cells**

```bash
python3 -c "
import sys
sys.path.insert(0, '.')
import pandas as pd, json
from pathlib import Path
OUT_PARQUET = Path('data/nl_research_orgs.parquet')
CURATED_DIR = Path('data/curated')
RAW_DIR = Path('data/raw')

# Re-run the cell body's logic standalone (copy of preview_loaders, for a quick check only)
exec(open('/dev/stdin').read())
" <<'PYEOF'
def _load_ror_raw():
    from src.ror_fetcher import load_orgs
    rows = load_orgs()
    return pd.DataFrame(rows) if rows else None

def _flatten_per_org_json(stage, list_key, limit=300):
    def _loader():
        paths = sorted((RAW_DIR / stage).glob("*.json"))
        paths = [p for p in paths if p.name != "_metadata.json"][:limit]
        rows = []
        for p in paths:
            data = json.loads(p.read_text())
            rows.extend(data.get(list_key, []))
        return pd.DataFrame(rows) if rows else None
    return _loader

df1 = _load_ror_raw()
print("ROR raw:", None if df1 is None else df1.shape)
df2 = _flatten_per_org_json("openalex", "results")()
print("OpenAlex sample:", None if df2 is None else df2.shape)
df3 = pd.read_parquet(OUT_PARQUET) if OUT_PARQUET.exists() else None
print("Assembled:", None if df3 is None else df3.shape)
PYEOF
```

Expected: three shape tuples printed, no exceptions (`ROR raw: (1494, ...)`, `OpenAlex sample: (300, ...)` or close to it, `Assembled: (1494, ...)` — exact numbers may differ slightly from a previous session's cached data, that's fine, this is just confirming nothing throws).

- [ ] **Step 3: Add the dropdown + rendering cells, delete `output_preview`**

Delete the old `output_preview` cell entirely (`notebook.py:400-417`):

```python
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
```

Replace it with two new cells in its place:

```python
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
                mo.md("No data yet for this source — run its Refresh button in **Pipeline Stages** below."),
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
            "a raw pipeline source, or a curated membership list. Defaults to the "
            "assembled output. Raw per-organisation sources (OpenAlex, OpenAIRE) are "
            "capped to the first 300 cached files for speed; every other view shows "
            "the full dataset."
        ),
        dataset_dropdown,
        _table,
    ])
    return (dataset_preview_section,)
```

- [ ] **Step 4: Update `page` to use the new section**

In the `page` cell (from Task 2), change the parameter list and body from referencing `output_tab` to `dataset_preview_section`:

```python
@app.cell(hide_code=True)
def page(
    mo, dashboard_header, dashboard_section, full_refresh_btn, refresh_output,
    dataset_preview_section, pipeline_tab, llm_tab, membership_tab,
):
    # Main layout — single scrolling page, no tabs
    page_ui = mo.vstack([
        dashboard_header,
        dashboard_section,
        full_refresh_btn,
        refresh_output,
        dataset_preview_section,
        llm_tab,
        membership_tab,
        pipeline_tab,
    ])
    page_ui
    return
```

- [ ] **Step 5: Verify**

```bash
marimo export html notebook.py -o /tmp/claude-1000/nb_check.html -f
echo "exit: $?"
grep -c "Dataset Preview" /tmp/claude-1000/nb_check.html
```

Expected: `exit: 0`; the grep count is at least `1` (the heading rendered).

- [ ] **Step 6: Commit**

```bash
git add notebook.py
git commit -m "feat: add comprehensive dataset preview dropdown, remove single-purpose output preview"
```

---

### Task 4: "Curate Data" intro section, finalize Full Refresh's position

**Files:**
- Create (new cell): `curate_data_intro`
- Modify: `page` cell — move `full_refresh_btn`/`refresh_output` to sit after the new intro, ahead of `dataset_preview_section` per the spec's page order.

**Interfaces:**
- Produces: `curate_data_intro: Html` — consumed by `page`.

- [ ] **Step 1: Add the `curate_data_intro` cell**

```python
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
        "`force_refresh=True` and finishes by re-running the assembler, so "
        "`data/nl_research_orgs.parquet` ends up reflecting everything currently in "
        "`data/curated/` plus freshly-fetched raw data. This can take a while and "
        "calls every external API."
    )
    return (curate_data_intro,)
```

- [ ] **Step 2: Reorder `page`**

```python
@app.cell(hide_code=True)
def page(
    mo, dashboard_header, dashboard_section, dataset_preview_section,
    curate_data_intro, full_refresh_btn, refresh_output,
    llm_tab, membership_tab, pipeline_tab,
):
    # Main layout — single scrolling page, no tabs
    page_ui = mo.vstack([
        dashboard_header,
        dashboard_section,
        dataset_preview_section,
        curate_data_intro,
        full_refresh_btn,
        refresh_output,
        llm_tab,
        membership_tab,
        pipeline_tab,
    ])
    page_ui
    return
```

- [ ] **Step 3: Verify**

```bash
marimo export html notebook.py -o /tmp/claude-1000/nb_check.html -f
echo "exit: $?"
grep -c "Curate Data" /tmp/claude-1000/nb_check.html
```

Expected: `exit: 0`; grep count at least `1`.

- [ ] **Step 4: Commit**

```bash
git add notebook.py
git commit -m "feat: add Curate Data section intro, finalize page section order"
```

---

### Task 5: LLM Configuration copy (rename `llm_tab` → `llm_section`)

**Files:**
- Modify: `notebook.py:297-318` (`llm_tab` cell)
- Modify: `page` cell — swap `llm_tab` param/reference for `llm_section`

**Interfaces:**
- Produces: `llm_section: Html` (was `llm_tab`) — consumed by `page`.

- [ ] **Step 1: Rewrite the cell**

Replace `notebook.py:297-318`:

```python
@app.cell(hide_code=True)
def llm_section(mo, llm_base_url, llm_api_key, llm_model_live, test_btn, conn_status):
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
```

- [ ] **Step 2: Update `page`**

Change the `page` cell's parameter `llm_tab` to `llm_section`, and the corresponding entry in the `mo.vstack([...])` list from `llm_tab` to `llm_section`.

- [ ] **Step 3: Verify**

```bash
marimo export html notebook.py -o /tmp/claude-1000/nb_check.html -f
echo "exit: $?"
```

Expected: `exit: 0`.

- [ ] **Step 4: Commit**

```bash
git add notebook.py
git commit -m "docs: explain LLM Configuration's role and its Test connection button"
```

---

### Task 6: Membership Curation copy (rename `membership_curation`'s output → `membership_section`)

**Files:**
- Modify: `notebook.py:324-394` (`membership_curation` cell)
- Modify: `page` cell — swap `membership_tab` for `membership_section`

**Interfaces:**
- Produces: `membership_section: Html` (was `membership_tab`) — consumed by `page`.

- [ ] **Step 1: Rewrite the end of the cell**

Everything in `membership_curation` (lines 324-392, the `MEMBERSHIP_SOURCES` dict, `save_status`, `_make_membership_section`) stays **exactly as-is**. Only the final two lines change, from:

```python
    sections = dict(
        _make_membership_section(f, lbl, url)
        for f, (lbl, url) in MEMBERSHIP_SOURCES.items()
    )
    membership_tab = mo.accordion(sections)
    return (membership_tab,)
```

to:

```python
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
```

- [ ] **Step 2: Update `page`**

Change the `page` cell's parameter `membership_tab` to `membership_section`, and the corresponding list entry.

- [ ] **Step 3: Verify**

```bash
marimo export html notebook.py -o /tmp/claude-1000/nb_check.html -f
echo "exit: $?"
```

Expected: `exit: 0`.

- [ ] **Step 4: Commit**

```bash
git add notebook.py
git commit -m "docs: explain Membership Curation's Save/LLM Auto-update buttons"
```

---

### Task 7: Pipeline Stages copy + remove redundant ROR-only preview (rename → `pipeline_section`)

**Files:**
- Modify: `notebook.py:216-291` (`pipeline_stages` cell)
- Modify: `page` cell — swap `pipeline_tab` for `pipeline_section`

**Interfaces:**
- Produces: `pipeline_section: Html` (was `pipeline_tab`) — consumed by `page`.
- No longer consumes `pd` (the removed ROR-preview block was its only use in this cell).

- [ ] **Step 1: Rewrite the cell**

Replace the whole cell at `notebook.py:216-291`:

```python
@app.cell(hide_code=True)
def pipeline_section(mo, STAGE_META, read_meta, get_refresh_results, set_refresh_results):
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
            "that source only; freshness shown here also drives the Dashboard "
            "cards above and the raw entries in Dataset Preview."
        ),
        mo.accordion(accordion_items),
    ])
    return (pipeline_section,)
```

Note what changed vs. the original: the function signature drops `pd` (unused now), the ROR-only preview block (`if stage == "ror": ...` building a 10-row table) is removed along with the `preview` variable and its slot in `body`'s `mo.vstack`, a one-line button explanation is added, and an intro `mo.md` + rename wrap the final accordion.

- [ ] **Step 2: Update `page`**

Change the `page` cell's parameter `pipeline_tab` to `pipeline_section`, and the corresponding list entry. This is also the last remaining rename, so `page` should now read:

```python
@app.cell(hide_code=True)
def page(
    mo, dashboard_header, dashboard_section, dataset_preview_section,
    curate_data_intro, full_refresh_btn, refresh_output,
    llm_section, membership_section, pipeline_section,
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
```

- [ ] **Step 3: Verify**

```bash
marimo export html notebook.py -o /tmp/claude-1000/nb_check.html -f
echo "exit: $?"
grep -c "mo.ui.tabs" notebook.py
grep -c "_tab\b" notebook.py
```

Expected: `exit: 0`; both greps return `0` (no leftover `_tab`-suffixed variable names, no `mo.ui.tabs` calls anywhere).

- [ ] **Step 4: Commit**

```bash
git add notebook.py
git commit -m "docs: explain Pipeline Stages refresh buttons, remove redundant ROR-only preview"
```

---

### Task 8: Update `README.md`'s stale tab references

**Files:**
- Modify: `README.md:50`

**Interfaces:** none (docs only).

- [ ] **Step 1: Replace the stale tab-numbered instructions**

Current line 50:

```markdown
Open the notebook (`uvx marimo run notebook.py`), go to **Tab 4 — Membership Curation**. Each membership source shows an editable table and an "LLM Auto-update" button. Configure your LLM provider first in **Tab 3 — LLM Configuration**.
```

Replace with:

```markdown
Open the notebook (`uvx marimo run notebook.py`) and scroll to **Curate Data → Membership Curation**. Each membership source shows an editable table and an "LLM Auto-update" button. Configure your LLM provider first in **Curate Data → LLM Configuration**, just above it.
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: update README for the single-page notebook layout"
```

---

### Task 9: Full verification, push, PR, merge

**Files:** none (verification + shipping only).

- [ ] **Step 1: Run the full existing test suite**

```bash
pytest tests/ -q
```

Expected: all tests pass (same count as before this change — this task touched no `src/*.py` files).

- [ ] **Step 2: Full headless notebook run**

```bash
marimo export html notebook.py -o /tmp/claude-1000/nb_final.html -f
echo "exit: $?"
```

Expected: `exit: 0`.

- [ ] **Step 3: Spot-check the rendered HTML for the key structural requirements**

```bash
grep -c "mo.ui.tabs" notebook.py                     # expect 0
grep -o "surf-logo.svg" /tmp/claude-1000/nb_final.html | head -1   # expect a match
grep -c "Curate Data" /tmp/claude-1000/nb_final.html  # expect >= 1
grep -c "Dataset Preview" /tmp/claude-1000/nb_final.html  # expect >= 1
```

- [ ] **Step 4: Review the full diff**

```bash
git diff master --stat
git log --oneline master..HEAD
```

Confirm the diff only touches `notebook.py`, `README.md`, and adds `assets/surf-logo.svg`.

- [ ] **Step 5: Push and open the PR**

```bash
git push -u origin <branch-name>
gh pr create --title "feat: redesign notebook layout — single page, SURF logo, dataset preview, curation guide" --body "$(cat <<'EOF'
## Summary
- Replaced the 5-tab layout with a single scrolling page (no `mo.ui.tabs`).
- Dashboard: added explanatory copy, the SURF logo (fetched once to `assets/surf-logo.svg`), and context that the output feeds the Dutch Open Research Information data lake and is archived at https://zenodo.org/communities/surf/.
- Added a comprehensive "Dataset Preview" dropdown (assembled output, every raw source, the joined memberships view, and all 10 curated CSVs) directly under the dashboard cards, replacing the old assembled-only Output Preview tab.
- Added a "Curate Data" section explaining the logical order of what follows and what's needed to produce the output file; moved the "Full Refresh" button here from the Dashboard.
- Added explanatory text to every button across LLM Configuration, Membership Curation, and Pipeline Stages.
- Removed the now-redundant ROR-only raw-data preview table from Pipeline Stages (superseded by Dataset Preview).
- Updated `README.md`'s stale tab-numbered instructions.

## Test plan
- [x] `pytest tests/` — all pass (no `src/*.py` changes)
- [x] `marimo export html notebook.py` — runs headlessly with no errors
- [x] Verified no `mo.ui.tabs` remain in `notebook.py`
EOF
)"
```

- [ ] **Step 6: Merge**

```bash
gh pr merge --squash --delete-branch
git checkout master && git pull --ff-only
git log --oneline -3
```
