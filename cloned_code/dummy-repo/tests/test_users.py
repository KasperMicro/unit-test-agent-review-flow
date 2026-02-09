"""Unit tests for user management functions in app.py."""

import pytest

from app import create_user, get_user, delete_user, list_users, users


def test_create_user_success():
    """create_user() should create and store a user with valid input."""
    # Act
    user = create_user("alice", "alice@example.com")

    # Assert
    assert user["username"] == "alice", "Username not set correctly"
    assert user["email"] == "alice@example.com", "Email not set correctly"
    assert user.get("active") is True, "User should be active by default"
    assert users["alice"] == user, "User not stored in global users dict"


def test_create_user_missing_username_or_email_raises():
    """create_user() should require both username and email."""
    # Act / Assert
    with pytest.raises(ValueError, match="Username and email are required"):
        create_user("", "")


def test_create_user_duplicate_username_raises_value_error():
    """create_user() should reject duplicate usernames."""
    # Arrange
    create_user("alice", "alice@example.com")

    # Act / Assert
    with pytest.raises(ValueError, match="User 'alice' already exists"):
        create_user("alice", "alice2@example.com")


@pytest.mark.parametrize("email", [
    "invalid-email",
    "missing_at.example.com",
    "another-invalid",
])
def test_create_user_invalid_email_format_raises(email):
    """create_user() should validate email format for '@' presence."""
    # Act / Assert
    with pytest.raises(ValueError, match="Invalid email format"):
        create_user("alice", email)


def test_get_user_existing_user_returns_dict():
    """get_user() should return the stored user for an existing username."""
    # Arrange
    created = create_user("alice", "alice@example.com")

    # Act
    result = get_user("alice")

    # Assert
    assert result == created, "get_user() did not return the expected user"


def test_get_user_nonexistent_returns_none():
    """get_user() should return None when the user does not exist."""
    # Act
    result = get_user("missing")

    # Assert
    assert result is None, "Nonexistent user should yield None"


def test_delete_user_existing_returns_true_and_removes_user():
    """delete_user() should remove an existing user and return True."""
    # Arrange
    create_user("alice", "alice@example.com")

    # Act
    result = delete_user("alice")

    # Assert
    assert result is True, "delete_user() should return True on success"
    assert "alice" not in users, "User should be removed from storage"


def test_delete_user_nonexistent_returns_false():
    """delete_user() should return False when the user does not exist."""
    # Arrange
    create_user("bob", "bob@example.com")

    # Act
    result = delete_user("alice")

    # Assert
    assert result is False, "delete_user() should return False for missing user"
    assert "bob" in users, "Existing users should remain untouched"


def test_list_users_empty_returns_empty_list():
    """list_users() should return an empty list when no users exist."""
    # Act
    result = list_users()

    # Assert
    assert result == [], "Expected an empty list when no users are stored"


def test_list_users_multiple_returns_all_users():
    """list_users() should return all created users."""
    # Arrange
    u1 = create_user("alice", "alice@example.com")
    u2 = create_user("bob", "bob@example.com")

    # Act
    result = list_users()

    # Assert
    assert len(result) == 2, "Expected exactly two users in the list"
    assert u1 in result, "First user not found in list_users() output"
    assert u2 in result, "Second user not found in list_users() output"
