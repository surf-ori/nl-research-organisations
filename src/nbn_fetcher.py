# /// script
# requires-python = ">=3.11"
# dependencies = ["marimo", "requests", "python-dotenv"]
# ///

import marimo

__generated_with = "0.23.10"
app = marimo.App(width="full")


with app.setup:
    # Setup — constants and parsing helpers for the KB NBN catalog
    import marimo as mo
    import csv
    import difflib
    import io
    import re
    import time
    from pathlib import Path

    import requests

    KB_CATALOG_URL = (
        "https://www.kb.nl/organisatie/onderzoek-expertise/informatie-infrastructuur-"
        "diensten-voor-bibliotheken/registration-agency-nbn/nbn-catalogus"
    )
    ROR_API_BASE = "https://api.ror.org/v2/organizations"
    DATA_DIR     = Path("data/curated")
    OUT_CSV      = DATA_DIR / "nbn_prefixes.csv"
    NBN_META_DIR = Path("data/raw/nbn")

    _KNOWN_IDS = {
        # Hard-coded for common institutions where the ROR API search is unreliable
        "Universiteit Utrecht":              "https://ror.org/04pp8hn57",
        "Utrecht University":               "https://ror.org/04pp8hn57",
        "Rijksuniversiteit Groningen":       "https://ror.org/012p63287",
        "Universiteit van Tilburg":          "https://ror.org/04b8v1s79",
        "Tilburg University":               "https://ror.org/04b8v1s79",
        "Erasmus Universiteit Rotterdam":    "https://ror.org/057w15z03",
        "KNAW":                             "https://ror.org/043c0p156",
        "NWO / CWI":                        "https://ror.org/04jsz6e67",
        "Open Universiteit Nederland":       "https://ror.org/018dfmf50",
        "Radboud Universiteit Nijmegen":     "https://ror.org/016xsfp80",
        "RIVM":                             "https://ror.org/01cesdt21",
        "Rijksinstituut voor Volksgezondheid en Mileu": "https://ror.org/01cesdt21",
        "Technische Universiteit Delft":     "https://ror.org/02e2c7k09",
        "Technische Universiteit Eindhoven": "https://ror.org/02c2kyt77",
        "Universiteit Leiden":              "https://ror.org/027bh9e22",
        "Universiteit Maastricht":          "https://ror.org/02jz4aj89",
        "Universiteit Twente":              "https://ror.org/006hf6230",
        "Universiteit van Amsterdam":        "https://ror.org/04dkp9463",
        "Vrije Universiteit Amsterdam":      "https://ror.org/008xxew50",
        "Wageningen Universiteit & Research Centrum": "https://ror.org/04qw24q55",
        "Wageningen Universiteit":          "https://ror.org/04qw24q55",
        "Dutch Institute for Fundamental Energy Research (DIFFER)": "https://ror.org/03w5dn804",
        "Hogeschool van Amsterdam":         "https://ror.org/00y2z2s03",
        "Avans Hogeschool":                 "https://ror.org/015d5s513",
        "HZ University of Applied Sciences":"https://ror.org/047cqa323",
        "Haagse Hogeschool":               "https://ror.org/021zvq422",
        "Hanzehogeschool Groningen":        "https://ror.org/00xqtxw43",
        "Hogeschool Inholland":            "https://ror.org/03cfsyg37",
        "Hogeschool Rotterdam":            "https://ror.org/0481e1q24",
        "Hogeschool Utrecht":              "https://ror.org/028z9kw20",
        "Hogeschool van Arnhem en Nijmegen": "https://ror.org/0500gea42",
        "Fontys Hogescholen":              "https://ror.org/01jwcme05",
        "NHL Stenden Hogeschool":          "https://ror.org/02xgxme97",
        "Saxion":                          "https://ror.org/005t9n460",
        "Windesheim":                      "https://ror.org/04zmc0e16",
        "Zuyd Hogeschool":                 "https://ror.org/02m6k0m40",
        "Breda University of Applied Sciences": "https://ror.org/04mfj5474",
        "AERES Hogeschool":                "https://ror.org/03jnx2c74",
        "TNO":                             "https://ror.org/01bnjb948",
    }

    def _parse_catalog(html: str) -> list[dict]:
        """Extract (nbn_prefix, dutch_name) pairs from the KB NBN catalog HTML."""
        article = re.search(r"<article[^>]*>(.*?)</article>", html, re.DOTALL)
        text = re.sub(r"<[^>]+>", " ", article.group(1)) if article else html
        text = re.sub(r"&amp;", "&", text)
        text = re.sub(r"&nbsp;", " ", text)
        pattern = re.compile(r"\b(UI|HS|IN):(\d+)-?\s+([^\n]+?)(?=\s+(?:UI|HS|IN):\d+|\s*$)", re.DOTALL)
        entries = []
        for series, num, name in pattern.findall(text):
            clean_name = re.sub(r"\s+", " ", name).strip()
            # Skip retired entries
            if "vervallen" in clean_name.lower():
                continue
            nbn_prefix = f"urn:nbn:nl:{series.lower()}:{num}-"
            entries.append({"nbn_prefix": nbn_prefix, "dutch_name": clean_name})
        return entries

    def _ror_search(query: str) -> tuple[str, str]:
        """Search ROR API for a NL institution; return (ror_id_url, canonical_name)."""
        if query in _KNOWN_IDS:
            return _KNOWN_IDS[query], query
        for cc in ["NL", "AW", "CW", "SX"]:
            try:
                r = requests.get(
                    ROR_API_BASE,
                    params={"query": query, "filter": f"country.country_code:{cc}"},
                    timeout=10,
                )
                items = r.json().get("items", []) if r.status_code == 200 else []
                if not items:
                    continue
                top = items[0]
                disp = [n["value"] for n in top.get("names", []) if "ror_display" in n.get("types", [])]
                ror_url = top["id"]
                top_name = disp[0] if disp else ""
                score = difflib.SequenceMatcher(None, query.lower(), top_name.lower()).ratio()
                if score >= 0.75:
                    return ror_url, top_name
            except Exception:
                pass
            time.sleep(0.05)
        return "", query


@app.function
def load_results() -> dict[str, str]:
    """Return a mapping of ror_id_url → nbn_prefix from the curated CSV.

    Returns an empty dict if the CSV does not yet exist.
    """
    if not OUT_CSV.exists():
        return {}
    with OUT_CSV.open() as f:
        reader = csv.DictReader(f)
        return {
            row["ror_id_url"]: row["nbn_prefix"]
            for row in reader
            if row.get("ror_id_url") and row.get("nbn_prefix")
        }


@app.function
def fetch(force_refresh: bool = False) -> dict:
    """Fetch the KB NBN catalog, match institutions to ROR IDs, and write nbn_prefixes.csv.

    Returns {"record_count": int, "fetched_at": str, "source_url": str}.
    """
    from datetime import datetime, timezone
    import json

    meta_path = NBN_META_DIR / "_metadata.json"
    if OUT_CSV.exists() and not force_refresh and meta_path.exists():
        return json.loads(meta_path.read_text())

    resp = requests.get(KB_CATALOG_URL, timeout=30)
    resp.raise_for_status()
    # Cache the fetched page itself (bronze), matching every other stage's contract —
    # previously only _metadata.json was written here, never the HTML actually parsed.
    NBN_META_DIR.mkdir(parents=True, exist_ok=True)
    (NBN_META_DIR / "kb_nbn_catalog.html").write_text(resp.text, encoding="utf-8")
    entries = _parse_catalog(resp.text)
    if not entries:
        raise ValueError("NBN catalog parsing returned 0 entries — page format may have changed")

    rows = []
    for entry in entries:
        ror_url, ror_name = _ror_search(entry["dutch_name"])
        rows.append({
            "ror_id_url": ror_url,
            "name":        ror_name if ror_url else entry["dutch_name"],
            "nbn_prefix":  entry["nbn_prefix"],
        })
        time.sleep(0.05)

    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=["ror_id_url", "name", "nbn_prefix"])
    writer.writeheader()
    writer.writerows(rows)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OUT_CSV.unlink(missing_ok=True)
    OUT_CSV.write_text(out.getvalue())

    meta = {
        "fetched_at":   datetime.now(timezone.utc).isoformat(),
        "record_count": len(rows),
        "source_url":   KB_CATALOG_URL,
    }
    NBN_META_DIR.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(json.dumps(meta))
    return meta


@app.cell(hide_code=True)
def header():
    # Header — NBN fetcher description
    mo.md("""
    ## NBN Fetcher — KB URN:NBN Prefix Catalog

    Fetches the [KB NBN catalog](https://www.kb.nl/.../nbn-catalogus) and matches
    each Dutch institution to its ROR ID, producing `data/curated/nbn_prefixes.csv`.

    The URN:NBN prefix format is `urn:nbn:nl:{series}:{number}-`, e.g.:
    - `urn:nbn:nl:ui:10-` → Utrecht University
    - `urn:nbn:nl:hs:23-` → University of Applied Sciences Utrecht

    Series: **UI** (universities & research), **HS** (hogescholen), **IN** (other institutions).
    """)
    return


@app.cell(hide_code=True)
def summary():
    # Summary — show the curated NBN prefixes
    import pandas as pd
    content = (
        mo.vstack([
            mo.md(f"**{len(pd.read_csv(OUT_CSV))} institutions** with URN:NBN prefixes · `{OUT_CSV}`"),
            mo.ui.table(pd.read_csv(OUT_CSV)),
        ])
        if OUT_CSV.exists()
        else mo.callout(mo.md("No NBN data yet — run `fetch()` to populate."), kind="warn")
    )
    content
    return


if __name__ == "__main__":
    app.run()
