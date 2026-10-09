import pytest

from deerscout.access import AccessRules, RuleError
from deerscout.config import DATA_DIR


@pytest.fixture(scope="module")
def rules():
    return AccessRules.load(DATA_DIR / "access_rules.yaml", DATA_DIR / "verifications.yaml")


def prop(**kw):
    base = {
        "name": "Test Forest",
        "parent_name": None,
        "agency_code": 52010,
        "protection_type_code": "FO",
        "public_access_code": 1,
        "tract_id": "001-001  -001",
        "parent_id": "001-001  -",
    }
    base.update(kw)
    return base


def test_dncr_state_forest_is_verified_with_sources(rules):
    r = rules.evaluate(prop(name="Nash Stream Forest", agency_code=31000, protection_type_code="FO"))
    assert r.status == "verified"
    assert r.rule_id == "dncr-fee-land"
    assert r.sources and all(s["url"].startswith("https://") for s in r.sources)
    assert r.checked_on == "2026-10-09"


def test_dncr_named_exclusion_is_not_verified(rules):
    r = rules.evaluate(prop(name="Shieling State Forest", agency_code=31000, protection_type_code="FO"))
    assert r.status == "unknown"


def test_dncr_easement_is_not_auto_verified(rules):
    # An easement held by DNCR on private land is not the same as state-owned land.
    r = rules.evaluate(prop(name="Some Easement", agency_code=31000, protection_type_code="CE"))
    assert r.status == "unknown"


def test_no_public_access_is_prohibited(rules):
    r = rules.evaluate(prop(public_access_code=3))
    assert r.status == "prohibited"


def test_clhw_verified_even_when_granit_access_unknown(rules):
    r = rules.evaluate(
        prop(name="Connecticut Lakes Headwaters", parent_name="Connecticut Lakes Headwaters", agency_code=30000, protection_type_code="CE", public_access_code=4)
    )
    assert r.status == "verified"
    assert r.rule_id == "clhw-easement"
    assert any("camping" in x.lower() for x in r.restrictions)


def test_conflict_with_no_access_record_is_flagged(rules):
    r = rules.evaluate(prop(name="Connecticut Lakes Headwaters", public_access_code=3))
    assert r.status == "verified"
    assert r.notes and "conflicts" in r.notes[0]


def test_wmnf_and_umbagog(rules):
    assert rules.evaluate(prop(agency_code=22000, protection_type_code="FO")).status == "verified"
    assert rules.evaluate(prop(name="Lake Umbagog NWR", agency_code=21000)).status == "verified"
    r = rules.evaluate(prop(name="Pondicherry Unit of Silvio O Conte NFWR", agency_code=21000))
    assert r.status == "unknown"
    assert r.rule_id == "conte-pondicherry-division"


def test_fish_and_game_land_needs_checking(rules):
    r = rules.evaluate(prop(agency_code=32000))
    assert r.status == "unknown"
    assert "Fish and Game" in r.summary


def test_private_land_trust_defaults_to_unknown(rules):
    r = rules.evaluate(prop(agency_code=52010, public_access_code=1))
    assert r.status == "unknown"
    assert r.rule_id == "default"


def test_manual_verification_overrides_rules():
    doc = {
        "sources": {"s": {"title": "x", "url": "https://example.org", "retrieved": "2026-01-01"}},
        "rules": [{"id": "r", "status": "prohibited", "when": {"public_access_code": [3]}, "sources": ["s"]}],
        "default": {"status": "unknown", "summary": "", "sources": ["s"]},
    }
    ver = {
        "verifications": [
            {
                "match": {"parent_id": "001-001  -"},
                "status": "verified",
                "summary": "Town said yes",
                "source_title": "Call with town office",
                "checked_on": "2026-10-10",
            }
        ]
    }
    r = AccessRules(doc, ver).evaluate(prop(public_access_code=3))
    assert r.status == "verified"
    assert r.rule_id == "manual-verification"
    assert r.checked_on == "2026-10-10"


def test_verified_rule_without_source_is_rejected():
    doc = {"sources": {}, "rules": [{"id": "r", "status": "verified", "when": {}}], "default": {"status": "unknown"}}
    with pytest.raises(RuleError):
        AccessRules(doc)


def test_manual_verified_without_date_is_rejected():
    doc = {"sources": {}, "rules": [], "default": {"status": "unknown"}}
    with pytest.raises(RuleError):
        AccessRules(doc, {"verifications": [{"match": {"name": "x"}, "status": "verified", "source_title": "t"}]})


def test_bad_status_is_rejected():
    doc = {"sources": {}, "rules": [{"id": "r", "status": "maybe"}], "default": {"status": "unknown"}}
    with pytest.raises(RuleError):
        AccessRules(doc)


def test_general_restrictions_are_cited(rules):
    g = rules.general_restrictions()
    assert any("not for legal use" in x["text"] for x in g)
    assert all(x["sources"] for x in g)


def test_fish_and_game_listed_wma_is_verified(rules):
    r = rules.evaluate(prop(name="Brown WMA", agency_code=32000))
    assert r.status == "verified"
    assert r.rule_id == "nhfg-listed-lands"


def test_connecticut_lakes_natural_area(rules):
    r = rules.evaluate(prop(name="Connecticut Lakes Natural Area", agency_code=32000))
    assert r.status == "verified"
    assert any("bait" in x.lower() for x in r.restrictions)


def test_unlisted_fish_and_game_land_stays_unknown(rules):
    assert rules.evaluate(prop(name="Connecticut River Drivers WMA", agency_code=32000)).status == "unknown"


def test_dartmouth_grant_carries_its_age_warning(rules):
    r = rules.evaluate(prop(name="Second College Grant", agency_code=50420))
    assert r.status == "verified"
    assert any("2012" in n for n in r.notes)


def test_dartmouth_grant_is_walk_in_for_the_public(rules):
    r = rules.evaluate(prop(name="Second College Grant", agency_code=50420))
    text = " ".join(r.restrictions)
    assert "Dartmouth-affiliated" in text and "Oct 1 - Nov 28" in text
    assert {s["id"] for s in r.sources} == {"dartmouth_grant", "dartmouth_grant_page"}


def test_pondicherry_wildlife_refuge_is_closed(rules):
    # Fish and Game lists it as closed, even though GRANIT codes public access as allowed.
    r = rules.evaluate(prop(name="Pondicherry Wildlife Refuge", agency_code=50130, protection_type_code="CE", public_access_code=1))
    assert r.status == "prohibited"
    assert r.sources[0]["id"] == "nhfg_state_lands_faq"


def test_state_historic_sites_are_closed(rules):
    r = rules.evaluate(prop(name="Fort Stark State Historic Site", agency_code=31000, protection_type_code="FO"))
    assert r.status == "prohibited"


def test_weeks_state_park_is_not_auto_verified(rules):
    # It contains a state historic site, where hunting is not allowed.
    r = rules.evaluate(prop(name="Weeks State Park", agency_code=31000, protection_type_code="FO"))
    assert r.status == "unknown"
    assert r.rule_id == "weeks-state-park"
