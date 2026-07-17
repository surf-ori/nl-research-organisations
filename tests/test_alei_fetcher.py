import json
from unittest.mock import patch, MagicMock


def test_load_results(tmp_path):
    alei_dir = tmp_path / "alei"
    alei_dir.mkdir()
    (alei_dir / "008xxew50.json").write_text(json.dumps(
        [{"dossiernummer": "41208034", "handelsnaam": "Vrije Universiteit Amsterdam"}]
    ))
    (alei_dir / "no-match.json").write_text(json.dumps([]))
    with patch("src.alei_fetcher.DATA_DIR", alei_dir):
        from src.alei_fetcher import load_results
        results = load_results()
    assert results["https://ror.org/008xxew50"] == "NL.KVK:41208034"
    assert results["https://ror.org/no-match"] is None


def test_fetch_without_api_key_reports_zero(tmp_path):
    alei_dir = tmp_path / "alei"
    with patch("src.alei_fetcher.DATA_DIR", alei_dir), \
         patch("src.alei_fetcher.API_KEY", ""):
        from src.alei_fetcher import fetch
        result = fetch([{"ror_id_url": "https://ror.org/008xxew50", "name": "VU Amsterdam"}])
    assert result["record_count"] == 0
    assert (alei_dir / "_metadata.json").exists()


def test_fetch_rejects_unrelated_search_results(tmp_path):
    # Regression test: OpenKvK's query does a text search, not exact match, and can
    # return an unrelated company that only shares a word or two with the query.
    alei_dir = tmp_path / "alei"
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "_embedded": {"bedrijf": [{"dossiernummer": "12345678", "handelsnaam": "University Shop VU B.V."}]}
    }
    with patch("src.alei_fetcher.DATA_DIR", alei_dir), \
         patch("src.alei_fetcher.API_KEY", "mykey"), \
         patch("src.alei_fetcher.requests.get", return_value=mock_resp):
        from src.alei_fetcher import fetch
        result = fetch([{"ror_id_url": "https://ror.org/008xxew50", "name": "Vrije Universiteit Amsterdam"}])
    assert result["record_count"] == 0


def test_fetch_falls_back_to_alias(tmp_path):
    alei_dir = tmp_path / "alei"
    mock_no_match = MagicMock()
    mock_no_match.json.return_value = {"_embedded": {"bedrijf": []}}
    mock_match = MagicMock()
    mock_match.json.return_value = {
        "_embedded": {"bedrijf": [{"dossiernummer": "41208034", "handelsnaam": "Stichting VU"}]}
    }
    with patch("src.alei_fetcher.DATA_DIR", alei_dir), \
         patch("src.alei_fetcher.API_KEY", "mykey"), \
         patch("src.alei_fetcher.requests.get", side_effect=[mock_no_match, mock_match]):
        from src.alei_fetcher import fetch
        result = fetch([{
            "ror_id_url": "https://ror.org/008xxew50",
            "name": "Vrije Universiteit Amsterdam",
            "aliases": "Stichting VU|VU Amsterdam",
        }])
    assert result["record_count"] == 1


def test_fetch_continues_after_one_org_errors(tmp_path):
    # Regression test: a real query ("Re/genT (Netherlands)") got a 400 "ongeldige
    # vraag" from OpenKvK — one bad org must not abort every org processed after it.
    alei_dir = tmp_path / "alei"
    mock_error_resp = MagicMock()
    mock_error_resp.raise_for_status.side_effect = Exception("400 Bad Request")
    mock_ok_resp = MagicMock()
    mock_ok_resp.json.return_value = {
        "_embedded": {"bedrijf": [{"dossiernummer": "41208034", "handelsnaam": "VU Amsterdam"}]}
    }
    with patch("src.alei_fetcher.DATA_DIR", alei_dir), \
         patch("src.alei_fetcher.API_KEY", "mykey"), \
         patch("src.alei_fetcher.requests.get", side_effect=[mock_error_resp, mock_ok_resp]):
        from src.alei_fetcher import fetch
        result = fetch([
            {"ror_id_url": "https://ror.org/bad-name", "name": "Re/genT (Netherlands)"},
            {"ror_id_url": "https://ror.org/008xxew50", "name": "VU Amsterdam"},
        ])
    assert result["record_count"] == 1
    assert (alei_dir / "008xxew50.json").exists()


def test_fetch_with_api_key_searches_and_caches(tmp_path):
    alei_dir = tmp_path / "alei"
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "_embedded": {"bedrijf": [{"dossiernummer": "41208034", "handelsnaam": "VU Amsterdam"}]}
    }
    with patch("src.alei_fetcher.DATA_DIR", alei_dir), \
         patch("src.alei_fetcher.API_KEY", "mykey"), \
         patch("src.alei_fetcher.requests.get", return_value=mock_resp):
        from src.alei_fetcher import fetch
        result = fetch([{"ror_id_url": "https://ror.org/008xxew50", "name": "VU Amsterdam"}])
    assert result["record_count"] == 1
    assert (alei_dir / "008xxew50.json").exists()
