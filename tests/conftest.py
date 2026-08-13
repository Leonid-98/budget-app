import pytest

from app import create_app, db


@pytest.fixture()
def app(tmp_path):
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'test.db'}",
        "SPLIT_RATIO": "0.5",
        "IDENTITY_HEADER": "X-Forwarded-Email",
        "USERS": [
            {"email": "lenya@example.com", "name": "Лёня", "dative": "Лёне", "side": "left"},
            {"email": "anya@example.com", "name": "Аня", "dative": "Ане", "side": "right"},
        ],
    })
    yield app


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def as_lenya(client):
    """Client that always sends the oauth2-proxy identity header."""
    client.environ_base["HTTP_X_FORWARDED_EMAIL"] = "lenya@example.com"
    return client
