# /// script
# requires-python = ">=3.11"
# dependencies = ["marimo", "duckdb", "pandas", "pyarrow", "requests", "openpyxl", "openai", "python-dotenv"]
# ///
import marimo as mo

__generated_with = "0.13.0"
app = mo.App()


@app.cell
def _():
    import marimo as mo
    return (mo,)


@app.cell
def _(mo):
    args = mo.cli_args()
    source = args.get("source", "all")
    force = args.get("force-refresh", "false").lower() == "true"
    mo.md(f"Running pipeline: source=`{source}`, force_refresh=`{force}`")
    return args, force, source


@app.cell
def _(force, mo, source):
    from dotenv import load_dotenv
    load_dotenv()

    STAGES = {
        "ror": ("src.ror_fetcher", []),
        "zenodo": ("src.zenodo_baseline", []),
        "barcelona": ("src.barcelona", []),
        "memberships": ("src.memberships", []),
    }
    ORDER = ["ror", "zenodo", "openalex", "openaire", "alei", "pic", "barcelona", "memberships", "assemble"]

    to_run = ORDER if source == "all" else [source]
    results = {}

    for stage in to_run:
        print(f"[{stage}] starting...")
        try:
            if stage == "openalex":
                import importlib
                mod = importlib.import_module("src.ror_fetcher")
                orgs = mod.load_orgs()
                ror_urls = [o["ror_id_url"] for o in orgs]
                m = importlib.import_module("src.openalex")
                result = m.fetch(ror_urls, force_refresh=force)
            elif stage == "openaire":
                import importlib
                mod = importlib.import_module("src.ror_fetcher")
                orgs = mod.load_orgs()
                ror_urls = [o["ror_id_url"] for o in orgs]
                m = importlib.import_module("src.openaire")
                result = m.fetch(ror_urls, force_refresh=force)
            elif stage == "pic":
                # PIC's search endpoint matches by organisation name, not ROR ID
                import importlib
                mod = importlib.import_module("src.ror_fetcher")
                orgs = mod.load_orgs()
                m = importlib.import_module("src.pic_fetcher")
                result = m.fetch(orgs, force_refresh=force)
            elif stage == "alei":
                # OpenKvK's search endpoint matches by organisation name, not ROR ID
                import importlib
                mod = importlib.import_module("src.ror_fetcher")
                orgs = mod.load_orgs()
                m = importlib.import_module("src.alei_fetcher")
                result = m.fetch(orgs, force_refresh=force)
            elif stage == "assemble":
                import importlib
                m = importlib.import_module("src.assembler")
                result = m.fetch(force_refresh=force)
            else:
                import importlib
                mod_name, _ = STAGES[stage]
                m = importlib.import_module(mod_name)
                result = m.fetch(force_refresh=force)
            results[stage] = result
            print(f"[{stage}] done — {result.get('record_count', '?')} records")
        except Exception as e:
            print(f"[{stage}] ERROR: {e}")
            results[stage] = {"error": str(e)}

    mo.md("Pipeline complete. See stdout for details.")
    return results,


if __name__ == "__main__":
    app.run()
