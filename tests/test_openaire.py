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


def test_get_token():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"access_token": "tok123"}
    with patch("src.openaire.requests.post", return_value=mock_resp):
        with patch("src.openaire.CLIENT_ID", "myid"):
            with patch("src.openaire.CLIENT_SECRET", "mysecret"):
                from src.openaire import _get_token
                assert _get_token() == "tok123"
