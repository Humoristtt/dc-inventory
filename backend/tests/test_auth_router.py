from app.main import app


def test_auth_routes_are_registered() -> None:
    paths = set(app.openapi()["paths"])

    assert "/api/auth/telegram" in paths
    assert "/api/auth/me" in paths
    assert "/api/auth/logout" in paths
