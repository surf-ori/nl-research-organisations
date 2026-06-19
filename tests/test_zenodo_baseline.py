import io
from pathlib import Path
from unittest.mock import patch, MagicMock
import openpyxl
import pytest


def _make_xlsx(ror_urls: list[str]) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["name", "ROR"])
    for url in ror_urls:
        ws.append(["Test Org", url])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_load_ror_ids(tmp_path):
    xlsx_bytes = _make_xlsx(["https://ror.org/04dkp9463", "https://ror.org/abc123"])
    zenodo_dir = tmp_path / "zenodo"
    zenodo_dir.mkdir()
    (zenodo_dir / "nl-orgs-baseline.xlsx").write_bytes(xlsx_bytes)
    with patch("src.zenodo_baseline.DATA_DIR", zenodo_dir):
        from src.zenodo_baseline import load_ror_ids
        ids = load_ror_ids()
    assert "https://ror.org/04dkp9463" in ids
    assert "https://ror.org/abc123" in ids
    assert len(ids) == 2


def test_fetch_skips_when_cached(tmp_path):
    zenodo_dir = tmp_path / "zenodo"
    zenodo_dir.mkdir()
    xlsx_bytes = _make_xlsx(["https://ror.org/04dkp9463"])
    (zenodo_dir / "nl-orgs-baseline.xlsx").write_bytes(xlsx_bytes)
    import json
    (zenodo_dir / "_metadata.json").write_text(json.dumps({"fetched_at": "2026-01-01", "record_count": 1, "source_url": "x"}))
    with patch("src.zenodo_baseline.DATA_DIR", zenodo_dir):
        with patch("src.zenodo_baseline.requests.get") as mock_get:
            from src.zenodo_baseline import fetch
            fetch(force_refresh=False)
            mock_get.assert_not_called()
