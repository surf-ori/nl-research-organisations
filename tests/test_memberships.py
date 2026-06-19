from pathlib import Path
from unittest.mock import patch


def setup_curated(tmp_path):
    c = tmp_path / "curated"
    c.mkdir()
    (c / "surf_members.csv").write_text("ror_id_url,name,member_type\nhttps://ror.org/04dkp9463,VU Amsterdam,instelling\n")
    for name in ["ukb_members", "shb_members", "unl_members", "umcnl_members", "vh_members", "knaw_institutes", "nwoi_institutes", "openaire_members"]:
        (c / f"{name}.csv").write_text("ror_id_url,name\n")
    return c


def test_load_memberships(tmp_path):
    curated = setup_curated(tmp_path)
    with patch("src.memberships.CURATED_DIR", curated):
        from src.memberships import load_memberships
        result = load_memberships(["https://ror.org/04dkp9463", "https://ror.org/unknown"])
    vu = result["https://ror.org/04dkp9463"]
    assert vu["is_surf_member"] is True
    assert vu["surf_member_type"] == "instelling"
    unknown = result["https://ror.org/unknown"]
    assert unknown["is_surf_member"] is False
    assert unknown["surf_member_type"] is None
