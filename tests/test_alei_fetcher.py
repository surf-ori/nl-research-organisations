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
