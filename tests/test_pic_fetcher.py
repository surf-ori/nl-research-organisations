import json
from unittest.mock import patch, MagicMock


def test_load_results(tmp_path):
    pic_dir = tmp_path / "pic"
    pic_dir.mkdir()
    (pic_dir / "008xxew50.json").write_text(json.dumps(
        [{"pic": "919322739", "name": "VU Amsterdam", "country": "NL"}]
    ))
    (pic_dir / "no-match.json").write_text(json.dumps([]))
    with patch("src.pic_fetcher.DATA_DIR", pic_dir):
        from src.pic_fetcher import load_results
        results = load_results()
    assert results["https://ror.org/008xxew50"] == "919322739"
    assert results["https://ror.org/no-match"] is None


def test_get_token():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"access_token": "tok123"}
    with patch("src.pic_fetcher.requests.post", return_value=mock_resp):
        from src.pic_fetcher import _get_token
        assert _get_token() == "tok123"


def test_fetch_without_credentials_reports_zero(tmp_path):
    pic_dir = tmp_path / "pic"
    with patch("src.pic_fetcher.DATA_DIR", pic_dir), \
         patch("src.pic_fetcher.CLIENT_ID", ""), \
         patch("src.pic_fetcher.CLIENT_SECRET", ""):
        from src.pic_fetcher import fetch
        result = fetch([{"ror_id_url": "https://ror.org/008xxew50", "name": "VU Amsterdam"}])
    assert result["record_count"] == 0
    assert (pic_dir / "_metadata.json").exists()


def test_fetch_with_credentials_searches_and_caches(tmp_path):
    pic_dir = tmp_path / "pic"
    mock_token_resp = MagicMock()
    mock_token_resp.json.return_value = {"access_token": "tok123"}
    mock_search_resp = MagicMock()
    mock_search_resp.json.return_value = [{"pic": "919322739", "name": "VU Amsterdam", "country": "NL"}]
    with patch("src.pic_fetcher.DATA_DIR", pic_dir), \
         patch("src.pic_fetcher.CLIENT_ID", "myid"), \
         patch("src.pic_fetcher.CLIENT_SECRET", "mysecret"), \
         patch("src.pic_fetcher.requests.post", return_value=mock_token_resp), \
         patch("src.pic_fetcher.requests.get", return_value=mock_search_resp):
        from src.pic_fetcher import fetch
        result = fetch([{"ror_id_url": "https://ror.org/008xxew50", "name": "VU Amsterdam"}])
    assert result["record_count"] == 1
    assert (pic_dir / "008xxew50.json").exists()
