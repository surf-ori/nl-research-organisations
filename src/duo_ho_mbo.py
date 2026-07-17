# /// script
# requires-python = ">=3.11"
# dependencies = ["marimo", "requests", "python-dotenv"]
# ///
"""
DUO HO/MBO Fetcher

Downloads DUO's official address lists of Dutch higher education (HO) and
vocational education (MBO) institutions and matches each ROR organisation against
them by name, adding is_ho_institution/ho_instellingscode and
is_mbo_institution/mbo_instellingscode columns.

Sources (see data.overheid.nl for the human-readable dataset pages):
  HO:  https://data.overheid.nl/dataset/adressen_ho  (RDF: .../adressen_ho/rdf)
  MBO: https://data.overheid.nl/dataset/adressen_mbo (RDF: .../adressen_mbo/rdf)
Machine-readable dumps used here (no API key needed):
  HO:  https://onderwijsdata.duo.nl/datastore/dump/bf1da9c6-c688-4873-91b1-b12c9ac2c132?format=json
  MBO: https://onderwijsdata.duo.nl/datastore/dump/1a946297-a7ca-48d5-9ae8-19ad73bf8176?format=json

Both dumps list one row per institution *location* (INSTELLINGSNAAM + address), not
per legal entity, and carry no ROR ID — matching is by exact name (see _match()'s
docstring for why fuzzy matching isn't safe here).
"""

import marimo

__generated_with = "0.23.10"
app = marimo.App(width="full")


with app.setup:
    # Setup — imports, constants, and internal helpers
    import marimo as mo
    import json
    from datetime import datetime, timezone
    from pathlib import Path

    import requests

    DATA_DIR = Path("data/raw/duo")
    HO_URL  = "https://onderwijsdata.duo.nl/datastore/dump/bf1da9c6-c688-4873-91b1-b12c9ac2c132?format=json"
    MBO_URL = "https://onderwijsdata.duo.nl/datastore/dump/1a946297-a7ca-48d5-9ae8-19ad73bf8176?format=json"

    def _read_dump(filename: str) -> list[dict]:
        """Read a cached DUO dump and return one dict per row (records are field-order lists)."""
        path = DATA_DIR / filename
        if not path.exists():
            return []
        data = json.loads(path.read_text())
        field_ids = [f["id"] for f in data.get("fields", [])]
        return [dict(zip(field_ids, record)) for record in data.get("records", [])]

    def _distinct_institutions(rows: list[dict]) -> dict[str, dict]:
        """Collapse per-location rows to one entry per distinct institution name.

        Returns {INSTELLINGSNAAM: {code, straatnaam, huisnummer, postcode, plaatsnaam}},
        keeping the first row seen. DUO's dump only carries a combined house
        number + addition field ("HUISNUMMER-TOEVOEGING", e.g. "10" or "12a"), not
        separate house number and addition columns.
        """
        out: dict[str, dict] = {}
        for row in rows:
            name = row.get("INSTELLINGSNAAM")
            if name and name not in out:
                out[name] = {
                    "code":       row.get("INSTELLINGSCODE"),
                    "straatnaam": row.get("STRAATNAAM"),
                    "huisnummer": row.get("HUISNUMMER-TOEVOEGING"),
                    "postcode":   row.get("POSTCODE"),
                    "plaatsnaam": row.get("PLAATSNAAM"),
                }
        return out

    def _match(org: dict, institutions_lower: dict[str, dict]) -> dict | None:
        """Exact-match (case-insensitive) an org's name or aliases against DUO institution
        names; return the matched institution info dict.

        DUO's official name is almost always the Dutch name ("Technische Universiteit
        Delft"), while ROR's is usually the English display name ("Delft University of
        Technology") — these differ too much, in more than just spelling, for
        difflib-style fuzzy matching to be safe. A first attempt at fuzzy matching
        produced confident-looking false positives between unrelated institutions that
        happen to share a generic suffix like "University of Applied Sciences" (e.g.
        Rotterdam UAS matched to Breda UAS at a 0.89 ratio). Exact match undercounts —
        it misses ROR orgs whose Dutch name isn't in ROR's aliases — but doesn't lie.
        """
        candidates = [org["name"]] + (org.get("aliases") or "").split("|")
        for candidate in candidates:
            info = institutions_lower.get(candidate.strip().lower())
            if info:
                return info
        return None


@app.function
def load_results(ror_orgs: list[dict]) -> dict[str, dict]:
    """Match each ROR org against the cached DUO HO and MBO institution lists.

    Returns a mapping of ror_id_url -> {is_ho_institution, ho_instellingscode,
    ho_straatnaam, ho_huisnummer, ho_postcode, ho_plaatsnaam,
    is_mbo_institution, mbo_instellingscode,
    mbo_straatnaam, mbo_huisnummer, mbo_postcode, mbo_plaatsnaam}.
    """
    ho_institutions  = {k.lower(): v for k, v in _distinct_institutions(_read_dump("ho.json")).items()}
    mbo_institutions = {k.lower(): v for k, v in _distinct_institutions(_read_dump("mbo.json")).items()}

    results: dict[str, dict] = {}
    for org in ror_orgs:
        ho_info  = _match(org, ho_institutions)
        mbo_info = _match(org, mbo_institutions)
        results[org["ror_id_url"]] = {
            "is_ho_institution":    ho_info is not None,
            "ho_instellingscode":   ho_info.get("code") if ho_info else None,
            "ho_straatnaam":        ho_info.get("straatnaam") if ho_info else None,
            "ho_huisnummer":        ho_info.get("huisnummer") if ho_info else None,
            "ho_postcode":          ho_info.get("postcode") if ho_info else None,
            "ho_plaatsnaam":        ho_info.get("plaatsnaam") if ho_info else None,
            "is_mbo_institution":   mbo_info is not None,
            "mbo_instellingscode":  mbo_info.get("code") if mbo_info else None,
            "mbo_straatnaam":       mbo_info.get("straatnaam") if mbo_info else None,
            "mbo_huisnummer":       mbo_info.get("huisnummer") if mbo_info else None,
            "mbo_postcode":         mbo_info.get("postcode") if mbo_info else None,
            "mbo_plaatsnaam":       mbo_info.get("plaatsnaam") if mbo_info else None,
        }
    return results


@app.function
def fetch(force_refresh: bool = False) -> dict:
    """Download both DUO dumps and cache them to DATA_DIR.

    Skips the download when both files already exist and force_refresh is False.
    Returns {"record_count": int, "fetched_at": str, "source_url": str}.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    meta_path = DATA_DIR / "_metadata.json"
    ho_path, mbo_path = DATA_DIR / "ho.json", DATA_DIR / "mbo.json"

    if ho_path.exists() and mbo_path.exists() and not force_refresh and meta_path.exists():
        return json.loads(meta_path.read_text())

    for url, path in [(HO_URL, ho_path), (MBO_URL, mbo_path)]:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        path.write_bytes(resp.content)

    record_count = len(_read_dump("ho.json")) + len(_read_dump("mbo.json"))
    meta = {
        "fetched_at":   datetime.now(timezone.utc).isoformat(),
        "record_count": record_count,
        "source_url":   HO_URL,
    }
    meta_path.write_text(json.dumps(meta))
    return meta


@app.cell(hide_code=True)
def header():
    # Header — DUO HO/MBO module description and matching strategy
    mo.md("""
    ## DUO HO/MBO — Official Higher Education & Vocational Education Address Lists

    Downloads DUO's official institution address lists for
    [higher education](https://data.overheid.nl/dataset/adressen_ho) and
    [vocational education (MBO)](https://data.overheid.nl/dataset/adressen_mbo),
    and matches each ROR organisation by exact name/alias — neither dump carries a
    ROR ID, and DUO's official Dutch institution names differ too much from ROR's
    English display names for fuzzy matching to be safe (see `_match()`'s docstring).

    Adds `is_ho_institution`/`ho_instellingscode` and
    `is_mbo_institution`/`mbo_instellingscode`.

    Cached at `data/raw/duo/ho.json` and `data/raw/duo/mbo.json`.
    """)
    return


@app.cell(hide_code=True)
def summary():
    # Summary — count of distinct institutions in each cached dump
    ho_count = len(_distinct_institutions(_read_dump("ho.json")))
    mbo_count = len(_distinct_institutions(_read_dump("mbo.json")))
    content = (
        mo.md(f"**{ho_count} HO institutions**, **{mbo_count} MBO institutions** cached")
        if ho_count or mbo_count
        else mo.callout(
            mo.md("No DUO data cached yet — run `fetch()` or use the Pipeline Stages tab."),
            kind="warn",
        )
    )
    content
    return


if __name__ == "__main__":
    app.run()
