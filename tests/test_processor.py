import json
from unittest.mock import patch

import pandas as pd
import pytest


def test_fetch_builds_ror_parquet_and_copies_metadata(tmp_path, ror_page_nl):
    raw = tmp_path / "raw"
    processed = tmp_path / "processed"
    curated = tmp_path / "curated"
    (raw / "ror").mkdir(parents=True)
    (raw / "ror" / "page_NL_001.json").write_text(json.dumps(ror_page_nl))
    (raw / "ror" / "_metadata.json").write_text(
        json.dumps({"fetched_at": "2026-01-01T00:00:00", "record_count": 1, "source_url": "x"})
    )
    curated.mkdir()

    import src.processor
    import src.ror_fetcher
    import src.memberships

    with patch("src.processor.RAW_DIR", raw), \
         patch("src.processor.CURATED_DIR", curated), \
         patch("src.processor.PROCESSED_DIR", processed), \
         patch("src.ror_fetcher.DATA_DIR", raw / "ror"), \
         patch("src.memberships.CURATED_DIR", curated):
        from src.processor import fetch
        result = fetch()

    assert (processed / "ror.parquet").exists()
    assert (processed / "ror_metadata.json").exists()
    meta = json.loads((processed / "ror_metadata.json").read_text())
    assert meta["record_count"] == 1
    df = pd.read_parquet(processed / "ror.parquet")
    assert len(df) == 1
    assert result["output_path"] == str(processed)


def test_fetch_converts_curated_csv_to_parquet_twin(tmp_path):
    raw = tmp_path / "raw"
    processed = tmp_path / "processed"
    curated = tmp_path / "curated"
    (raw / "ror").mkdir(parents=True)
    curated.mkdir()
    (curated / "ukb_members.csv").write_text("ror_id_url,name\nhttps://ror.org/x,Org\n")

    import src.processor
    import src.ror_fetcher
    import src.memberships

    with patch("src.processor.RAW_DIR", raw), \
         patch("src.processor.CURATED_DIR", curated), \
         patch("src.processor.PROCESSED_DIR", processed), \
         patch("src.ror_fetcher.DATA_DIR", raw / "ror"), \
         patch("src.memberships.CURATED_DIR", curated):
        from src.processor import fetch
        fetch()

    assert (processed / "ukb_members.parquet").exists()
    df = pd.read_parquet(processed / "ukb_members.parquet")
    assert df.iloc[0]["name"] == "Org"


def test_fetch_flattens_alei_matches(tmp_path):
    raw = tmp_path / "raw"
    processed = tmp_path / "processed"
    curated = tmp_path / "curated"
    (raw / "ror").mkdir(parents=True)
    (raw / "alei").mkdir(parents=True)
    curated.mkdir()
    (raw / "alei" / "008xxew50.json").write_text(json.dumps(
        [{"dossiernummer": "41208034", "handelsnaam": "Vrije Universiteit Amsterdam"}]
    ))

    import src.processor
    import src.ror_fetcher
    import src.memberships

    with patch("src.processor.RAW_DIR", raw), \
         patch("src.processor.CURATED_DIR", curated), \
         patch("src.processor.PROCESSED_DIR", processed), \
         patch("src.ror_fetcher.DATA_DIR", raw / "ror"), \
         patch("src.memberships.CURATED_DIR", curated):
        from src.processor import fetch
        fetch()

    assert (processed / "alei.parquet").exists()
    df = pd.read_parquet(processed / "alei.parquet")
    assert df.iloc[0]["ror_id_url"] == "https://ror.org/008xxew50"
    assert df.iloc[0]["dossiernummer"] == "41208034"


def test_fetch_reads_duo_dump_format(tmp_path):
    raw = tmp_path / "raw"
    processed = tmp_path / "processed"
    curated = tmp_path / "curated"
    (raw / "ror").mkdir(parents=True)
    (raw / "duo").mkdir(parents=True)
    curated.mkdir()
    (raw / "duo" / "ho.json").write_text(json.dumps({
        "fields": [{"id": "INSTELLINGSNAAM"}, {"id": "INSTELLINGSCODE"}],
        "records": [["Vrije Universiteit Amsterdam", "21160"]],
    }))

    import src.processor
    import src.ror_fetcher
    import src.memberships

    with patch("src.processor.RAW_DIR", raw), \
         patch("src.processor.CURATED_DIR", curated), \
         patch("src.processor.PROCESSED_DIR", processed), \
         patch("src.ror_fetcher.DATA_DIR", raw / "ror"), \
         patch("src.memberships.CURATED_DIR", curated):
        from src.processor import fetch
        fetch()

    assert (processed / "duo_ho.parquet").exists()
    df = pd.read_parquet(processed / "duo_ho.parquet")
    assert df.iloc[0]["INSTELLINGSNAAM"] == "Vrije Universiteit Amsterdam"


def test_fetch_skips_missing_sources_without_error(tmp_path):
    raw = tmp_path / "raw"
    processed = tmp_path / "processed"
    curated = tmp_path / "curated"
    (raw / "ror").mkdir(parents=True)
    curated.mkdir()

    import src.processor
    import src.ror_fetcher
    import src.memberships

    with patch("src.processor.RAW_DIR", raw), \
         patch("src.processor.CURATED_DIR", curated), \
         patch("src.processor.PROCESSED_DIR", processed), \
         patch("src.ror_fetcher.DATA_DIR", raw / "ror"), \
         patch("src.memberships.CURATED_DIR", curated):
        from src.processor import fetch
        result = fetch()

    assert result["record_count"] == 0
    assert not (processed / "ror.parquet").exists()
    assert not (processed / "zenodo.parquet").exists()
