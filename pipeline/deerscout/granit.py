"""Code tables for the GRANIT Conservation/Public Lands layer.

Source: "GRANIT Conservation/Public Lands Layer, Polygon Coding Standards" (rev. July 2022),
https://ftp.granit.unh.edu/d-cons/ConservationLandsStandard.pdf (retrieved 2026-10-08).
Only the agency codes needed so far are listed; unknown codes decode to "Agency code NNNNN".
"""

from __future__ import annotations

from typing import Any

STANDARD_URL = "https://ftp.granit.unh.edu/d-cons/ConservationLandsStandard.pdf"

PROTECTION_TYPE = {
    "AR": "Agricultural preservation restriction",
    "CE": "Conservation easement",
    "DR": "Deed restriction",
    "FE": "Flowage rights or easement",
    "FO": "Fee ownership",
    "HP": "Historic preservation easement",
    "LE": "Long-term lease",
    "PE": "Protective easement (water supply)",
    "RV": "Reverter",
    "RW": "Right of way",
    "SA": "Set-aside open space in a development",
    "SE": "Scenic easement",
}

AGENCY_TYPE = {1: "Municipal/County", 2: "Federal", 3: "State", 4: "Other public", 5: "Private"}

OWNER_TYPE = {
    1: "Municipal",
    2: "Federal",
    3: "State",
    4: "Other public",
    5: "Private",
    6: "County",
    9: "Unknown",
}

PUBLIC_ACCESS = {
    1: "Allowed (minor restrictions may apply)",
    2: "Restricted to certain areas, times or members",
    3: "Not allowed",
    4: "Unknown",
    5: "No response to access survey",
}

MANAGEMENT_STATUS = {
    1: "Fully protected, managed for natural processes",
    2: "Fully protected, mostly natural, some limited uses",
    3: "Protected, allows timber harvest or other extraction",
    4: "Mostly unprotected, or agriculture / active recreation",
    9: "Unknown",
}

BOUNDARY_ACCURACY = {
    1: "Very good (survey)",
    2: "Good (good tax map or imperfect survey)",
    3: "Fair (poor tax map; some lines questionable)",
    4: "Poor (location approximate only)",
    5: "Unknown",
}

PROGRAM = {
    0: "None noted",
    1: "Land Conservation Investment Program (LCIP)",
    2: "Agricultural preservation",
    3: "Land & Water Conservation Fund",
    4: "Appalachian Trail",
    7: "USFS Forest Legacy Program",
    10: "LCHIP",
    14: "Waterfowl Conservation Fund",
    99: "Other",
}

AGENCY = {
    20000: "US Government",
    21000: "US Fish & Wildlife Service",
    21100: "National Park Service",
    21200: "National Park Service (Appalachian Trail)",
    22000: "US Forest Service",
    22100: "USDA Natural Resources Conservation Service",
    23000: "US Army Corps of Engineers",
    30000: "State of New Hampshire",
    31000: "NH Dept. of Natural & Cultural Resources (formerly DRED)",
    32000: "NH Fish & Game",
    33000: "NH Dept. of Agriculture",
    35000: "NH Dept. of Environmental Services",
    36000: "NH Dept. of Transportation",
    51305: "Mahoosuc Land Trust",
    51500: "Northeast Wilderness Trust",
    51950: "Society for the Protection of NH Forests",
    52010: "The Nature Conservancy",
    52025: "Trust for Public Land",
    7000: "Coos County",
    7020: "City of Berlin",
    7040: "Town of Clarksville",
    7045: "Town of Colebrook",
    7050: "Town of Columbia",
    7085: "Town of Errol",
    7095: "Town of Gorham",
    7110: "Town of Jefferson",
    7120: "Town of Lancaster",
    7135: "Town of Milan",
    7160: "Town of Pittsburg",
    7165: "Town of Randolph",
    7180: "Town of Shelburne",
    7190: "Town of Stewartstown",
    7195: "Town of Stratford",
    7215: "Town of Whitefield",
}


def _int(v: Any) -> int | None:
    try:
        if v is None or (isinstance(v, str) and not v.strip()):
            return None
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _str(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def agency_name(code: Any) -> str | None:
    c = _int(code)
    if c is None or c == 0:
        return None
    return AGENCY.get(c, f"Agency code {c:05d}")


def decode(props: dict[str, Any]) -> dict[str, Any]:
    """Turn raw GRANIT attributes into readable fields. Raw codes are kept alongside."""
    pptype = _str(props.get("PPTYPE"))
    owner = _int(props.get("OWNERTYPE"))
    access = _int(props.get("ACCESS"))
    mstatus = _int(props.get("MSTATUS"))
    acc = _int(props.get("ACCURACY"))
    prog = _int(props.get("PROGRAM"))
    return {
        "tract_id": _str(props.get("TID")),
        "parent_id": _str(props.get("PID")),
        "name": _str(props.get("NAME")) or "Unnamed conservation land",
        "alt_name": _str(props.get("NAMEALT")),
        "parent_name": _str(props.get("P_NAME")),
        "protection_type_code": pptype,
        "protection_type": PROTECTION_TYPE.get(pptype or "", pptype),
        "agency_code": _int(props.get("PPAGENCY")),
        "agency": agency_name(props.get("PPAGENCY")),
        "secondary_agency": agency_name(props.get("SPAGENCY1")),
        "agency_type": AGENCY_TYPE.get(_int(props.get("PPAGENTYPE")) or -1),
        "owner_type_code": owner,
        "owner_type": OWNER_TYPE.get(owner or 9, "Unknown"),
        "public_access_code": access,
        "public_access": PUBLIC_ACCESS.get(access or 4, "Unknown"),
        "management_status_code": mstatus,
        "management_status": MANAGEMENT_STATUS.get(mstatus or 9, "Unknown"),
        "gap_status": _str(props.get("GAP_STATUS")),
        "program_code": prog,
        "program": PROGRAM.get(prog, f"Program {prog}") if prog is not None else None,
        "boundary_accuracy_code": acc,
        "boundary_accuracy": BOUNDARY_ACCURACY.get(acc or 5, "Unknown"),
        "reported_acres": _float_or_none(props.get("RSIZE")),
        "granit_calc_acres": _float_or_none(props.get("CSIZE")),
        "parent_acres": _float_or_none(props.get("P_CSIZE")),
        "date_added": _str(props.get("DATEADDED")),
        "date_altered": _str(props.get("DATEALTER")),
        "notes": " ".join(n for n in (_str(props.get(f"NOTES{i}")) for i in range(1, 5)) if n) or None,
    }


def _float_or_none(v: Any) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f < 0 else f  # -999 means "not reported"
