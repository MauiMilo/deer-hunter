from datetime import date

import pytest
import yaml

from deerscout.config import DATA_DIR
from deerscout.wmu import lookup, normalize, regulation_unit


@pytest.mark.parametrize(
    "name,units,conf",
    [
        ("Pittsburg", ("A",), "town-wide"),
        ("Pittsburg town", ("A",), "town-wide"),
        ("Second College grant", ("A",), "town-wide"),
        ("Dix's grant", ("A",), "town-wide"),
        ("Atkinson and Gilmanton Academy grant", ("A",), "town-wide"),
        ("Columbia", ("B",), "town-wide"),
        ("Colebrook", ("A", "B"), "split-town"),
        ("Wentworth's location", ("A", "C2"), "split-town"),
        ("Concord", (), "unknown"),
        (None, (), "unknown"),
    ],
)
def test_wmu_lookup(name, units, conf):
    r = lookup(name)
    assert r.units == units
    assert r.confidence == conf


def test_normalize():
    assert normalize("Dix's Grant") == "dixs"
    assert normalize("Atkinson & Gilmanton Academy Grant") == "atkinson and gilmanton"


def test_regulations_file_is_consistent():
    regs = yaml.safe_load((DATA_DIR / "regulations" / "nh-deer-2026.yaml").read_text())
    assert regs["legal_hours"]["before_sunrise_min"] == 30
    for s in regs["seasons"]:
        start, end = date.fromisoformat(s["start"]), date.fromisoformat(s["end"])
        assert start <= end, s
        assert s["method"] in {"archery", "youth", "muzzleloader", "firearm"}
        assert s["deer"] in regs["definitions"]
        assert s["units"]
    a_archery = [s for s in regs["seasons"] if s["method"] == "archery" and "A" in s["units"]]
    assert a_archery[0]["end"] == "2026-12-08"
    # firearm "any deer" day and antlered-only days must not overlap within a unit
    for unit in ("A", "B"):
        fa = sorted(
            (date.fromisoformat(s["start"]), date.fromisoformat(s["end"]))
            for s in regs["seasons"]
            if s["method"] == "firearm" and unit in s["units"]
        )
        for (s1, e1), (s2, e2) in zip(fa, fa[1:]):
            assert e1 < s2


def test_map_subunits_map_to_regulation_units():
    known = {"A", "B", "C1", "C2", "D1", "E"}
    assert regulation_unit("A1", known) == "A"
    assert regulation_unit("A2", known) == "A"
    assert regulation_unit("C1", known) == "C1"
    assert regulation_unit("e", known) == "E"
    assert regulation_unit("D2E", known) == "D2E"  # not a letter+digits subunit; kept as is
    assert regulation_unit("A1", None) == "A1"


def test_every_coos_unit_has_each_season():
    regs = yaml.safe_load((DATA_DIR / "regulations" / "nh-deer-2026.yaml").read_text())
    for unit in ("A", "B", "C1", "C2", "D1", "E"):
        for method in ("archery", "muzzleloader", "firearm", "youth"):
            assert any(unit in s["units"] and s["method"] == method for s in regs["seasons"]), (unit, method)


def test_crossbow_note_lists_the_exceptions():
    regs = yaml.safe_load((DATA_DIR / "regulations" / "nh-deer-2026.yaml").read_text())
    note = regs["method_notes"]["crossbow"]
    for must in ("68", "Disabled Crossbow Permit", "Youth Deer Weekend", "firearms season", "muzzleloader season", "E and F)"):
        assert must in note, must


MERRIMACK_UNITS = ("I1", "I2", "J1", "J2", "K", "L", "M", "H1", "H2", "G1", "G2", "F", "D2E", "D2W")


def test_every_statewide_unit_has_each_season():
    regs = yaml.safe_load((DATA_DIR / "regulations" / "nh-deer-2026.yaml").read_text())
    for unit in MERRIMACK_UNITS:
        for method in ("archery", "muzzleloader", "firearm", "youth"):
            assert any(unit in s["units"] and s["method"] == method for s in regs["seasons"]), (unit, method)


def test_no_unit_has_overlapping_seasons_of_one_method():
    regs = yaml.safe_load((DATA_DIR / "regulations" / "nh-deer-2026.yaml").read_text())
    units = {u for s in regs["seasons"] for u in s["units"]}
    for unit in units:
        for method in ("archery", "muzzleloader", "firearm"):
            spans = sorted(
                (date.fromisoformat(s["start"]), date.fromisoformat(s["end"]))
                for s in regs["seasons"]
                if s["method"] == method and unit in s["units"]
            )
            for (s1, e1), (s2, e2) in zip(spans, spans[1:]):
                assert e1 < s2, (unit, method)


def test_concord_area_unit_dates():
    regs = yaml.safe_load((DATA_DIR / "regulations" / "nh-deer-2026.yaml").read_text())

    def spans(unit, method):
        return [(s["start"], s["end"], s["deer"]) for s in regs["seasons"] if s["method"] == method and unit in s["units"]]

    assert spans("K", "archery") == [("2026-09-15", "2026-12-15", "any")]
    assert spans("L", "muzzleloader") == [("2026-10-31", "2026-11-10", "any")]
    assert spans("L", "firearm") == [("2026-11-11", "2026-11-22", "any"), ("2026-11-23", "2026-12-06", "antlered")]
    assert spans("I1", "firearm") == [("2026-11-11", "2026-11-13", "any"), ("2026-11-14", "2026-12-06", "antlered")]
    # A (the far north) is the only unit whose archery season ends early.
    assert [u for u in {u for s in regs["seasons"] if s["method"] == "archery" for u in s["units"]} if spans(u, "archery")[0][1] != "2026-12-15"] == ["A"]


def test_merrimack_region_is_defined():
    from deerscout.config import MERRIMACK, REGIONS

    assert REGIONS["merrimack"] is MERRIMACK
    assert MERRIMACK.county_geoid == "33013"
    lon_min, lat_min, lon_max, lat_max = MERRIMACK.envelope
    assert lon_min < -71.54 < lon_max and lat_min < 43.21 < lat_max  # Concord is inside
    assert "Concord" in MERRIMACK.focus_towns
