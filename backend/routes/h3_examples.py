"""Explore existing H3 renders without importing them as library Assets."""

from fastapi import APIRouter, HTTPException, Query, Response

from h3_examples import get_example, get_thumbnail, search_examples


router = APIRouter(prefix="/api/prompt/h3/examples", tags=["prompt"])


@router.get("")
def examples(
    q: str = Query("", max_length=300), style: str = "", topic: str = "",
    similar_to: str = "", limit: int = Query(24, ge=1, le=60), offset: int = Query(0, ge=0),
):
    try:
        return search_examples(q, style=style, topic=topic, similar_to=similar_to, limit=limit, offset=offset)
    except KeyError:
        raise HTTPException(404, "H3 example not found") from None


@router.get("/{example_id}")
def example(example_id: str):
    try:
        return get_example(example_id)
    except KeyError:
        raise HTTPException(404, "H3 example not found") from None


@router.get("/{example_id}/thumbnail")
def thumbnail(example_id: str):
    try:
        return Response(get_thumbnail(example_id), media_type="image/webp", headers={"Cache-Control": "public, max-age=86400"})
    except KeyError:
        raise HTTPException(404, "H3 example not found") from None
