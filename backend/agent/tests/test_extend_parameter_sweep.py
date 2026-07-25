"""Tests for stimma.extend_parameter_sweep.

Growing a sweep used to mean re-listing every surviving cell by hand — a
56-element literal of media ids transcribed off the previous grid. One
transposed id silently mislabels a cell and nothing downstream catches it,
because a grid has no idea what its cells were supposed to be. These tests pin
the behaviour that removes the transcription step: existing cells are read back
off the old grid, and only the new ones are supplied.
"""

from pathlib import Path

import pytest

from agent.v2.code_runtime import StimmaSDK
from database import Chat
from tests.helpers.media import create_media_item


@pytest.fixture
async def chat_id(session):
    chat = Chat(name="grid test")
    session.add(chat)
    await session.flush()
    await session.commit()
    return chat.id


@pytest.fixture
def sdk(session, chat_id, tmp_path):
    return StimmaSDK(
        session=session,
        chat_id=chat_id,
        workspace_dir=tmp_path,
        project_workspace_dir=None,
        interrupt_checker=lambda: None,
    )


async def _cells(session, n, prefix):
    """n real library rows, so the grid builder can resolve every cell."""
    out = []
    for i in range(n):
        item = await create_media_item(
            session, file_path=Path(f"/tmp/stimma-test/{prefix}_{i}.png")
        )
        out.append(item.id)
    return out


async def _matrix_of(sdk, grid):
    """Read a grid back into a row-major id matrix."""
    loaded = await sdk._load_sweep(grid)
    return loaded["matrix"], loaded["row_headers"], loaded["col_headers"]


@pytest.fixture
async def base_grid(sdk, session):
    """A 2x2 sweep: rows R0/R1, cols C0/C1."""
    ids = await _cells(session, 4, "base")
    grid = await sdk.create_parameter_sweep(
        media_ids=ids,
        rows=2,
        cols=2,
        row_headers=["R0", "R1"],
        col_headers=["C0", "C1"],
        title="Base",
    )
    return grid, ids


class TestAddColumns:
    async def test_existing_cells_are_carried_over_untouched(self, sdk, session, base_grid):
        grid, ids = base_grid
        new = await _cells(session, 2, "newcol")

        out = await sdk.extend_parameter_sweep(grid, add_cols={"C2": new})
        matrix, rows, cols = await _matrix_of(sdk, out)

        assert cols == ["C0", "C1", "C2"]
        assert rows == ["R0", "R1"]
        # Original cells keep their exact positions; new column is appended.
        assert matrix == [
            [ids[0], ids[1], new[0]],
            [ids[2], ids[3], new[1]],
        ]

    async def test_multiple_columns_keep_declaration_order(self, sdk, session, base_grid):
        grid, _ = base_grid
        a = await _cells(session, 2, "a")
        b = await _cells(session, 2, "b")

        out = await sdk.extend_parameter_sweep(grid, add_cols={"C2": a, "C3": b})
        matrix, _, cols = await _matrix_of(sdk, out)

        assert cols == ["C0", "C1", "C2", "C3"]
        assert [row[2] for row in matrix] == a
        assert [row[3] for row in matrix] == b

    async def test_wrong_cell_count_is_rejected(self, sdk, session, base_grid):
        grid, _ = base_grid
        short = await _cells(session, 1, "short")
        with pytest.raises(ValueError, match="expected 2 cells, got 1"):
            await sdk.extend_parameter_sweep(grid, add_cols={"C2": short})

    async def test_duplicate_header_is_rejected(self, sdk, session, base_grid):
        grid, _ = base_grid
        new = await _cells(session, 2, "dup")
        with pytest.raises(ValueError, match="already exists"):
            await sdk.extend_parameter_sweep(grid, add_cols={"C0": new})

    async def test_original_grid_is_left_intact(self, sdk, session, base_grid):
        grid, ids = base_grid
        new = await _cells(session, 2, "keep")

        await sdk.extend_parameter_sweep(grid, add_cols={"C2": new})
        matrix, _, cols = await _matrix_of(sdk, grid)

        assert cols == ["C0", "C1"]
        assert matrix == [[ids[0], ids[1]], [ids[2], ids[3]]]


class TestAddRows:
    async def test_row_is_appended(self, sdk, session, base_grid):
        grid, ids = base_grid
        new = await _cells(session, 2, "newrow")

        out = await sdk.extend_parameter_sweep(grid, add_rows={"R2": new})
        matrix, rows, _ = await _matrix_of(sdk, out)

        assert rows == ["R0", "R1", "R2"]
        assert matrix[2] == new


class TestReplace:
    async def test_replace_row_by_header(self, sdk, session, base_grid):
        grid, ids = base_grid
        redone = await _cells(session, 2, "redone")

        out = await sdk.extend_parameter_sweep(grid, replace_rows={"R1": redone})
        matrix, rows, _ = await _matrix_of(sdk, out)

        assert rows == ["R0", "R1"]
        assert matrix == [[ids[0], ids[1]], redone]

    async def test_replace_column_by_header(self, sdk, session, base_grid):
        grid, ids = base_grid
        redone = await _cells(session, 2, "redonecol")

        out = await sdk.extend_parameter_sweep(grid, replace_cols={"C0": redone})
        matrix, _, _ = await _matrix_of(sdk, out)

        assert [row[0] for row in matrix] == redone
        assert [row[1] for row in matrix] == [ids[1], ids[3]]

    async def test_replace_unknown_header_is_rejected(self, sdk, session, base_grid):
        grid, _ = base_grid
        redone = await _cells(session, 2, "nope")
        with pytest.raises(ValueError, match="no row 'R9'"):
            await sdk.extend_parameter_sweep(grid, replace_rows={"R9": redone})

    async def test_replace_then_add_uses_new_geometry_for_rows(self, sdk, session, base_grid):
        """
        A row replaced in the same call as a column addition supplies cells for
        the ORIGINAL column count; the added column then extends it. Getting
        this order wrong would silently drop or shift a cell.
        """
        grid, ids = base_grid
        redone = await _cells(session, 2, "r1")   # 2 cells: original col count
        added = await _cells(session, 2, "c2")    # 2 cells: one per row

        out = await sdk.extend_parameter_sweep(
            grid, replace_rows={"R1": redone}, add_cols={"C2": added}
        )
        matrix, rows, cols = await _matrix_of(sdk, out)

        assert rows == ["R0", "R1"]
        assert cols == ["C0", "C1", "C2"]
        assert matrix == [
            [ids[0], ids[1], added[0]],
            [redone[0], redone[1], added[1]],
        ]


class TestLoadSweep:
    async def test_rejects_non_grid_media(self, sdk, session):
        item = await create_media_item(
            session, file_path=Path("/tmp/stimma-test/plain.png")
        )
        with pytest.raises(ValueError, match="not a parameter sweep"):
            await sdk.extend_parameter_sweep(item.id, add_cols={})

    async def test_rejects_missing_media(self, sdk):
        with pytest.raises(ValueError, match="No media item"):
            await sdk.extend_parameter_sweep(999999, add_cols={})
