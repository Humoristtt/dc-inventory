from app.modules.catalog.configuration import (
    LEAF_DESCRIPTIONS,
    LEAVES,
)


def test_every_fixed_leaf_has_description() -> None:
    assert set(LEAF_DESCRIPTIONS) == set(LEAVES)

    for description in LEAF_DESCRIPTIONS.values():
        assert description.strip()
