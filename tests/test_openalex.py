import json
from unittest.mock import patch, MagicMock


def test_load_results(tmp_path):
    oa_dir = tmp_path / "openalex"
    oa_dir.mkdir()
    payload = {"results": [{"id": "https://openalex.org/I123456789"}]}
    (oa_dir / "04dkp9463.json").write_text(json.dumps(payload))
    with patch("src.openalex.DATA_DIR", oa_dir):
        from src.openalex import load_results
        results = load_results()
    assert results["https://ror.org/04dkp9463"] == "https://openalex.org/I123456789"


def test_fetch_skips_cached(tmp_path):
    oa_dir = tmp_path / "openalex"
    oa_dir.mkdir()
    (oa_dir / "04dkp9463.json").write_text('{"results":[{"id":"https://openalex.org/I1"}]}')
    with patch("src.openalex.DATA_DIR", oa_dir):
        with patch("src.openalex.requests.get") as mock_get:
            from src.openalex import fetch
            fetch(["https://ror.org/04dkp9463"])
            mock_get.assert_not_called()


def test_fetch_calls_api_for_uncached(tmp_path):
    oa_dir = tmp_path / "openalex"
    oa_dir.mkdir()
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"results": [{"id": "https://openalex.org/I999"}]}
    mock_resp.status_code = 200
    mock_resp.text = '{"results": [{"id": "https://openalex.org/I999"}]}'
    with patch("src.openalex.DATA_DIR", oa_dir):
        with patch("src.openalex.requests.get", return_value=mock_resp) as mock_get:
            from src.openalex import fetch
            fetch(["https://ror.org/newid123"])
            mock_get.assert_called_once()
