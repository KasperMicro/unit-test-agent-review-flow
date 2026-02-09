"""Integration-style tests for Flask routes defined in app.py.

These tests exercise the HTTP API using Flask's test client.
"""

import pytest

from app import users, calculations


def test_index_route(client):
    """GET / should return a welcome message and version information."""
    # Act
    response = client.get("/")

    # Assert
    assert response.status_code == 200, "Index route should return HTTP 200"
    data = response.get_json()
    assert data["message"] == "Welcome to the Calculator API"
    assert data["version"] == "1.0"


def test_health_route(client):
    """GET /health should report a healthy status."""
    # Act
    response = client.get("/health")

    # Assert
    assert response.status_code == 200, "Health route should return HTTP 200"
    assert response.get_json() == {"status": "healthy"}


@pytest.mark.parametrize("operation,a,b,expected", [
    ("add", 1, 2, 3.0),
    ("subtract", 5, 3, 2.0),
    ("multiply", 2, 4, 8.0),
    ("divide", 6, 3, 2.0),
])
def test_calculate_happy_paths(client, operation, a, b, expected):
    """POST /calculate should perform operations and record history."""
    # Arrange
    payload = {"operation": operation, "a": a, "b": b}

    # Act
    response = client.post("/calculate", json=payload)

    # Assert
    assert response.status_code == 200, "Valid calculation should return HTTP 200"
    data = response.get_json()
    assert data["result"] == expected, "Unexpected calculation result"
    assert len(calculations) == 1, "Calculation should be recorded in history"
    assert calculations[-1]["result"] == expected, "History result mismatch"


def test_calculate_no_body_returns_400(client):
    """POST /calculate with no body should return a 400 error."""
    # Act
    response = client.post("/calculate")

    # Assert
    assert response.status_code == 400, "Expected HTTP 400 for missing body"
    data = response.get_json()
    assert data["error"] == "No data provided"


def test_calculate_non_json_body_returns_400(client):
    """POST /calculate with non-JSON body should return a 400 error."""
    # Act
    response = client.post("/calculate", data="not-json", content_type="text/plain")

    # Assert
    assert response.status_code == 400, "Expected HTTP 400 for non-JSON body"
    data = response.get_json()
    assert data["error"] == "No data provided"


@pytest.mark.parametrize("payload", [
    {"a": 1, "b": 2},
    {"operation": "add", "b": 2},
    {"operation": "add", "a": 1},
])
def test_calculate_missing_fields_returns_400(client, payload):
    """POST /calculate should validate presence of operation, a, and b."""
    # Act
    response = client.post("/calculate", json=payload)

    # Assert
    assert response.status_code == 400, "Expected HTTP 400 for missing fields"
    data = response.get_json()
    assert data["error"] == "Missing required fields: operation, a, b"


@pytest.mark.parametrize("a,b", [
    ("not-a-number", 2),
    (1, "not-a-number"),
    ("x", "y"),
])
def test_calculate_non_numeric_inputs_return_400(client, a, b):
    """POST /calculate should reject non-numeric operands."""
    # Arrange
    payload = {"operation": "add", "a": a, "b": b}

    # Act
    response = client.post("/calculate", json=payload)

    # Assert
    assert response.status_code == 400, "Expected HTTP 400 for non-numeric input"
    data = response.get_json()
    assert data["error"] == "a and b must be numbers"


def test_calculate_unknown_operation_returns_400(client):
    """POST /calculate should reject unknown operations."""
    # Arrange
    payload = {"operation": "mod", "a": 5, "b": 2}

    # Act
    response = client.post("/calculate", json=payload)

    # Assert
    assert response.status_code == 400, "Expected HTTP 400 for unknown op"
    data = response.get_json()
    assert data["error"] == "Unknown operation: mod"


def test_calculate_divide_by_zero_returns_400(client):
    """POST /calculate divide by zero should surface ValueError as 400."""
    # Arrange
    payload = {"operation": "divide", "a": 1, "b": 0}

    # Act
    response = client.post("/calculate", json=payload)

    # Assert
    assert response.status_code == 400, "Expected HTTP 400 for divide by zero"
    data = response.get_json()
    assert data["error"] == "Cannot divide by zero"


def test_users_get_empty_returns_empty_list(client):
    """GET /users should return an empty list when no users exist."""
    # Act
    response = client.get("/users")

    # Assert
    assert response.status_code == 200, "Expected HTTP 200 from /users"
    data = response.get_json()
    assert data["users"] == [], "Expected empty users list"


def test_users_get_populated_returns_all_users(client):
    """GET /users should return all stored users."""
    # Arrange
    users["alice"] = {"username": "alice", "email": "alice@example.com", "active": True}
    users["bob"] = {"username": "bob", "email": "bob@example.com", "active": True}

    # Act
    response = client.get("/users")

    # Assert
    assert response.status_code == 200, "Expected HTTP 200 from /users"
    data = response.get_json()
    user_list = data["users"]
    assert isinstance(user_list, list), "Response 'users' field should be a list"
    assert len(user_list) == 2, "Expected two users in response"
    assert any(u["username"] == "alice" for u in user_list), "Alice missing from users list"
    assert any(u["username"] == "bob" for u in user_list), "Bob missing from users list"


def test_users_post_create_success(client):
    """POST /users should create a user with valid input."""
    # Arrange
    payload = {"username": "alice", "email": "alice@example.com"}

    # Act
    response = client.post("/users", json=payload)

    # Assert
    assert response.status_code == 201, "User creation should return HTTP 201"
    data = response.get_json()
    user = data["user"]
    assert user["username"] == "alice", "Username not echoed correctly"
    assert user["email"] == "alice@example.com", "Email not echoed correctly"
    assert user.get("active") is True, "User should be active by default"
    assert "alice" in users, "User not stored in global users dict"


def test_users_post_no_body_returns_400(client):
    """POST /users with no body should return a 400 error."""
    # Act
    response = client.post("/users")

    # Assert
    assert response.status_code == 400, "Expected HTTP 400 for missing user body"
    data = response.get_json()
    assert data["error"] == "No data provided"


@pytest.mark.parametrize("payload,expected_error", [
    ({"username": "", "email": "test@example.com"}, "Username and email are required"),
    ({"username": "alice", "email": ""}, "Username and email are required"),
])
def test_users_post_missing_fields_returns_400(client, payload, expected_error):
    """POST /users should enforce required username and email fields."""
    # Act
    response = client.post("/users", json=payload)

    # Assert
    assert response.status_code == 400, "Expected HTTP 400 for invalid user body"
    data = response.get_json()
    assert data["error"] == expected_error


def test_users_post_duplicate_username_returns_400(client):
    """POST /users should reject duplicate usernames."""
    # Arrange
    users["alice"] = {"username": "alice", "email": "alice@example.com", "active": True}
    payload = {"username": "alice", "email": "alice2@example.com"}

    # Act
    response = client.post("/users", json=payload)

    # Assert
    assert response.status_code == 400, "Expected HTTP 400 for duplicate user"
    data = response.get_json()
    assert data["error"] == "User 'alice' already exists"


def test_users_post_invalid_email_returns_400(client):
    """POST /users should reject invalid email formats."""
    # Arrange
    payload = {"username": "alice", "email": "invalid-email"}

    # Act
    response = client.post("/users", json=payload)

    # Assert
    assert response.status_code == 400, "Expected HTTP 400 for invalid email"
    data = response.get_json()
    assert data["error"] == "Invalid email format"


def test_user_get_existing_returns_user(client):
    """GET /users/<username> should return the user when it exists."""
    # Arrange
    users["alice"] = {"username": "alice", "email": "alice@example.com", "active": True}

    # Act
    response = client.get("/users/alice")

    # Assert
    assert response.status_code == 200, "Expected HTTP 200 for existing user"
    data = response.get_json()
    user = data["user"]
    assert user["username"] == "alice", "Username mismatch in user response"
    assert user["email"] == "alice@example.com", "Email mismatch in user response"


def test_user_get_nonexistent_returns_404(client):
    """GET /users/<username> should return 404 for unknown users."""
    # Act
    response = client.get("/users/missing")

    # Assert
    assert response.status_code == 404, "Expected HTTP 404 for missing user"
    assert response.get_json() == {"error": "User not found"}


def test_user_delete_existing_returns_200_and_removes_user(client):
    """DELETE /users/<username> should delete an existing user."""
    # Arrange
    users["alice"] = {"username": "alice", "email": "alice@example.com", "active": True}

    # Act
    response = client.delete("/users/alice")

    # Assert
    assert response.status_code == 200, "Expected HTTP 200 on successful delete"
    data = response.get_json()
    assert data["message"] == "User 'alice' deleted"
    assert "alice" not in users, "User should be removed after delete"


def test_user_delete_nonexistent_returns_404(client):
    """DELETE /users/<username> should return 404 for unknown users."""
    # Act
    response = client.delete("/users/missing")

    # Assert
    assert response.status_code == 404, "Expected HTTP 404 for missing user delete"
    assert response.get_json() == {"error": "User not found"}


def test_history_initially_empty_returns_empty_list(client):
    """GET /history should return an empty list when no calculations exist."""
    # Act
    response = client.get("/history")

    # Assert
    assert response.status_code == 200, "Expected HTTP 200 from /history"
    data = response.get_json()
    assert data["calculations"] == [], "Expected empty calculations history"


def test_history_after_calculations_returns_all_entries(client):
    """GET /history should return all performed calculations in order."""
    # Arrange - perform a couple of calculations
    client.post("/calculate", json={"operation": "add", "a": 1, "b": 2})
    client.post("/calculate", json={"operation": "multiply", "a": 3, "b": 4})

    # Act
    response = client.get("/history")

    # Assert
    assert response.status_code == 200, "Expected HTTP 200 from /history"
    data = response.get_json()
    history = data["calculations"]
    assert len(history) == 2, "Expected two calculations in history"
    assert history[0]["operation"] == "add", "First history entry operation mismatch"
    assert history[0]["result"] == 3.0, "First history entry result mismatch"
    assert history[1]["operation"] == "multiply", "Second history entry operation mismatch"
    assert history[1]["result"] == 12.0, "Second history entry result mismatch"
