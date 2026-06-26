import pytest
import database.db as db_module
from database.db import init_db, seed_db
from app import app as flask_app


@pytest.fixture
def test_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    init_db()
    seed_db()
    return db_path


@pytest.fixture
def client(test_db):
    flask_app.config["TESTING"] = True
    flask_app.config["SECRET_KEY"] = "test-secret"
    return flask_app.test_client()
