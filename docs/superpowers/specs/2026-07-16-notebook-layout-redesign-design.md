# Notebook Layout Redesign — Design Spec

Date: 2026-07-16

## Context

`notebook.py` currently presents 5 top-level `mo.ui.tabs`: Dashboard, Pipeline
Stages, LLM Configuration, Membership Curation, Output Preview. The user wants
a single scrolling page (no tabs) with clearer explanations, a SURF logo, and
context about where the output file is used downstream.

## Goals

- Replace the top-level `mo.ui.tabs` with a single vertically-stacked page:
  headings/sections in order, no tab-switching required to see anything.
- Dashboard section: stat cards (unchanged), explanatory copy, SURF logo top
  right of the title, and context that the output feeds the Dutch Open
  Research Information data lake and is archived at the SURF Zenodo
  community for downstream fetching.
- Directly below the dashboard cards: the dataset preview, defaulting to the
  assembled output, with a dropdown to switch to any other pipeline
  dataset (raw or curated).
- A "Curate data" section: explains what the user can do here, the logical
  order of the sub-sections below it, and what steps are needed to produce
  the output file. Contains the "Full Refresh" button (moved here from the
  Dashboard) and its result log.
- Under "Curate data", in order: LLM Configuration, Membership Curation,
  Pipeline Stages — each as its own heading/section (not tabs), each with
  explanatory text describing what its buttons do.
- Pipeline Stages and Membership Curation keep their existing `mo.accordion`
  (collapsible per-item lists) — accordions aren't tabs, and they're still
  the right fit for 10 pipeline sources / 9+1 curated CSVs.

## Non-goals

- No change to the actual fetch/save logic in `src/*.py` — this is a layout
  and copy pass over `notebook.py` only, plus one new small preview-loader
  layer.
- No change to `pipeline.py` (the headless CLI).

## Page structure (top to bottom)

1. **Header** — `mo.hstack([title+intro markdown, surf logo image], justify="space-between")`.
2. **Dashboard explanation** — markdown: what the cards mean, how "fresh
   /aging/stale" works, and the downstream-usage context (Dutch ORI data
   lake + `https://zenodo.org/communities/surf/` archive).
3. **Stat cards** — unchanged `mo.hstack(cards, wrap=True)` loop over
   `STAGE_META`.
4. **Dataset preview** — `mo.ui.dropdown` (default: "Assembled Output") +
   `mo.ui.table` of whatever is selected. Backed by `PREVIEW_SOURCES` (see
   below).
5. **"Curate data" heading + description** — what curation means here, the
   logical order (LLM config → Membership Curation → Pipeline Stages), and
   what's needed to (re)produce the output file.
6. **Full Refresh** — button + result log (moved from Dashboard).
7. **LLM Configuration** — existing controls + explanation that membership
   LLM Auto-update buttons need this configured first.
8. **Membership Curation** — existing accordion; add explanation of Save /
   LLM Auto-update buttons per section.
9. **Pipeline Stages** — existing accordion; add explanation of each
   Refresh button; **remove** the ROR-only raw-data preview table (now
   redundant with the new Dataset preview section).

## Dataset preview: `PREVIEW_SOURCES`

A new cell defines a dict: `{label: loader}` where `loader` is a zero-arg
callable returning a `pd.DataFrame`, or raising/returning `None` for
not-yet-implemented sources (rendered as a callout instead of a table).

| Label | Loader |
|---|---|
| Assembled Output | `pd.read_parquet(OUT_PARQUET)` |
| ROR (raw) | `pd.DataFrame(ror_fetcher.load_orgs())` |
| Zenodo Baseline (raw) | `pd.read_excel(data/raw/zenodo/nl-orgs-baseline.xlsx)` |
| OpenAlex (raw) | `duckdb.read_json_auto('data/raw/openalex/*.json')` → df |
| OpenAIRE (raw) | `duckdb.read_json_auto('data/raw/openaire/*.json')` → df |
| Barcelona Declaration (raw) | `pd.read_csv(data/raw/barcelona/signatories.csv)` |
| ALEI / KVK | placeholder callout (not yet implemented) |
| EU PIC | placeholder callout (not yet implemented) |
| Memberships (joined) | `src.memberships.load_memberships(ror_urls)` → df |
| surf_members.csv … nbn_prefixes.csv (10 files) | `pd.read_csv(data/curated/<file>)` |

Missing files (e.g. a stage never fetched) render "No data yet — run Refresh
for this stage" instead of erroring.

## SURF logo asset

- Fetch `https://www.surf.nl/themes/surf/logo.svg` once and commit it to
  `assets/surf-logo.svg` (new top-level `assets/` dir).
- Displayed via `mo.image(str(LOGO_PATH), width=120)` (SVG scales cleanly;
  exact width tuned visually once rendered).
- Not re-fetched at runtime — it's a static asset like any other repo file,
  so the notebook has no new network dependency for layout chrome.

## Copy / explanatory text (content notes, not final wording)

- Dashboard intro: 2–3 sentences — this page assembles a reference table of
  Dutch research organisations from ROR + several enrichment sources +
  curated membership lists; cards show how fresh each source's cache is;
  the assembled parquet is the thing that matters for downstream use.
- Downstream-usage note: the output feeds the Dutch Open Research
  Information data lake, and is archived at
  `https://zenodo.org/communities/surf/` where it gets fetched for further
  processing.
- Curate data intro: explains the three sections below run in a logical
  order — configure an LLM first (optional but needed for the
  Auto-update buttons), curate/verify membership lists, then refresh raw
  pipeline sources — and that "Full Refresh" runs all of that in one click
  to (re)produce the output parquet.
- Every button gets a one-line "what happens when you click this" note
  next to it (Save changes → overwrites the CSV on disk; LLM Auto-update →
  asks the configured LLM to suggest additions and overwrites on success;
  Refresh `<stage>` → re-fetches that one source; Full Refresh → re-runs
  all 10 stages in order and reassembles the output).

## Testing

- `pytest tests/` must still pass unchanged (no `src/*.py` fetch logic
  changes).
- Manual check: run `uvx marimo run notebook.py`, confirm no tabs remain,
  scroll through the full page, exercise the dataset dropdown across a
  few sources including a placeholder (ALEI) and a missing-data case.
