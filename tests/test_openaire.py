import json
from unittest.mock import patch, MagicMock


def test_load_results(tmp_path):
    oa_dir = tmp_path / "openaire"
    oa_dir.mkdir()
    payload = {"content": [{"id": "openaire::abc123"}]}
    (oa_dir / "04dkp9463.json").write_text(json.dumps(payload))
    with patch("src.openaire.DATA_DIR", oa_dir):
        from src.openaire import load_results
        results = load_results()
    assert results["https://ror.org/04dkp9463"] == "openaire::abc123"


def test_load_identifiers(tmp_path):
    oa_dir = tmp_path / "openaire"
    oa_dir.mkdir()
    payload = {
        "results": [{
            "id": "openaire::abc123",
            "pids": [
                {"scheme": "PIC", "value": "999999999"},
                {"scheme": "PIC", "value": "111111111"},  # duplicate scheme: first one wins
                {"scheme": "GRID", "value": "grid.1.1"},
                {"scheme": "Wikidata", "value": "Q1"},
                {"scheme": "eurocrisdris::01222", "value": "ignored-custom-scheme"},
            ],
        }]
    }
    (oa_dir / "04dkp9463.json").write_text(json.dumps(payload))
    (oa_dir / "no-match.json").write_text(json.dumps({"results": []}))
    with patch("src.openaire.DATA_DIR", oa_dir):
        from src.openaire import load_identifiers
        results = load_identifiers()

    matched = results["https://ror.org/04dkp9463"]
    assert matched["pic_id"] == "999999999"
    assert matched["grid_id"] == "grid.1.1"
    assert matched["wikidata_id"] == "Q1"
    assert matched["viaf_id"] is None

    unmatched = results["https://ror.org/no-match"]
    assert all(v is None for v in unmatched.values())


def test_get_token():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"access_token": "tok123"}
    with patch("src.openaire.requests.post", return_value=mock_resp):
        with patch("src.openaire.CLIENT_ID", "myid"):
            with patch("src.openaire.CLIENT_SECRET", "mysecret"):
                from src.openaire import _get_token
                assert _get_token() == "tok123"
