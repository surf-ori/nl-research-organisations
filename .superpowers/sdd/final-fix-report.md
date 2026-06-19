# Final Fix Report

## Fix 1: Contract docs align with implementation (`source_url` vs `output_path`)

### Changes
- `agents.md` lines 65-73: Updated `fetch()` return dict example to use `source_url` (was `output_path`). Added explanatory note that `src/assembler.py` is the exception — it returns `output_path` instead of `source_url`.
- `README.md` lines 97-99: Updated Contributing section `fetch()` signature to return `source_url`. Added note distinguishing assembler behaviour.

No Python code was changed. The implementation was already correct and consistent.

## Fix 2: Dead `CSV_PATH` constant in `src/barcelona.py`

### Changes
- `src/barcelona.py` line 19: Removed `CSV_PATH = DATA_DIR / "signatories.csv"`. The canonical path resolver is `_get_csv_path()`, which is used by all functions in the module.
- `tests/test_assembler.py` line 65: Removed `patch("src.barcelona.CSV_PATH", raw / "barcelona" / "signatories.csv")` — this patch targeted a constant that no longer exists and had no effect on test behaviour.

## Fix 3: LLM output CSV validation before write in `notebook.py`

### Changes
- `notebook.py` lines 337-350 (`_llm_handler` closure inside `_membership_curation`):
  Added validation of the LLM-returned string as CSV before writing to disk.
  - Parses the returned string with `csv.DictReader`.
  - Checks that `ror_id_url` and `name` are present in the fieldnames.
  - Only writes to disk if both columns are present; otherwise sets status to `"error: LLM output missing required columns"`.
  - All other exceptions are still caught and surfaced via `set_save_status`.

## Test Results

```
============================= test session starts ==============================
platform linux -- Python 3.14.4, pytest-9.1.1
collected 17 items

tests/test_assembler.py::test_assemble_produces_parquet PASSED
tests/test_barcelona.py::test_load_results_by_ror PASSED
tests/test_barcelona.py::test_load_results_fuzzy_fallback PASSED
tests/test_llm_curator.py::test_fetch_models_success PASSED
tests/test_llm_curator.py::test_fetch_models_fallback_on_error PASSED
tests/test_llm_curator.py::test_test_connection_success PASSED
tests/test_llm_curator.py::test_curate_csv_returns_string PASSED
tests/test_memberships.py::test_load_memberships PASSED
tests/test_openaire.py::test_load_results PASSED
tests/test_openaire.py::test_get_token PASSED
tests/test_openalex.py::test_load_results PASSED
tests/test_openalex.py::test_fetch_skips_cached PASSED
tests/test_openalex.py::test_fetch_calls_api_for_uncached PASSED
tests/test_ror_fetcher.py::test_extract_org_fields PASSED
tests/test_ror_fetcher.py::test_fetch_skips_when_cached PASSED
tests/test_zenodo_baseline.py::test_load_ror_ids PASSED
tests/test_zenodo_baseline.py::test_fetch_skips_when_cached PASSED

======================== 17 passed in 89.20s (0:01:29) =========================
```

## marimo check output

```
python3 -m marimo check notebook.py
Exit: 0
```

Zero issues reported.

## Concerns

None. All three fixes are low-risk:
- Fix 1 is documentation-only.
- Fix 2 removes dead code with no runtime impact (the removed patch was inert).
- Fix 3 adds a guard that prevents silent data corruption without altering the happy path.
