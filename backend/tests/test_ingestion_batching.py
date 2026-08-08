from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

import ingestion


@pytest.mark.asyncio
async def test_discovery_insert_is_committed_in_bounded_batches(monkeypatch):
    created = []

    def make_media_item(**values):
        item = SimpleNamespace(**values)
        created.append(item)
        return item

    monkeypatch.setattr(ingestion, "MediaItem", make_media_item)
    session = SimpleNamespace(
        add=Mock(),
        commit=AsyncMock(),
        expunge_all=Mock(),
    )
    processor = object.__new__(ingestion.MediaIngestion)
    count = ingestion.DISCOVERY_INSERT_BATCH_SIZE * 2 + 1
    metadata = [
        {
            "file_path": f"file-{index}.png",
            "file_hash": "",
            "file_size": index,
            "file_format": "png",
        }
        for index in range(count)
    ]

    await processor._insert_batch(session, metadata)

    assert session.add.call_count == count
    assert session.commit.await_count == 3
    assert session.expunge_all.call_count == 3
    assert all(hasattr(item, "random_sort_value") for item in created)
    assert all("random_sort_value" not in values for values in metadata)
