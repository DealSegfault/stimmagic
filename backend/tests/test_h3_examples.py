import httpx
import pytest
from fastapi import FastAPI

from h3_examples import get_example, search_examples
from routes.h3_examples import router


def test_search_filters_and_similar_examples_use_real_catalogue():
    assert search_examples()["total"] == 1000
    noir = search_examples("mafieux noir blanc cigare", limit=8)
    assert "000128" in [item["id"] for item in noir["items"]]
    assert search_examples("zzzzzzzzunknown")["total"] == 0
    stop_motion = search_examples(style="stop-motion", limit=3)
    assert all(item["style"] == "stop-motion" for item in stop_motion["items"])
    related = search_examples(similar_to="000128", limit=6)["items"]
    assert related and all(item["id"] != "000128" for item in related)
    assert any(item["style"] == "film-stock" for item in related)
    assert "description" not in noir["items"][0]  # Search does not flood agent context with full prompts.


@pytest.mark.asyncio
async def test_catalogue_routes_details_thumbnail_and_invalid_ids():
    app = FastAPI()
    app.include_router(router)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        search = await client.get("/api/prompt/h3/examples", params={"q": "000128", "limit": 1})
        assert search.json()["items"][0]["id"] == "000128"
        detail = await client.get("/api/prompt/h3/examples/000128")
        assert detail.status_code == 200
        assert "silver-haired don" in detail.json()["prompt"]
        assert detail.json()["seconds"] == 5.17
        assert detail.json()["credit"]["prompts"]["who"] == "ostris"
        thumb = await client.get("/api/prompt/h3/examples/000128/thumbnail")
        assert thumb.headers["content-type"] == "image/webp"
        assert thumb.content[:4] == b"RIFF"
        assert (await client.get("/api/prompt/h3/examples/999999")).status_code == 404
        assert (await client.get("/api/prompt/h3/examples/garbage/thumbnail")).status_code == 404
        assert (await client.get("/api/prompt/h3/examples", params={"similar_to": "999999"})).status_code == 404
        assert (await client.get("/api/prompt/h3/examples", params={"limit": 5000})).status_code == 422


@pytest.mark.asyncio
async def test_agent_library_can_search_without_database_or_importing_media():
    import json
    from agent.v2.tools.library import library
    from agent.v2.code_runtime import StimmaLibraryAPI

    result = json.loads(await library(action="prompt_examples", query="cigar noir", limit=3))
    assert result["items"] and len(result["items"]) == 3
    assert "stimma-h3:" in result["items"][0]["chat_link"]
    detail = json.loads(await library(action="prompt_examples", filters={"example_id": "000128"}))
    assert detail == get_example("000128")
    sdk_detail = await StimmaLibraryAPI(None).prompt_examples(example_id="000128")
    assert sdk_detail == detail
