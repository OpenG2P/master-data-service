"""Small builders shared by the tests."""

from openg2p_gen2_master_data.schemas.g2p_catalogue import (
    CreateListPayload,
    DecideDraftPayload,
    DraftValueInput,
    SubmitDraftPayload,
)
from openg2p_gen2_master_data.services import G2PCatalogueListService
from openg2p_gen2_master_data.services.catalogue_common import Actor

MAKER = Actor("maker", token="maker-token")
CHECKER = Actor("checker", token="checker-token")


def svc() -> G2PCatalogueListService:
    return G2PCatalogueListService.get_component()


def values(*codes, **extra):
    return [
        DraftValueInput(value_code=c, display=c.title(), sort_order=i, **extra) for i, c in enumerate(codes)
    ]


async def publish_list(code, codes=("A", "B", "C"), *, schema=None, hierarchical=False, effective_from=None):
    """Create a list and publish version 1 with the given values."""
    s = svc()
    await s.create_list(
        CreateListPayload(
            list_code=code, display=code.title(), attribute_schema=schema, is_hierarchical=hierarchical
        ),
        MAKER,
    )
    if codes:
        await s.upsert_draft_values(code, values(*codes), MAKER)
    await s.submit_draft(SubmitDraftPayload(list_code=code), MAKER)
    _, v = await s.approve_draft(DecideDraftPayload(list_code=code, effective_from=effective_from), CHECKER)
    return v


async def submit_and_approve(code, effective_from=None, note=None):
    s = svc()
    await s.submit_draft(SubmitDraftPayload(list_code=code, change_note=note), MAKER)
    _, v = await s.approve_draft(DecideDraftPayload(list_code=code, effective_from=effective_from), CHECKER)
    return v
