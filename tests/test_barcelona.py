import csv
import io
from pathlib import Path
from unittest.mock import patch, MagicMock


SAMPLE_CSV = """ror_id,organisation_name,country
https://ror.org/04dkp9463,Vrije Universiteit Amsterdam,Netherlands
,Some Other Org Without ROR,Netherlands
"""


def test_load_results_by_ror(tmp_path):
    bdir = tmp_path / "barcelona"
    bdir.mkdir()
    (bdir / "signatories.csv").write_text(SAMPLE_CSV)
    with patch("src.barcelona.DATA_DIR", bdir):
        from src.barcelona import load_results
        orgs = [
            {"ror_id_url": "https://ror.org/04dkp9463", "name": "Vrije Universiteit Amsterdam"},
            {"ror_id_url": "https://ror.org/notinlist", "name": "Unknown Org"},
        ]
        results = load_results(orgs)
    assert results["https://ror.org/04dkp9463"] is True
    assert results["https://ror.org/notinlist"] is False


def test_load_results_fuzzy_fallback(tmp_path):
    bdir = tmp_path / "barcelona"
    bdir.mkdir()
    csv_content = "ror_id,organisation_name,country\n,Delft University of Technology,Netherlands\n"
    (bdir / "signatories.csv").write_text(csv_content)
    with patch("src.barcelona.DATA_DIR", bdir):
        from src.barcelona import load_results
        orgs = [{"ror_id_url": "https://ror.org/02w4jbg70", "name": "Delft University of Technology"}]
        results = load_results(orgs)
    assert results["https://ror.org/02w4jbg70"] is True
