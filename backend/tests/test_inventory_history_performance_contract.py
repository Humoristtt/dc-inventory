import inspect

from app.modules.inventory.service import (
    list_movements_cursor,
)


def test_movement_cursor_has_no_count_or_offset() -> None:
    source = inspect.getsource(list_movements_cursor)

    assert "func.count" not in source
    assert ".offset(" not in source
    assert ".limit(limit + 1)" in source
    assert (
        "Movement.journal_seq < before_journal_seq"
        in source
    )
