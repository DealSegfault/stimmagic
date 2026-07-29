"""Tests for the op-stack image editor's working-document store.

The document is a directory, deliberately pack-ratty: steps removed from
document.json keep their payloads, the journal only ever appends, and cache/ is
the one subtree that may be discarded.
"""

import io
import json
from pathlib import Path

import httpx
import pytest
from PIL import Image
from sqlalchemy import select

import image_stack_service as stack
from database import Asset, AssetRevision, MediaItem, WorkingDocument
from tests.helpers.media import create_media_item, generate_test_image


async def _asset(db_session, tmp_path, *, name="base", width=256, height=128):
    """An Asset backed by a real file — save-edit needs a readable source."""
    from asset_service import create_asset_from_media

    async with db_session() as session:
        source = tmp_path / f"{name}.png"
        file_hash = generate_test_image(source, width=width, height=height)
        media = await create_media_item(
            session, file_path=source, file_hash=file_hash, width=width, height=height
        )
        asset = await create_asset_from_media(session, media_id=media.id)
        await session.commit()
        return asset.id, media.id, file_hash


async def _open(client, db_session, tmp_path, name):
    asset_id, media_id, _ = await _asset(db_session, tmp_path, name=name)
    body = (await client.post("/api/image-stack/open", json={"asset_id": asset_id})).json()
    return body["document_id"], body["base"]


def _document(base, edits=None):
    return {
        "format": stack.DOCUMENT_FORMAT,
        "version": stack.DOCUMENT_VERSION,
        "base": base,
        "canvas": {"width": base["width"], "height": base["height"]},
        "edits": edits or [],
    }


def _png_bytes(size=(8, 8), color=(255, 0, 0)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


class TestOpen:
    async def test_open_creates_the_directory_layout(
        self, client: httpx.AsyncClient, db_session, tmp_path
    ):
        asset_id, media_id, file_hash = await _asset(db_session, tmp_path, name="open-layout")

        response = await client.post("/api/image-stack/open", json={"asset_id": asset_id})
        assert response.status_code == 200, response.text
        body = response.json()

        assert body["base"]["asset_id"] == asset_id
        assert body["base"]["media_id"] == media_id
        assert body["base"]["file_hash"] == file_hash
        assert body["base"]["width"] == 256
        # A fresh asset has no stack yet.
        assert body["document"] is None

        async with db_session() as session:
            document = await session.get(WorkingDocument, body["document_id"])
            assert document.editor_type == stack.EDITOR_TYPE
            directory = Path(document.state_locator)

        assert (directory / "payloads").is_dir()
        assert (directory / "cache").is_dir()

    async def test_reopening_resumes_the_same_document(
        self, client: httpx.AsyncClient, db_session, tmp_path
    ):
        """One stack per asset — this is what makes one-instance-per-asset hold
        across restarts."""
        asset_id, _, _ = await _asset(db_session, tmp_path, name="open-resume")

        first = await client.post("/api/image-stack/open", json={"asset_id": asset_id})
        second = await client.post("/api/image-stack/open", json={"asset_id": asset_id})

        assert first.json()["document_id"] == second.json()["document_id"]

    async def test_open_rejects_a_revision_from_another_asset(
        self, client: httpx.AsyncClient, db_session, tmp_path
    ):
        asset_a, _, _ = await _asset(db_session, tmp_path, name="open-a")
        asset_b, _, _ = await _asset(db_session, tmp_path, name="open-b")
        async with db_session() as session:
            other = await session.get(Asset, asset_b)
            foreign_revision = other.current_revision_id

        response = await client.post(
            "/api/image-stack/open",
            json={"asset_id": asset_a, "revision_id": foreign_revision},
        )
        assert response.status_code == 400


class TestDocument:
    async def test_document_round_trips(
        self, client: httpx.AsyncClient, db_session, tmp_path
    ):
        document_id, base = await _open(client, db_session, tmp_path, "doc-round-trip")
        payload = _document(base, edits=[{
            "id": "01J000000000000000000000AA",
            "class": "patch",
            "enabled": True,
            "label": "Inpaint — collar",
        }])

        write = await client.put(
            f"/api/image-stack/{document_id}/document", json={"document": payload}
        )
        assert write.status_code == 200

        read = await client.get(f"/api/image-stack/{document_id}")
        assert read.json()["document"] == payload

    @pytest.mark.parametrize("label,mutation", [
        ("format", {"format": "something-else"}),
        ("version", {"version": 99}),
        ("edits", {"edits": "not a list"}),
        ("base", {"base": None}),
    ])
    async def test_malformed_documents_are_rejected(
        self, client: httpx.AsyncClient, db_session, tmp_path, label, mutation
    ):
        document_id, base = await _open(client, db_session, tmp_path, f"doc-bad-{label}")
        payload = {**_document(base), **mutation}
        response = await client.put(
            f"/api/image-stack/{document_id}/document", json={"document": payload}
        )
        assert response.status_code == 400

    async def test_unknown_document_is_404(self, client: httpx.AsyncClient):
        assert (await client.get("/api/image-stack/999999")).status_code == 404

    async def test_legacy_editor_documents_are_not_reachable(
        self, client: httpx.AsyncClient, db_session, tmp_path
    ):
        """The snapshot editor's rows share the table but not this surface."""
        from asset_service import create_working_document

        asset_id, _, _ = await _asset(db_session, tmp_path, name="doc-legacy-type")
        async with db_session() as session:
            legacy = await create_working_document(
                session, asset_id=asset_id, editor_type="image"
            )
            await session.commit()
            legacy_id = legacy.id

        assert (await client.get(f"/api/image-stack/{legacy_id}")).status_code == 404


class TestJournal:
    async def test_entries_append_and_read_back(
        self, client: httpx.AsyncClient, db_session, tmp_path
    ):
        document_id, _ = await _open(client, db_session, tmp_path, "journal-append")

        await client.post(f"/api/image-stack/{document_id}/journal", json={"entries": [
            {"seq": 1, "action": "add_op", "inverse": {"action": "remove_op", "op_id": "a"}},
            {"seq": 2, "action": "pick_candidate", "inverse": {"action": "pick_candidate"}},
        ]})
        response = await client.post(
            f"/api/image-stack/{document_id}/journal",
            json={"entries": [{"seq": 3, "action": "undo", "inverse": None}]},
        )
        assert response.json()["journal_length"] == 3

        entries = (await client.get(f"/api/image-stack/{document_id}/journal")).json()["entries"]
        assert [e["seq"] for e in entries] == [1, 2, 3]
        # Undo is recorded, not a truncation: entry 2 is still there.
        assert entries[1]["action"] == "pick_candidate"
        assert all("ts" in e for e in entries)

    async def test_entries_without_an_action_are_rejected(
        self, client: httpx.AsyncClient, db_session, tmp_path
    ):
        document_id, _ = await _open(client, db_session, tmp_path, "journal-bad")
        response = await client.post(
            f"/api/image-stack/{document_id}/journal",
            json={"entries": [{"seq": 1}]},
        )
        assert response.status_code == 400

    async def test_replay_starts_at_the_last_checkpoint(
        self, client: httpx.AsyncClient, db_session, tmp_path
    ):
        document_id, _ = await _open(client, db_session, tmp_path, "journal-checkpoint")
        await client.post(f"/api/image-stack/{document_id}/journal", json={"entries": [
            {"seq": 1, "action": "add_op"},
            {"seq": 2, "action": "checkpoint", "document": {"edits": []}},
            {"seq": 3, "action": "toggle_op"},
        ]})

        entries = (await client.get(f"/api/image-stack/{document_id}/journal")).json()["entries"]
        assert [e["seq"] for e in entries] == [2, 3]

    async def test_a_torn_final_line_does_not_lose_the_log(
        self, client: httpx.AsyncClient, db_session, tmp_path
    ):
        """A crash mid-append leaves a partial line; everything before it stands."""
        document_id, _ = await _open(client, db_session, tmp_path, "journal-torn")
        await client.post(
            f"/api/image-stack/{document_id}/journal",
            json={"entries": [{"seq": 1, "action": "add_op"}]},
        )
        async with db_session() as session:
            document = await session.get(WorkingDocument, document_id)
            journal = Path(document.state_locator) / "journal.jsonl"
        with journal.open("a") as handle:
            handle.write('{"seq": 2, "action": "add_o')

        entries = (await client.get(f"/api/image-stack/{document_id}/journal")).json()["entries"]
        assert [e["seq"] for e in entries] == [1]


class TestPayloads:
    async def test_payload_round_trips(
        self, client: httpx.AsyncClient, db_session, tmp_path
    ):
        document_id, _ = await _open(client, db_session, tmp_path, "payload-round-trip")
        data = _png_bytes()

        upload = await client.post(
            f"/api/image-stack/{document_id}/payloads",
            files={"file": ("mask.png", data, "image/png")},
            data={"name": "01J0-mask.png"},
        )
        assert upload.status_code == 200
        assert upload.json()["ref"] == "payloads/01J0-mask.png"

        fetched = await client.get(f"/api/image-stack/{document_id}/payloads/01J0-mask.png")
        assert fetched.status_code == 200
        assert fetched.content == data
        assert fetched.headers["cache-control"] == "no-cache"

    async def test_overwritten_payload_refetches_latest_bytes(
        self, client: httpx.AsyncClient, db_session, tmp_path
    ):
        """Paint layers keep their ref while each completed stroke rewrites it."""
        document_id, _ = await _open(client, db_session, tmp_path, "payload-overwrite")
        url = f"/api/image-stack/{document_id}/payloads/paint-layer.png"
        first = _png_bytes(color=(255, 0, 0))
        latest = _png_bytes(color=(0, 0, 255))

        for data in (first, latest):
            upload = await client.post(
                f"/api/image-stack/{document_id}/payloads",
                files={"file": ("paint-layer.png", data, "image/png")},
                data={"name": "paint-layer.png"},
            )
            assert upload.status_code == 200

        fetched = await client.get(url)
        assert fetched.status_code == 200
        assert fetched.content == latest
        assert fetched.headers["cache-control"] == "no-cache"

    @pytest.mark.parametrize("label,name", [
        ("traversal", "../escape.png"),
        ("subdir", "sub/dir.png"),
        ("no-extension", "no-extension"),
        ("wrong-extension", "script.svg"),
        ("dotfile", ".hidden.png"),
        ("empty", ""),
    ])
    async def test_payload_names_cannot_escape_the_document(
        self, client: httpx.AsyncClient, db_session, tmp_path, label, name
    ):
        document_id, _ = await _open(client, db_session, tmp_path, f"payload-esc-{label}")
        response = await client.post(
            f"/api/image-stack/{document_id}/payloads",
            files={"file": ("x.png", _png_bytes(), "image/png")},
            data={"name": name},
        )
        assert response.status_code in (400, 422), name

    async def test_cache_is_deletable_and_payloads_survive(
        self, client: httpx.AsyncClient, db_session, tmp_path
    ):
        """cache/ is a pure function of document + payloads + base. payloads/
        is the pack-rat store and must never be swept with it."""
        document_id, _ = await _open(client, db_session, tmp_path, "payload-cache")
        await client.post(
            f"/api/image-stack/{document_id}/payloads",
            files={"file": ("m.png", _png_bytes(), "image/png")},
            data={"name": "keep-me.png"},
        )
        await client.post(
            f"/api/image-stack/{document_id}/payloads",
            files={"file": ("c.png", _png_bytes(), "image/png")},
            data={"name": "composite-1.png", "subdir": "cache"},
        )

        assert (await client.delete(f"/api/image-stack/{document_id}/cache")).status_code == 200

        assert (await client.get(
            f"/api/image-stack/{document_id}/payloads/keep-me.png"
        )).status_code == 200
        assert (await client.get(
            f"/api/image-stack/{document_id}/payloads/composite-1.png?subdir=cache"
        )).status_code == 404


class TestSaveEdit:
    """Save materializes the composite; the stack stays the recipe."""

    async def test_save_keeps_the_stack_on_the_revision_it_was_built_against(
        self, client: httpx.AsyncClient, db_session, tmp_path
    ):
        asset_id, media_id, _ = await _asset(db_session, tmp_path, name="save-advance")
        opened = (await client.post(
            "/api/image-stack/open", json={"asset_id": asset_id}
        )).json()
        document_id = opened["document_id"]
        base_revision_id = opened["base"]["revision_id"]

        summary = [{"class": "patch", "exec": {"tool_id": "test:inpaint"}, "job_ids": ["7"]}]
        response = await client.post(
            "/api/media/save-edit",
            files={"file": ("composite.png", _png_bytes((256, 128), (0, 128, 255)), "image/png")},
            data={
                "source_media_id": str(media_id),
                "asset_id": str(asset_id),
                "base_revision_id": str(base_revision_id),
                "working_document_id": str(document_id),
                "stack_summary": json.dumps(summary),
            },
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["asset_id"] == asset_id
        assert body["revision_id"] != base_revision_id

        async with db_session() as session:
            document = await session.get(WorkingDocument, document_id)
            # The same document — not a second one — and still rooted at the
            # revision its ops were authored against.
            #
            # Re-parenting it to its own output would double every edit: the
            # stack would render on a frame that already contained it, so
            # hiding or deleting a step would remove nothing.
            assert document.base_revision_id == base_revision_id
            assert document.base_revision_id != body["revision_id"]
            assert document.editor_type == stack.EDITOR_TYPE

            documents = (await session.execute(
                select(WorkingDocument).where(
                    WorkingDocument.asset_id == asset_id,
                    WorkingDocument.deleted_at.is_(None),
                )
            )).scalars().all()
            assert [d.id for d in documents] == [document_id]

            committed = await session.get(MediaItem, body["media_id"])
            metadata = json.loads(committed.generation_metadata)
            assert metadata["parameters"]["stack"] == summary

            revision = await session.get(AssetRevision, body["revision_id"])
            assert revision.parent_revision_id == base_revision_id

    async def test_save_does_not_rewrite_the_stack(
        self, client: httpx.AsyncClient, db_session, tmp_path
    ):
        """The stack keeps applying from the revision it was built against."""
        asset_id, media_id, _ = await _asset(db_session, tmp_path, name="save-recipe")
        opened = (await client.post(
            "/api/image-stack/open", json={"asset_id": asset_id}
        )).json()
        document_id = opened["document_id"]
        document = _document(opened["base"], edits=[{"id": "01J0", "class": "patch", "enabled": True}])
        await client.put(f"/api/image-stack/{document_id}/document", json={"document": document})

        saved = await client.post(
            "/api/media/save-edit",
            files={"file": ("c.png", _png_bytes((256, 128)), "image/png")},
            data={
                "source_media_id": str(media_id),
                "asset_id": str(asset_id),
                "working_document_id": str(document_id),
            },
        )
        assert saved.status_code == 200, saved.text

        after = (await client.get(f"/api/image-stack/{document_id}")).json()["document"]
        assert after == document

    async def test_save_as_new_forks_the_document(
        self, client: httpx.AsyncClient, db_session, tmp_path
    ):
        asset_id, media_id, _ = await _asset(db_session, tmp_path, name="save-fork")
        document_id = (await client.post(
            "/api/image-stack/open", json={"asset_id": asset_id}
        )).json()["document_id"]

        response = await client.post(
            "/api/media/save-edit",
            files={"file": ("c.png", _png_bytes((256, 128)), "image/png")},
            data={
                "source_media_id": str(media_id),
                "asset_id": str(asset_id),
                "working_document_id": str(document_id),
                "save_as_new": "true",
            },
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["asset_id"] != asset_id

        async with db_session() as session:
            forked = await session.scalar(
                select(WorkingDocument).where(
                    WorkingDocument.asset_id == body["asset_id"],
                    WorkingDocument.deleted_at.is_(None),
                )
            )
            assert forked is not None
            assert forked.id != document_id
            assert forked.editor_type == stack.EDITOR_TYPE
            # The original stack is untouched by a fork.
            original = await session.get(WorkingDocument, document_id)
            assert original.asset_id == asset_id

    async def test_unknown_stack_document_is_rejected(
        self, client: httpx.AsyncClient, db_session, tmp_path
    ):
        _, media_id, _ = await _asset(db_session, tmp_path, name="save-unknown-doc")
        response = await client.post(
            "/api/media/save-edit",
            files={"file": ("c.png", _png_bytes(), "image/png")},
            data={"source_media_id": str(media_id), "working_document_id": "999999"},
        )
        assert response.status_code == 404

    async def test_legacy_sidecar_save_is_unchanged(
        self, client: httpx.AsyncClient, db_session, tmp_path
    ):
        """The snapshot editor's path must not shift under the extension."""
        asset_id, media_id, _ = await _asset(db_session, tmp_path, name="save-legacy")
        response = await client.post(
            "/api/media/save-edit",
            files={"file": ("c.png", _png_bytes(), "image/png")},
            data={
                "source_media_id": str(media_id),
                "asset_id": str(asset_id),
                "editor_project": json.dumps({"version": 1, "state": {}}),
            },
        )
        assert response.status_code == 200, response.text

        async with db_session() as session:
            document = await session.scalar(
                select(WorkingDocument).where(
                    WorkingDocument.asset_id == response.json()["asset_id"],
                    WorkingDocument.editor_type == "image",
                    WorkingDocument.deleted_at.is_(None),
                )
            )
            assert document is not None
            assert document.state_locator.endswith(".json")
