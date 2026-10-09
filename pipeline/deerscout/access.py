"""Decide each property's hunting-permission status from cited rules.

Legal status is kept completely separate from the habitat score. Three outcomes:
  verified   - an official source says hunting is allowed (with source and date)
  prohibited - a source says it is not allowed / no public access
  unknown    - nothing checked yet confirms either way (a research candidate)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

STATUSES = ("verified", "prohibited", "unknown")


@dataclass
class AccessResult:
    status: str
    rule_id: str
    summary: str
    restrictions: list[str] = field(default_factory=list)
    sources: list[dict[str, Any]] = field(default_factory=list)
    checked_on: str | None = None
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "rule_id": self.rule_id,
            "summary": self.summary,
            "restrictions": self.restrictions,
            "sources": self.sources,
            "checked_on": self.checked_on,
            "notes": self.notes,
        }


class RuleError(ValueError):
    pass


def _contains(hay: Any, needle: str) -> bool:
    return hay is not None and needle.lower() in str(hay).lower()


class AccessRules:
    def __init__(self, rules_doc: dict[str, Any], verifications_doc: dict[str, Any] | None = None):
        self.sources: dict[str, dict[str, Any]] = rules_doc.get("sources", {})
        self.rules: list[dict[str, Any]] = rules_doc.get("rules", [])
        self.default: dict[str, Any] = rules_doc.get("default", {"status": "unknown", "summary": ""})
        self.general = rules_doc.get("general_restrictions", [])
        self.verifications: list[dict[str, Any]] = (verifications_doc or {}).get("verifications") or []
        self._validate()

    @classmethod
    def load(cls, rules_path: Path, verifications_path: Path | None = None) -> "AccessRules":
        rules = yaml.safe_load(rules_path.read_text())
        ver = yaml.safe_load(verifications_path.read_text()) if verifications_path and verifications_path.exists() else {}
        return cls(rules, ver)

    def _validate(self) -> None:
        seen = set()
        for r in self.rules + [dict(self.default, id="default")]:
            rid = r.get("id")
            if rid in seen:
                raise RuleError(f"duplicate rule id {rid}")
            seen.add(rid)
            if r.get("status") not in STATUSES:
                raise RuleError(f"rule {rid}: bad status {r.get('status')!r}")
            if r.get("status") == "verified" and not r.get("sources"):
                raise RuleError(f"rule {rid}: a 'verified' rule must cite at least one source")
            for s in r.get("sources", []):
                if s not in self.sources:
                    raise RuleError(f"rule {rid}: unknown source {s!r}")
        for v in self.verifications:
            if v.get("status") not in STATUSES:
                raise RuleError(f"verification {v.get('match')}: bad status {v.get('status')!r}")
            if v.get("status") == "verified" and not (v.get("source_title") and v.get("checked_on")):
                raise RuleError(
                    f"verification {v.get('match')}: 'verified' needs source_title and checked_on"
                )

    def _cite(self, keys: list[str]) -> list[dict[str, Any]]:
        out = []
        for k in keys:
            s = self.sources[k]
            out.append(
                {
                    "id": k,
                    "title": s.get("title"),
                    "url": s.get("url"),
                    "publisher": s.get("publisher"),
                    "source_date": s.get("source_date"),
                    "retrieved": s.get("retrieved"),
                }
            )
        return out

    @staticmethod
    def _rule_matches(rule: dict[str, Any], p: dict[str, Any]) -> bool:
        when = rule.get("when", {})
        for key in ("agency_code", "protection_type_code", "public_access_code"):
            if key in when and p.get(key) not in when[key]:
                return False
        if "name_contains" in when and not _contains(p.get("name"), when["name_contains"]):
            return False
        if "parent_name_contains" in when and not (
            _contains(p.get("parent_name"), when["parent_name_contains"])
            or _contains(p.get("name"), when["parent_name_contains"])
        ):
            return False
        for bad in rule.get("name_excludes", []) or []:
            if _contains(p.get("name"), bad) or _contains(p.get("parent_name"), bad):
                return False
        return True

    @staticmethod
    def _verification_matches(v: dict[str, Any], p: dict[str, Any]) -> bool:
        m = v.get("match") or {}
        if not m:
            return False
        for key in ("tract_id", "parent_id", "name"):
            if key in m and str(m[key]).strip() != str(p.get(key) or "").strip():
                return False
        return True

    def general_restrictions(self) -> list[dict[str, Any]]:
        return [{"text": g["text"], "sources": self._cite(g.get("sources", []))} for g in self.general]

    def evaluate(self, p: dict[str, Any]) -> AccessResult:
        for v in self.verifications:
            if self._verification_matches(v, p):
                src = [
                    {
                        "id": "manual",
                        "title": v.get("source_title"),
                        "url": v.get("source_url") or None,
                        "publisher": "Your own check",
                        "source_date": v.get("checked_on"),
                        "retrieved": v.get("checked_on"),
                    }
                ]
                return AccessResult(
                    status=v["status"],
                    rule_id="manual-verification",
                    summary=v.get("summary") or "Checked by you.",
                    restrictions=list(v.get("restrictions") or []),
                    sources=src,
                    checked_on=v.get("checked_on"),
                )

        for rule in self.rules:
            if self._rule_matches(rule, p):
                result = self._result(rule)
                # A permissive agency rule never hides a "no public access" record.
                if result.status == "verified" and p.get("public_access_code") == 3:
                    result.notes.append(
                        "GRANIT records public access as 'not allowed' for this tract, which conflicts with the rule above. Verify before hunting."
                    )
                return result
        return self._result(dict(self.default, id="default"))

    def _result(self, rule: dict[str, Any]) -> AccessResult:
        cited = self._cite(rule.get("sources", []))
        dates = [s.get("retrieved") for s in cited if s.get("retrieved")]
        return AccessResult(
            status=rule["status"],
            rule_id=rule["id"],
            summary=rule.get("summary", ""),
            restrictions=list(rule.get("restrictions") or []),
            sources=cited,
            checked_on=max(dates) if dates else None,
        )
