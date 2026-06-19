# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest"]
# ///
import json
from pathlib import Path
import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def ror_page_nl():
    return json.loads((FIXTURES / "ror_page_NL.json").read_text())


@pytest.fixture
def tmp_raw(tmp_path):
    (tmp_path / "ror").mkdir(parents=True)
    (tmp_path / "zenodo").mkdir(parents=True)
    (tmp_path / "openalex").mkdir(parents=True)
    (tmp_path / "openaire").mkdir(parents=True)
    (tmp_path / "barcelona").mkdir(parents=True)
    return tmp_path
