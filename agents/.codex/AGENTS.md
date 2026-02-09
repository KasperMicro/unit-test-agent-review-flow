# Pytest Testing Standards

## Overview
This document defines the standards for writing pytest unit tests in our codebase.

## Test File Structure

### Naming Conventions
- Test files: `test_<module>.py` or `<module>_test.py`
- Test functions: `test_<function>_<scenario>` (e.g., `test_calculate_total_with_empty_list`)
- Test classes: `Test<ClassName>` (e.g., `TestUserService`)

### Directory Structure
```
project/
├── src/
│   └── module.py
└── tests/
    ├── conftest.py          # Shared fixtures
    ├── test_module.py       # Tests for module.py
    └── unit/                 # Subdirectory for unit tests
        └── test_helpers.py
```

## Writing Tests

### AAA Pattern
Follow the Arrange-Act-Assert pattern:
```python
def test_add_numbers():
    # Arrange
    a = 5
    b = 3
    
    # Act
    result = add(a, b)
    
    # Assert
    assert result == 8
```

### Assertions
- Use specific assertions with meaningful messages
- Prefer `assert x == y` over `assert x`
- Use `pytest.raises()` for exception testing

```python
def test_division_by_zero():
    with pytest.raises(ZeroDivisionError, match="division by zero"):
        divide(10, 0)
```

### Fixtures
Use fixtures for reusable test setup:

```python
# conftest.py
@pytest.fixture
def sample_user():
    return User(name="Test", email="test@example.com")

@pytest.fixture
def db_session():
    session = create_session()
    yield session
    session.rollback()
```

### Parametrize
Use `@pytest.mark.parametrize` for testing multiple inputs:

```python
@pytest.mark.parametrize("input,expected", [
    (1, 1),
    (2, 4),
    (3, 9),
    (-1, 1),
])
def test_square(input, expected):
    assert square(input) == expected
```

## Test Coverage Requirements

### What Must Be Tested
1. **Public API functions** - All public functions/methods
2. **Edge cases** - Empty inputs, boundary values, null/None
3. **Error handling** - Exception paths, error messages
4. **Business logic** - Critical calculations and decisions

### What Can Be Skipped
1. Simple getters/setters without logic
2. Third-party library code
3. Configuration constants

## Mocking Guidelines

### When to Mock
- External API calls
- Database operations
- File system operations
- Time-dependent code
- Random number generation

### How to Mock
```python
from unittest.mock import Mock, patch

@patch('module.external_api_call')
def test_process_data(mock_api):
    mock_api.return_value = {"status": "ok"}
    result = process_data()
    assert result.success is True
    mock_api.assert_called_once()
```

## Test Quality Checklist
- [ ] Test has a descriptive name
- [ ] Test tests ONE thing
- [ ] Test is independent (no shared state)
- [ ] Test has clear assertions
- [ ] Edge cases are covered
- [ ] Mocks are properly configured
- [ ] No side effects between tests
