"""Master Data as a catalogue: versioned, approved, pinnable reference data.

The legacy tables (``g2p_attributes``, ``g2p_attribute_values``,
``g2p_geo_levels``, ``g2p_geo_level_values``) stay, and hold the CURRENT
PUBLISHED state — materialised from the tables below in the same transaction as
a publish (see ``catalogue_sql.py``). Registries that read those tables directly
keep working; everything else reads versions through the ``/catalogue`` API.

Immutability of a published version is enforced by Postgres triggers, not only
by the service code: once a version's status is PUBLISHED, its rows (and the
version row itself) can be neither updated nor deleted, and nothing can be added
to it. A value or unit that disappears is RETIRED in the next version instead,
so a reference to it keeps resolving against the version it was taken from.
"""

from datetime import date, datetime
from typing import Optional

from openg2p_fastapi_common.models import BaseORMModel
from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column


class VersionStatus:
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    PUBLISHED = "PUBLISHED"
    REJECTED = "REJECTED"
    # A draft someone threw away. The row (and its content) is kept, like a
    # REJECTED one, so its version number is never handed out again and the
    # change log / audit trail / boundary keys that mention it stay unambiguous.
    DISCARDED = "DISCARDED"
    # Reserved: a published version is never changed, so nothing moves a
    # version to RETIRED today. Kept in the vocabulary of the spec.
    RETIRED = "RETIRED"

    OPEN = (DRAFT, SUBMITTED)


class ItemStatus:
    ACTIVE = "ACTIVE"
    RETIRED = "RETIRED"


class GeoChangeType:
    CREATE = "CREATE"
    RETIRE = "RETIRE"
    RENAME = "RENAME"
    RECODE = "RECODE"
    SPLIT = "SPLIT"
    MERGE = "MERGE"
    REPARENT = "REPARENT"
    BOUNDARY_CHANGE = "BOUNDARY_CHANGE"

    ALL = (CREATE, RETIRE, RENAME, RECODE, SPLIT, MERGE, REPARENT, BOUNDARY_CHANGE)


class _VersionWorkflowColumns:
    """Columns every versioned subject (list, geography) carries."""

    status: Mapped[str] = mapped_column(String, nullable=False, index=True)
    base_version_no: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    change_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    effective_from: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # *_by hold the stable user id (token ``sub``) or a system name; *_by_name
    # the user's display name, written together with the id (NULL for a
    # system actor). Names are for people to read; ids decide maker != checker.
    created_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_by_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, server_default=func.now()
    )
    updated_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    updated_by_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    submitted_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    submitted_by_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    decided_by_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # AWE request id when the approval runs through the Approval Workflow Engine.
    approval_ref: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


# ---------------------------------------------------------------------------
# Code lists
# ---------------------------------------------------------------------------


class G2PListVersion(_VersionWorkflowColumns, BaseORMModel):
    """One version of a code list. ``list_id`` is ``g2p_attributes.attribute_id``.

    The consumer-visible list metadata (code, label, labels per locale,
    hierarchy flag, attribute schema) is versioned with the values, because a
    consumer pinned to a version must see the list as it was. Description and
    owner are administrative and live only on ``g2p_attributes``.
    """

    __tablename__ = "g2p_list_versions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["list_id"], ["g2p_attributes.attribute_id"], ondelete="CASCADE", name="fk_list_versions_list"
        ),
    )

    list_id: Mapped[str] = mapped_column(String, primary_key=True)
    version_no: Mapped[int] = mapped_column(Integer, primary_key=True)

    list_code: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    display: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    display_i18n: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    is_hierarchical: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True, default=False)
    # JSON Schema for each value's ``attributes`` object. A property may carry
    # {"x-list-ref": "<LIST_CODE>"}: its value(s) must then be codes of that list.
    attribute_schema: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)


class G2PListVersionValue(BaseORMModel):
    __tablename__ = "g2p_list_version_values"
    __table_args__ = (
        ForeignKeyConstraint(
            ["list_id", "version_no"],
            ["g2p_list_versions.list_id", "g2p_list_versions.version_no"],
            ondelete="CASCADE",
            name="fk_list_version_values_version",
        ),
    )

    list_id: Mapped[str] = mapped_column(String, primary_key=True)
    version_no: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Stable across versions (a RECODE keeps the id and changes the code).
    value_id: Mapped[str] = mapped_column(String, primary_key=True)
    value_code: Mapped[str] = mapped_column(String, nullable=False, index=True)
    display: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    display_i18n: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    parent_value_code: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    sort_order: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    attributes: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    # Semantic role tags from the country pack (e.g. "female").
    roles: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default=ItemStatus.ACTIVE)


# ---------------------------------------------------------------------------
# Geography — versioned as ONE dataset (levels + units + boundaries)
# ---------------------------------------------------------------------------


class G2PGeoVersion(_VersionWorkflowColumns, BaseORMModel):
    __tablename__ = "g2p_geo_versions"

    version_no: Mapped[int] = mapped_column(Integer, primary_key=True)
    country: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    owner_org: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # {level_mnemonic: object key in the boundary bucket}. Keys are immutable and
    # versioned (geo/<country>/v<version>/<level>.geojson); a level that did not
    # change keeps pointing at the earlier version's object.
    boundary_objects: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    # {level_mnemonic: {"sha256": file hash, "bytes": n, "units": {unit_id: geometry hash}}}
    boundary_checksums: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)


class G2PGeoVersionLevel(BaseORMModel):
    __tablename__ = "g2p_geo_version_levels"
    __table_args__ = (
        ForeignKeyConstraint(
            ["version_no"], ["g2p_geo_versions.version_no"], ondelete="CASCADE", name="fk_geo_version_levels"
        ),
    )

    version_no: Mapped[int] = mapped_column(Integer, primary_key=True)
    level_id: Mapped[str] = mapped_column(String, primary_key=True)
    level_mnemonic: Mapped[str] = mapped_column(String, nullable=False)
    parent_level_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    display: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    display_i18n: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)


class G2PGeoVersionUnit(BaseORMModel):
    __tablename__ = "g2p_geo_version_units"
    __table_args__ = (
        ForeignKeyConstraint(
            ["version_no"], ["g2p_geo_versions.version_no"], ondelete="CASCADE", name="fk_geo_version_units"
        ),
    )

    version_no: Mapped[int] = mapped_column(Integer, primary_key=True)
    # The P-code for a real pack.
    unit_id: Mapped[str] = mapped_column(String, primary_key=True)
    level_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    name_i18n: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    parent_unit_id: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default=ItemStatus.ACTIVE)
    # Set at publish: when this unit came into / went out of effect.
    valid_from: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_to: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class G2PGeoChange(BaseORMModel):
    """A change event (lineage) recorded in a geography version.

    ``from_units`` are units of the base version, ``to_units`` units of this
    version. The crosswalk follows these across versions.
    """

    __tablename__ = "g2p_geo_changes"
    __table_args__ = (
        ForeignKeyConstraint(
            ["version_no"], ["g2p_geo_versions.version_no"], ondelete="CASCADE", name="fk_geo_changes_version"
        ),
    )

    change_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    change_type: Mapped[str] = mapped_column(String, nullable=False)
    from_units: Mapped[list] = mapped_column(ARRAY(String), nullable=False, default=list)
    to_units: Mapped[list] = mapped_column(ARRAY(String), nullable=False, default=list)
    effective_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # True when added automatically at submit to complete the lineage.
    is_auto: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_by_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, server_default=func.now()
    )


# ---------------------------------------------------------------------------
# Catalogue releases — a named set of list versions + one geography version
# ---------------------------------------------------------------------------


class G2PCatalogueRelease(BaseORMModel):
    __tablename__ = "g2p_catalogue_releases"

    release_code: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default=VersionStatus.DRAFT)
    geo_version_no: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # *_by: stable user id; *_by_name: display name, written with the id.
    created_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_by_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, server_default=func.now()
    )
    # Who last set the members (and the geography pin): a maker, so excluded
    # from publishing the release, like the creator.
    members_set_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    members_set_by_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    members_set_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    published_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    published_by_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class G2PCatalogueReleaseMember(BaseORMModel):
    __tablename__ = "g2p_catalogue_release_members"
    __table_args__ = (
        ForeignKeyConstraint(
            ["release_code"],
            ["g2p_catalogue_releases.release_code"],
            ondelete="CASCADE",
            name="fk_release_members_release",
        ),
    )

    release_code: Mapped[str] = mapped_column(String, primary_key=True)
    list_id: Mapped[str] = mapped_column(String, primary_key=True)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)


# ---------------------------------------------------------------------------
# Change log (append-only; backs the change feed) and small state
# ---------------------------------------------------------------------------


class G2PCatalogueChangeLog(BaseORMModel):
    """Append-only change log; also the outbox for the Audit Manager and WebSub.

    ``actor`` is the stable user identifier (the token's ``sub``) or a system
    name; ``actor_name`` the display name of a user (NULL for system actors).
    ``forwarded_at`` is set once the event has been delivered (see
    services/catalogue_outbox.py) and is the only column that may change.
    """

    __tablename__ = "g2p_catalogue_change_log"

    event_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String, nullable=False, index=True)
    # list | geo | release
    subject_type: Mapped[str] = mapped_column(String, nullable=False)
    subject_id: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)
    version_no: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    actor: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    actor_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    details: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    forwarded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class G2PCatalogueState(BaseORMModel):
    """Small key/value state: ``geo.current_version_no``, ``schema_version``,
    ``legacy.generation`` (bumped whenever the legacy tables are re-materialised),
    ``geo.visibility`` / ``geo.licence_uri`` / ``geo.licence_label`` (geography settings)."""

    __tablename__ = "g2p_catalogue_state"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    int_value: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    text_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, server_default=func.now()
    )


class G2PCatalogueAweEvent(BaseORMModel):
    """AWE webhook deliveries, for idempotency and troubleshooting."""

    __tablename__ = "g2p_catalogue_awe_events"

    event_id: Mapped[str] = mapped_column(String, primary_key=True)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    request_id: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)
    artifact_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    artifact_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    status: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    actor: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    occurred_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    received_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, server_default=func.now()
    )
    applied: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
