import json
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest


def test_extract_org_fields(tmp_raw, ror_page_nl):
    with patch("src.ror_fetcher.DATA_DIR", tmp_raw / "ror"):
        (tmp_raw / "ror").mkdir(exist_ok=True)
        (tmp_raw / "ror" / "page_NL_001.json").write_text(json.dumps(ror_page_nl))
        from src.ror_fetcher import load_orgs
        orgs = load_orgs()
    assert len(orgs) == 1
    org = orgs[0]
    assert org["ror_id"] == "04dkp9463"
    assert org["ror_id_url"] == "https://ror.org/04dkp9463"
    assert org["name"] == "Vrije Universiteit Amsterdam"
    assert org["acronym"] == "VU"
    assert "VU Amsterdam" in org["aliases"]
    assert org["org_type"] == "education"
    assert org["status"] == "active"
    assert org["established_year"] == 1880
    assert org["country_code"] == "NL"
    assert org["location_name"] == "Amsterdam"
    assert org["lat"] == 52.37403
    assert org["lng"] == 4.88969
    assert org["geonames_id"] == 2759794
    assert org["website_url"] == "https://vu.nl"
    assert org["wikipedia_url"] is not None
    assert org["isni_id"] == "0000 0001 2248 2840"
    assert org["wikidata_id"] == "Q1065919"
    assert org["grid_id"] == "grid.12380.38"
    assert org["fundref_id"] == "501100001833"


def test_fetch_skips_when_cached(tmp_raw):
    ror_dir = tmp_raw / "ror"
    ror_dir.mkdir(exist_ok=True)
    (ror_dir / "page_NL_001.json").write_text('{"items":[],"meta":{"total":0}}')
    (ror_dir / "_metadata.json").write_text('{"fetched_at":"2026-01-01T00:00:00","record_count":0,"source_url":"https://api.ror.org/v2/organizations"}')
    with patch("src.ror_fetcher.DATA_DIR", ror_dir):
        with patch("src.ror_fetcher.requests.get") as mock_get:
            from src.ror_fetcher import fetch
            fetch(force_refresh=False)
            mock_get.assert_not_called()
