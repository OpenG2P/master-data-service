"""Rules a geography change event (lineage) must satisfy — one implementation.

Used by the API (services/g2p_catalogue_geo_service.py, when an event is
recorded and again when a draft is submitted or published) and by the
country-pack loader (docker/db-seed/load_geo_pack.py, for the events of a
pack's changes.json), so a pack cannot publish lineage the API would refuse.

Pure Python, standard library only: the loader runs in a small image without
the API's dependencies, and gets this file copied next to it (see the db-seed
Dockerfile). Units are passed in as mappings ``{unit_id: unit}`` where a unit
is an object or a dict with ``status``, ``level_id``, ``name`` and
``parent_unit_id``.
"""

from __future__ import annotations

from typing import Any, Iterable, List, Mapping, Optional, Sequence, Tuple

CREATE = "CREATE"
RETIRE = "RETIRE"
RENAME = "RENAME"
RECODE = "RECODE"
SPLIT = "SPLIT"
MERGE = "MERGE"
REPARENT = "REPARENT"
BOUNDARY_CHANGE = "BOUNDARY_CHANGE"

ALL_TYPES = (CREATE, RETIRE, RENAME, RECODE, SPLIT, MERGE, REPARENT, BOUNDARY_CHANGE)
# Events after which a unit does not continue as itself.
TERMINAL = frozenset({RETIRE, SPLIT, MERGE, RECODE})

ACTIVE = "ACTIVE"
RETIRED = "RETIRED"


class GeoChangeRuleError(Exception):
    """``code`` is G2P-CAT-400 (invalid event) or G2P-CAT-409 (conflicts with another event)."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


def _get(unit: Any, key: str) -> Any:
    if isinstance(unit, Mapping):
        return unit.get(key)
    return getattr(unit, key, None)


def check_geo_change(
    change_type: str,
    from_units: Sequence[str],
    to_units: Sequence[str],
    *,
    base_version_no: Optional[int],
    base_units: Mapping[str, Any],
    draft_units: Mapping[str, Any],
    other_terminal_events: Iterable[Tuple[Any, str, Sequence[str]]] = (),
) -> Tuple[List[str], List[str]]:
    """Validate one event of a draft against its base; return (from_units, to_units) cleaned.

    ``other_terminal_events``: (change_id, change_type, from_units) of the
    draft's OTHER explicit terminal events — a unit can end only once.
    """
    if change_type not in ALL_TYPES:
        raise GeoChangeRuleError("G2P-CAT-400", f"unknown change_type {change_type}")
    if base_version_no is None:
        raise GeoChangeRuleError(
            "G2P-CAT-400", "the first geography version has no base to record changes against"
        )
    B, D = base_units, draft_units
    frm = [u.strip() for u in (from_units or []) if u and u.strip()]
    to = [u.strip() for u in (to_units or []) if u and u.strip()]
    if len(set(frm)) != len(frm) or len(set(to)) != len(to):
        raise GeoChangeRuleError("G2P-CAT-400", "from_units / to_units contain duplicates")

    def active_b(u):
        return u in B and _get(B[u], "status") == ACTIVE

    def active_d(u):
        return u in D and _get(D[u], "status") == ACTIVE

    def retired_d(u):
        return u in D and _get(D[u], "status") == RETIRED

    def need(cond, msg):
        if not cond:
            raise GeoChangeRuleError("G2P-CAT-400", f"{change_type}: {msg}")

    def same_level(units):
        lv = {_get(D.get(u) or B.get(u), "level_id") for u in units if (u in D or u in B)}
        need(len(lv) <= 1, f"units {units} are not all at the same level")

    if change_type == CREATE:
        need(not frm, "from_units must be empty")
        need(to, "to_units is required")
        for u in to:
            need(active_d(u), f"{u} is not an active unit of the draft")
            need(not active_b(u), f"{u} already exists in version {base_version_no}")
    elif change_type == RETIRE:
        need(not to, "to_units must be empty")
        need(frm, "from_units is required")
        for u in frm:
            need(active_b(u), f"{u} is not an active unit of version {base_version_no}")
            need(retired_d(u), f"{u} is not retired in the draft")
    elif change_type in (RENAME, REPARENT, BOUNDARY_CHANGE):
        need(frm, "from_units is required")
        to = to or list(frm)
        if change_type != BOUNDARY_CHANGE:
            need(len(frm) == 1 and to == frm, "from_units and to_units must name the same single unit")
        for u in frm:
            need(active_b(u), f"{u} is not an active unit of version {base_version_no}")
        for u in to:
            need(active_d(u), f"{u} is not an active unit of the draft")
        if change_type == RENAME:
            need(
                _get(B[frm[0]], "name") != _get(D[frm[0]], "name"),
                f"{frm[0]} has the same name in both versions",
            )
        if change_type == REPARENT:
            need(
                _get(B[frm[0]], "parent_unit_id") != _get(D[frm[0]], "parent_unit_id"),
                f"{frm[0]} has the same parent in both versions",
            )
    elif change_type == RECODE:
        need(len(frm) == 1 and len(to) == 1 and frm != to, "needs exactly one old and one new code")
        need(active_b(frm[0]), f"{frm[0]} is not an active unit of version {base_version_no}")
        need(retired_d(frm[0]), f"{frm[0]} must be retired in the draft")
        need(active_d(to[0]), f"{to[0]} is not an active unit of the draft")
        need(not active_b(to[0]), f"{to[0]} already exists in version {base_version_no}")
        same_level(frm + to)
    elif change_type == SPLIT:
        need(len(frm) == 1, "needs exactly one from-unit")
        need(len(to) >= 2, "needs at least two to-units")
        need(active_b(frm[0]), f"{frm[0]} is not an active unit of version {base_version_no}")
        need(
            retired_d(frm[0]) or frm[0] in to,
            f"{frm[0]} must be retired in the draft or be one of the parts",
        )
        for u in to:
            need(active_d(u), f"{u} is not an active unit of the draft")
        same_level(frm + to)
    elif change_type == MERGE:
        need(len(frm) >= 2, "needs at least two from-units")
        need(len(to) == 1, "needs exactly one to-unit")
        for u in frm:
            need(active_b(u), f"{u} is not an active unit of version {base_version_no}")
            need(retired_d(u) or u in to, f"{u} must be retired in the draft or be the merged unit")
        need(active_d(to[0]), f"{to[0]} is not an active unit of the draft")
        same_level(frm + to)

    if change_type in TERMINAL:
        ending = {u for u in frm if u not in to}
        for change_id, other_type, other_from in other_terminal_events:
            overlap = set(other_from or []) & ending
            if overlap:
                raise GeoChangeRuleError(
                    "G2P-CAT-409", f"{sorted(overlap)} already end in change {change_id} ({other_type})"
                )
    return frm, to
