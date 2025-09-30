# PawControl Testing Infrastructure

Complete testing suite for the PawControl Home Assistant integration.

## 🎯 Overview

- **Unit Tests:** 55+ tests covering core business logic
- **Integration Tests:** Config flow and HA integration
- **Coverage Target:** 80%+
- **Async Support:** Full pytest-asyncio integration
- **Fixtures:** Comprehensive mock environment

## 📋 Prerequisites

```bash
# Install test dependencies
pip install -r requirements_test.txt

# Dependencies included:
# - pytest>=7.4.0
# - pytest-asyncio>=0.21.0
# - pytest-cov>=4.1.0
# - pytest-homeassistant-custom-component
```

## 🚀 Running Tests

### Run All Tests
```bash
pytest
```

### Run Specific Test Types
```bash
# Unit tests only
pytest -m unit

# Integration tests only
pytest -m integration

# Exclude slow tests
pytest -m "not slow"

# Run specific test file
pytest tests/unit/test_feeding_manager.py

# Run specific test class
pytest tests/unit/test_feeding_manager.py::TestCalorieCalculations

# Run specific test
pytest tests/unit/test_feeding_manager.py::TestCalorieCalculations::test_calculate_rer_basic
```

### With Coverage
```bash
# Generate coverage report
pytest --cov=custom_components.pawcontrol --cov-report=html

# View coverage in browser
open htmlcov/index.html
```

### Verbose Output
```bash
# Show test names and output
pytest -v -s

# Show only failed tests
pytest --tb=short

# Stop at first failure
pytest -x
```

## 📊 Test Structure

```
tests/
├── conftest.py                 # Shared fixtures and configuration
├── pytest.ini                  # Pytest configuration
│
├── unit/                       # Unit tests (fast, isolated)
│   ├── test_coordinator.py    # Coordinator logic
│   ├── test_feeding_manager.py # Feeding calculations
│   ├── test_gps_manager.py    # GPS and geofencing
│   ├── test_notifications.py  # Notification system
│   ├── test_walk_manager.py   # Walk tracking
│   └── test_resilience.py     # Resilience patterns
│
└── integration/                # Integration tests (slower, with HA)
    ├── test_config_flow.py    # Configuration flow
    ├── test_services.py       # Service calls
    └── test_platforms.py      # Entity platforms
```

## 🔧 Available Fixtures

### Core Fixtures
```python
@pytest.fixture
async def mock_hass():
    """Mock Home Assistant instance."""

@pytest.fixture
def mock_config_entry():
    """Mock ConfigEntry with dog configuration."""

@pytest.fixture
async def mock_coordinator():
    """Initialized PawControlCoordinator."""

@pytest.fixture
async def mock_feeding_manager():
    """Initialized FeedingManager."""

@pytest.fixture
async def mock_gps_manager():
    """Initialized GPSGeofenceManager."""
```

### Helper Fixtures
```python
@pytest.fixture
def create_feeding_event():
    """Factory for creating feeding events."""

@pytest.fixture
def create_walk_event():
    """Factory for creating walk events."""

@pytest.fixture
def assert_valid_dog_data():
    """Helper to validate dog data structure."""
```

## 📝 Writing Tests

### Unit Test Example
```python
import pytest

@pytest.mark.unit
@pytest.mark.asyncio
async def test_calculate_portion(mock_feeding_manager):
    """Test portion calculation."""
    portion = mock_feeding_manager.calculate_portion("test_dog", "breakfast")
    
    assert 100 < portion < 500
    assert isinstance(portion, float)
```

### Integration Test Example
```python
import pytest
from homeassistant.core import HomeAssistant

@pytest.mark.integration
@pytest.mark.asyncio
async def test_service_call(hass: HomeAssistant, mock_config_entry):
    """Test service call integration."""
    mock_config_entry.add_to_hass(hass)
    
    await hass.services.async_call(
        "pawcontrol",
        "feed_dog",
        {"dog_id": "buddy", "amount": 200.0}
    )
    
    # Assert service effects
```

## 🎯 Test Categories

### Unit Tests (`-m unit`)
- **Fast:** < 1 second per test
- **Isolated:** No HA dependencies
- **Coverage:** Core business logic

### Integration Tests (`-m integration`)
- **Slower:** May take several seconds
- **HA Required:** Full Home Assistant instance
- **Coverage:** Config flow, services, platforms

### Load Tests (`-m load`)
- **Performance:** Test under load
- **Concurrent:** Multiple operations
- **Optional:** Run with `--run-load` flag

## 📈 Coverage Goals

| Component | Target | Current |
|-----------|--------|---------|
| Core Logic | 90%+ | 🟢 |
| Managers | 85%+ | 🟢 |
| Config Flow | 80%+ | 🟡 |
| Services | 80%+ | 🟡 |
| **Overall** | **80%+** | **🟡 In Progress** |

## 🐛 Debugging Tests

### Debug Single Test
```bash
# Run with debugger
pytest --pdb tests/unit/test_feeding_manager.py::test_specific

# Show print statements
pytest -s tests/unit/test_feeding_manager.py

# Show full traceback
pytest --tb=long
```

### Check Test Discovery
```bash
# List all tests without running
pytest --collect-only
```

## ⚡ Performance Tips

1. **Run Unit Tests First:** Fast feedback loop
2. **Use `-x`:** Stop at first failure
3. **Use `-k`:** Filter by test name pattern
4. **Parallel Execution:** `pytest -n auto` (requires pytest-xdist)

## 🔍 Continuous Integration

### GitHub Actions (Recommended)
```yaml
name: Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.13'
      - run: pip install -r requirements_test.txt
      - run: pytest --cov --cov-report=xml
      - uses: codecov/codecov-action@v3
```

## 📚 Additional Resources

- [Pytest Documentation](https://docs.pytest.org/)
- [pytest-asyncio Documentation](https://pytest-asyncio.readthedocs.io/)
- [Home Assistant Testing](https://developers.home-assistant.io/docs/development_testing)
- [Coverage.py Documentation](https://coverage.readthedocs.io/)

## 🤝 Contributing Tests

When contributing tests:

1. ✅ Follow existing test structure
2. ✅ Use appropriate markers (`@pytest.mark.unit`)
3. ✅ Write descriptive test names
4. ✅ Include docstrings
5. ✅ Test edge cases and errors
6. ✅ Maintain 80%+ coverage

## 📞 Support

For test-related issues:
1. Check test output for detailed errors
2. Review fixture documentation in `conftest.py`
3. Run with `-v -s` for detailed output
4. Open issue with test failure details
