"""Deer abundance (adult buck kill per square mile) from NH Fish and Game's report."""

import pytest
import yaml

from deerscout import build, factors
from deerscout.scoring import load_config
from deerscout.config import DATA_DIR

SRC = {"title": "2025 NH Wildlife Harvest Summary (deer)", "url": "https://www.wildlife.nh.gov/x.pdf", "retrieved": "2026-11-19", "page": "p. 12"}


def write(tmp_path, **doc):
    p = tmp_path / "abundance.yaml"
    p.write_text(yaml.safe_dump(doc))
    return p


def test_missing_file_means_no_numbers(tmp_path):
    assert build.load_abundance(tmp_path / "nope.yaml") == {}


def test_numbers_without_a_source_are_refused(tmp_path):
    with pytest.raises(ValueError, match="source"):
        build.load_abundance(write(tmp_path, year=2025, wmus=[{"wmu": "K", "buck_kill_per_sqmi": 2.1}]))


def test_bad_numbers_are_refused(tmp_path):
    with pytest.raises(ValueError, match="buck_kill_per_sqmi"):
        build.load_abundance(write(tmp_path, source=SRC, year=2025, wmus=[{"wmu": "K", "buck_kill_per_sqmi": "lots"}]))


def test_town_figure_wins_over_wmu_and_split_blocks_take_the_lower(tmp_path):
    ab = build.load_abundance(
        write(
            tmp_path,
            source=SRC,
            year=2025,
            wmus=[{"wmu": "K", "buck_kill_per_sqmi": 2.1}, {"wmu": "I2", "buck_kill_per_sqmi": 1.4}],
            towns=[{"town": "Hopkinton", "buck_kill_per_sqmi": 2.6}],
        )
    )
    assert build.abundance_for(ab, "Hopkinton", ["K"])["buck_kill_per_sqmi"] == 2.6
    assert build.abundance_for(ab, "hopkinton", ["K"])["level"] == "town"
    assert build.abundance_for(ab, "Weare", ["K"])["buck_kill_per_sqmi"] == 2.1
    assert build.abundance_for(ab, "Weare", ["K", "I2"])["buck_kill_per_sqmi"] == 1.4
    assert build.abundance_for(ab, None, ["A"]) is None
    assert ab["wmu:k"]["source"] == SRC and ab["wmu:k"]["year"] == 2025


def test_factor_scores_and_cites_its_source():
    cfg = load_config(DATA_DIR / "scoring.yaml")
    row = {"wmu": "K", "level": "wmu", "buck_kill_per_sqmi": 2.5, "year": 2025, "source": SRC}
    r = factors.abundance_factor({"abundance": row}, cfg)
    assert r.value == pytest.approx(100)
    assert r.signals["source"] == SRC and r.signals["where"] == "WMU K"
    assert any("2025 NH Wildlife Harvest Summary" in e for e in r.evidence)
    low = factors.abundance_factor({"abundance": {**row, "buck_kill_per_sqmi": 0.3}}, cfg)
    assert low.value == pytest.approx(0)
    town = factors.abundance_factor({"abundance": {**row, "level": "town", "town": "Weare"}}, cfg)
    assert town.evidence[0].startswith("Weare (town)")


def test_no_abundance_means_the_factor_is_skipped():
    cfg = load_config(DATA_DIR / "scoring.yaml")
    r = factors.abundance_factor({}, cfg)
    assert r.value is None
