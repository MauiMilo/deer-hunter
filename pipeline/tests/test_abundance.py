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


# ---------------------------------------------------------------- the real numbers (2025 summary)

REAL = yaml.safe_load((DATA_DIR / "abundance.yaml").read_text())


def test_real_file_covers_every_wmu_and_cites_the_report():
    regs = yaml.safe_load((DATA_DIR / "regulations" / "nh-deer-2026.yaml").read_text())
    units = {u for s in regs["seasons"] for u in s["units"]}
    assert {r["wmu"] for r in REAL["wmus"]} == units
    src = REAL["source"]
    assert src["title"] == "2025 New Hampshire Wildlife Harvest Summary"
    assert src["url"].startswith("https://www.wildlife.nh.gov/") and src["page"] and src["retrieved"]


def test_real_values_recompute_from_the_reports_own_numbers():
    habitat_total = 0.0
    for r in REAL["wmus"]:
        assert r["two_year_average"] == (r["adult_bucks_2024"] + r["adult_bucks_2025"]) / 2, r["wmu"]
        habitat = r["total_kill_2025"] / r["total_kpsm_2025"]
        habitat_total += habitat
        assert r["habitat_sq_mi"] == round(habitat), r["wmu"]
        assert r["buck_kill_per_sqmi"] == pytest.approx(r["two_year_average"] / habitat, abs=0.006), r["wmu"]
    # The units' habitat adds up to the report's statewide figure (14,387 deer / 1.81 per sq mi).
    assert habitat_total == pytest.approx(14387 / 1.81, rel=0.01)


def test_real_values_match_fish_and_game_current_levels_and_spot_values():
    by = {r["wmu"]: r for r in REAL["wmus"]}
    # "Current level" (2-year average adult buck kill), report p. 6
    for wmu, level in {"A": 366, "E": 112, "K": 770, "L": 764, "M": 963, "J2": 1069, "D2E": 24}.items():
        assert round(by[wmu]["two_year_average"] + 0.001) == level, wmu
    assert by["A"]["buck_kill_per_sqmi"] == 0.66
    assert by["K"]["buck_kill_per_sqmi"] == 1.38
    assert by["M"]["buck_kill_per_sqmi"] == 2.14


def test_real_file_loads_for_scoring():
    ab = build.load_abundance()
    assert ab["wmu:k"]["buck_kill_per_sqmi"] == 1.38
    assert ab["wmu:k"]["period"] == "2024-2025 average"
    assert ab["wmu:k"]["source"]["title"] == "2025 New Hampshire Wildlife Harvest Summary"
    assert not any(k.startswith("town:") for k in ab)
