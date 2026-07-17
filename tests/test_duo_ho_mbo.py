import json
from unittest.mock import patch, MagicMock


def _make_dump(field_ids, rows):
    return json.dumps({
        "fields": [{"id": f} for f in field_ids],
        "records": rows,
    })


HO_FIELDS = ["_id", "SOORT HO", "INSTELLINGSCODE", "INSTELLINGSNAAM"]
MBO_FIELDS = ["_id", "MBO INSTELLINGSSOORT - CODE", "INSTELLINGSCODE", "INSTELLINGSNAAM"]


def test_load_results_matches_ho_and_mbo(tmp_path):
    duo_dir = tmp_path / "duo"
    duo_dir.mkdir()
    (duo_dir / "ho.json").write_text(_make_dump(
        HO_FIELDS, [[1, "hbo", "31FR", "NHL Stenden Hogeschool"]]
    ))
    (duo_dir / "mbo.json").write_text(_make_dump(
        MBO_FIELDS, [[1, "BER", "04NZ", "SOMA College"]]
    ))
    with patch("src.duo_ho_mbo.DATA_DIR", duo_dir):
        from src.duo_ho_mbo import load_results
        orgs = [
            {"ror_id_url": "https://ror.org/ho-match", "name": "NHL Stenden Hogeschool"},
            {"ror_id_url": "https://ror.org/mbo-match", "name": "SOMA College"},
            {"ror_id_url": "https://ror.org/no-match", "name": "Completely Unrelated Org"},
        ]
        results = load_results(orgs)

    ho = results["https://ror.org/ho-match"]
    assert ho["is_ho_institution"] is True
    assert ho["ho_instellingscode"] == "31FR"
    assert ho["is_mbo_institution"] is False

    mbo = results["https://ror.org/mbo-match"]
    assert mbo["is_mbo_institution"] is True
    assert mbo["mbo_instellingscode"] == "04NZ"
    assert mbo["is_ho_institution"] is False

    none_matched = results["https://ror.org/no-match"]
    assert none_matched["is_ho_institution"] is False
    assert none_matched["is_mbo_institution"] is False
    assert none_matched["ho_instellingscode"] is None


def test_load_results_does_not_fuzzy_match_similar_names(tmp_path):
    # Regression test: an earlier difflib-based implementation matched "Rotterdam
    # University of Applied Sciences" to "Breda University of Applied Sciences" at a
    # 0.89 ratio — two unrelated institutions sharing a generic suffix. Exact match
    # must not do the same.
    duo_dir = tmp_path / "duo"
    duo_dir.mkdir()
    (duo_dir / "ho.json").write_text(_make_dump(
        HO_FIELDS, [[1, "hbo", "21UI", "Breda University of Applied Sciences"]]
    ))
    (duo_dir / "mbo.json").write_text(_make_dump(MBO_FIELDS, []))
    with patch("src.duo_ho_mbo.DATA_DIR", duo_dir):
        from src.duo_ho_mbo import load_results
        orgs = [{"ror_id_url": "https://ror.org/rotterdam", "name": "Rotterdam University of Applied Sciences"}]
        results = load_results(orgs)
    assert results["https://ror.org/rotterdam"]["is_ho_institution"] is False
    assert results["https://ror.org/rotterdam"]["ho_instellingscode"] is None


def test_load_results_matches_via_alias(tmp_path):
    duo_dir = tmp_path / "duo"
    duo_dir.mkdir()
    (duo_dir / "ho.json").write_text(_make_dump(
        HO_FIELDS, [[1, "wo", "21PN", "Universiteit Utrecht"]]
    ))
    (duo_dir / "mbo.json").write_text(_make_dump(MBO_FIELDS, []))
    with patch("src.duo_ho_mbo.DATA_DIR", duo_dir):
        from src.duo_ho_mbo import load_results
        orgs = [{
            "ror_id_url": "https://ror.org/04pp8hn57",
            "name": "Utrecht University",
            "aliases": "Rijksuniversiteit Utrecht|Universiteit Utrecht",
        }]
        results = load_results(orgs)
    assert results["https://ror.org/04pp8hn57"]["is_ho_institution"] is True
    assert results["https://ror.org/04pp8hn57"]["ho_instellingscode"] == "21PN"


def test_fetch_downloads_both_dumps(tmp_path):
    duo_dir = tmp_path / "duo"
    mock_ho = MagicMock()
    mock_ho.content = _make_dump(HO_FIELDS, [[1, "hbo", "31FR", "NHL Stenden Hogeschool"]]).encode()
    mock_mbo = MagicMock()
    mock_mbo.content = _make_dump(MBO_FIELDS, [[1, "BER", "04NZ", "SOMA College"]]).encode()
    with patch("src.duo_ho_mbo.DATA_DIR", duo_dir), \
         patch("src.duo_ho_mbo.requests.get", side_effect=[mock_ho, mock_mbo]):
        from src.duo_ho_mbo import fetch
        result = fetch(force_refresh=True)
    assert result["record_count"] == 2
    assert (duo_dir / "ho.json").exists()
    assert (duo_dir / "mbo.json").exists()
