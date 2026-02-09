"""Shared pytest fixtures for the dummy-repo tests.

Provides a Flask test client and ensures global state is reset
between tests.
"""
import pytest

from app import app, users, calculations


@pytest.fixture
def flask_app():
    """Provide the Flask application configured for testing.

    This fixture sets TESTING=True to enable Flask's testing mode
    and yields the app instance for use in tests.
    """
    app.config["TESTING"] = True
    yield app


@pytest.fixture
def client(flask_app):
    """Provide a Flask test client for sending requests to the app.

    Uses the application context created by ``flask_app`` and yields
    a fresh test client for each test.
    """
    with flask_app.test_client() as client:
        yield client


@pytest.fixture(autouse=True)
def reset_global_state():
    """Reset global in-memory state before and after each test.

    The application stores users and calculations in module-level
    globals. To keep tests independent, this fixture clears both
    ``users`` and ``calculations`` dictionaries/lists for every test.
    """
    users.clear()
    calculations.clear()
    yield
    users.clear()
    calculations.clear()
