"""Unit tests for pure calculator functions in app.py."""

import pytest

from app import add, subtract, multiply, divide


@pytest.mark.parametrize("a,b,expected", [
    (1, 1, 2),
    (-1, -1, -2),
    (5, -3, 2),
    (0, 5, 5),
    (1.5, 2.5, 4.0),
    (1e10, 1e10, 2e10),
])
def test_add_various_inputs(a, b, expected):
    """add() should return the arithmetic sum for a variety of inputs."""
    # Act
    result = add(a, b)

    # Assert
    assert result == expected, "add() returned an unexpected result"


@pytest.mark.parametrize("a,b,expected", [
    (5, 3, 2),
    (3, 5, -2),
    (-1, -1, 0),
    (0, 5, -5),
    (1.5, 0.5, 1.0),
])
def test_subtract_various_inputs(a, b, expected):
    """subtract() should correctly subtract b from a for common cases."""
    # Act
    result = subtract(a, b)

    # Assert
    assert result == expected, "subtract() returned an unexpected result"


@pytest.mark.parametrize("a,b,expected", [
    (2, 3, 6),
    (-2, 3, -6),
    (-2, -3, 6),
    (0, 5, 0),
    (1.5, 2.0, 3.0),
])
def test_multiply_various_inputs(a, b, expected):
    """multiply() should return the product of a and b."""
    # Act
    result = multiply(a, b)

    # Assert
    assert result == expected, "multiply() returned an unexpected result"


@pytest.mark.parametrize("a,b,expected", [
    (6, 3, 2.0),
    (-6, 3, -2.0),
    (5, 2, 2.5),
    (0, 5, 0.0),
])
def test_divide_various_inputs(a, b, expected):
    """divide() should correctly divide a by b for non-zero divisors."""
    # Act
    result = divide(a, b)

    # Assert
    assert result == expected, "divide() returned an unexpected result"


def test_divide_by_zero_raises_value_error():
    """divide() should raise ValueError with the documented message on /0."""
    # Act / Assert
    with pytest.raises(ValueError, match="Cannot divide by zero"):
        divide(1, 0)
