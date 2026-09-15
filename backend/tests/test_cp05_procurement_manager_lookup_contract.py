from inspect import signature

from app.modules.procurement.api import get_managers
from app.modules.procurement.service import list_managers


def test_manager_lookup_accepts_server_side_search_contract() -> None:
    assert "q" in signature(get_managers).parameters
    assert "query" in signature(list_managers).parameters
