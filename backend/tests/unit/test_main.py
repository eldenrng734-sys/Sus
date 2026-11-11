from app.main import app


def test_auth_routers_are_registered():
    paths = app.openapi()["paths"]

    assert "/api/v1/auth/login" in paths
    assert "/api/v1/auth/password-reset" in paths
    assert "/health" in paths
