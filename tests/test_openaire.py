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


def test_load_results_prefers_openorgs_over_pending(tmp_path):
    """A ROR with both an openorgs____ and a pending_org_ match should surface the
    curated openorgs____ ID as primary, not whichever one the API listed first."""
    oa_dir = tmp_path / "openaire"
    oa_dir.mkdir()
    payload = {"results": [
        {"id": "pending_org_::aaa111"},
        {"id": "openorgs____::bbb222"},
    ]}
    (oa_dir / "05sy4b952.json").write_text(json.dumps(payload))
    with patch("src.openaire.DATA_DIR", oa_dir):
        from src.openaire import load_results
        results = load_results()
    assert results["https://ror.org/05sy4b952"] == "openorgs____::bbb222"


def test_load_results_falls_back_to_pending_only(tmp_path):
    """A ROR with only a pending_org_ match (the Saba University School of Medicine
    case) should still surface that ID rather than being left empty."""
    oa_dir = tmp_path / "openaire"
    oa_dir.mkdir()
    payload = {"results": [{"id": "pending_org_::ce39425f4e58d8fafb723f979ec5359d"}]}
    (oa_dir / "05sy4b952.json").write_text(json.dumps(payload))
    with patch("src.openaire.DATA_DIR", oa_dir):
        from src.openaire import load_results
        results = load_results()
    assert results["https://ror.org/05sy4b952"] == "pending_org_::ce39425f4e58d8fafb723f979ec5359d"


def test_load_pending_info(tmp_path):
    oa_dir = tmp_path / "openaire"
    oa_dir.mkdir()
    # Multiple org IDs, no openorgs____ match -> first pending is primary (tested via
    # load_results above), the rest show up here as still-outstanding pending_ids.
    (oa_dir / "05sy4b952.json").write_text(json.dumps({"results": [
        {"id": "pending_org_::ce39425f4e58d8fafb723f979ec5359d"},
        {"id": "pending_org_::deadbeef00000000000000000000000"},
    ]}))
    # openorgs____ match + a duplicate pending record -> has_pending True even though
    # the pending ID wasn't chosen as primary.
    (oa_dir / "0002exf56.json").write_text(json.dumps({"results": [
        {"id": "openorgs____::994d7f6fc25c5de47b9212bb69524380"},
        {"id": "pending_org_::deadbeef11111111111111111111111"},
    ]}))
    # No pending record at all.
    (oa_dir / "04dkp9463.json").write_text(json.dumps({"results": [
        {"id": "openorgs____::994d7f6fc25c5de47b9212bb69524380"},
    ]}))
    (oa_dir / "no-match.json").write_text(json.dumps({"results": []}))
    with patch("src.openaire.DATA_DIR", oa_dir):
        from src.openaire import load_pending_info
        info = load_pending_info()

    saba = info["https://ror.org/05sy4b952"]
    assert saba["has_pending"] is True
    assert saba["pending_ids"] == ["pending_org_::deadbeef00000000000000000000000"]

    wodc = info["https://ror.org/0002exf56"]
    assert wodc["has_pending"] is True
    assert wodc["pending_ids"] == ["pending_org_::deadbeef11111111111111111111111"]

    clean = info["https://ror.org/04dkp9463"]
    assert clean["has_pending"] is False
    assert clean["pending_ids"] == []

    unmatched = info["https://ror.org/no-match"]
    assert unmatched["has_pending"] is False
    assert unmatched["pending_ids"] == []


def test_get_token():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"access_token": "tok123"}
    with patch("src.openaire.requests.post", return_value=mock_resp):
        with patch("src.openaire.CLIENT_ID", "myid"):
            with patch("src.openaire.CLIENT_SECRET", "mysecret"):
                from src.openaire import _get_token
                assert _get_token() == "tok123"
