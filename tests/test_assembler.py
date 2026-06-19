import io
import json
from pathlib import Path
from unittest.mock import patch

import openpyxl
import pytest


def _make_xlsx(ror_urls):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["name", "ROR"])
    for u in ror_urls:
        ws.append(["Org", u])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_assemble_produces_parquet(tmp_path, ror_page_nl):
    raw = tmp_path / "raw"
    (raw / "ror").mkdir(parents=True)
    (raw / "ror" / "page_NL_001.json").write_text(json.dumps(ror_page_nl))
    (raw / "zenodo").mkdir()
    (raw / "zenodo" / "nl-orgs-baseline.xlsx").write_bytes(
        _make_xlsx(["https://ror.org/04dkp9463"])
    )
    (raw / "zenodo" / "_metadata.json").write_text(
        '{"fetched_at":"x","record_count":1,"source_url":"x"}'
    )
    for d in ["openalex", "openaire", "barcelona", "alei", "pic"]:
        (raw / d).mkdir(exist_ok=True)
    (raw / "barcelona" / "signatories.csv").write_text(
        "ror_id,organisation_name,country\nhttps://ror.org/04dkp9463,VU,NL\n"
    )
    curated = tmp_path / "curated"
    curated.mkdir()
    for name in [
        "surf_members", "ukb_members", "shb_members", "unl_members",
        "umcnl_members", "vh_members", "knaw_institutes", "nwoi_institutes",
        "openaire_members",
    ]:
        (curated / f"{name}.csv").write_text("ror_id_url,name\n")

    out_parquet = tmp_path / "out.parquet"
    out_csv = tmp_path / "out.csv"

    # Pre-import all modules so patch() can resolve their attributes
    import src.assembler
    import src.ror_fetcher
    import src.zenodo_baseline
    import src.barcelona
    import src.openalex
    import src.openaire
    import src.memberships

    with patch("src.assembler.RAW_DIR", raw), \
         patch("src.assembler.CURATED_DIR", curated), \
         patch("src.assembler.OUT_PARQUET", out_parquet), \
         patch("src.assembler.OUT_CSV", out_csv), \
         patch("src.ror_fetcher.DATA_DIR", raw / "ror"), \
         patch("src.zenodo_baseline.DATA_DIR", raw / "zenodo"), \
         patch("src.barcelona.DATA_DIR", raw / "barcelona"), \
         patch("src.barcelona.CSV_PATH", raw / "barcelona" / "signatories.csv"), \
         patch("src.openalex.DATA_DIR", raw / "openalex"), \
         patch("src.openaire.DATA_DIR", raw / "openaire"), \
         patch("src.memberships.CURATED_DIR", curated):
        from src.assembler import fetch
        result = fetch(force_refresh=True)

    assert result["record_count"] == 1
    assert out_parquet.exists()
    assert out_csv.exists()

    import pandas as pd
    df = pd.read_parquet(out_parquet)
    assert "ror_id" in df.columns
    assert "is_barcelona_signatory" in df.columns
    assert "alei_id" in df.columns
    assert "pic_id" in df.columns
    assert bool(df.iloc[0]["ori_base_org"]) is True
