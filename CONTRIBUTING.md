# Contributing to Paw Control

First off, thank you for considering contributing to Paw Control! It's people like you that make Paw Control such a great tool for dog owners using Home Assistant.

## Code of Conduct

This project and everyone participating in it is governed by our Code of Conduct. By participating, you are expected to uphold this code.

## How Can I Contribute?

### Reporting Bugs

Before creating bug reports, please check existing issues as you might find out that you don't need to create one. When you are creating a bug report, please include as many details as possible:

* **Use a clear and descriptive title** for the issue to identify the problem.
* **Describe the exact steps which reproduce the problem** in as many details as possible.
* **Provide specific examples to demonstrate the steps**.
* **Describe the behavior you observed after following the steps** and point out what exactly is the problem with that behavior.
* **Explain which behavior you expected to see instead and why.**
* **Include screenshots and animated GIFs** which show you following the described steps and clearly demonstrate the problem.
* **Include your Home Assistant version** and the version of Paw Control.
* **Include relevant logs** from Home Assistant.

### Suggesting Enhancements

Enhancement suggestions are tracked as GitHub issues. When creating an enhancement suggestion, please include:

* **Use a clear and descriptive title** for the issue to identify the suggestion.
* **Provide a step-by-step description of the suggested enhancement** in as many details as possible.
* **Provide specific examples to demonstrate the steps**.
* **Describe the current behavior** and **explain which behavior you expected to see instead** and why.
* **Explain why this enhancement would be useful** to most Paw Control users.

### Pull Requests

1. Fork the repo and create your branch from `dev`.
2. If you've added code that should be tested, add tests.
3. If you've changed APIs, update the documentation.
4. Ensure the test suite passes.
5. Make sure your code lints.
6. Issue that pull request!

## Development Setup

1. **Fork and clone the repository**
   ```bash
   git clone https://github.com/bigdaddy1990/pawcontrol.git
   cd pawcontrol
   ```

2. **Create a virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install development dependencies**
   ```bash
   pip install -r requirements_dev.txt
   ```

4. **Set up pre-commit hooks**
   ```bash
   pre-commit install
   ```

5. **Create a test Home Assistant configuration**
   ```bash
   mkdir test_config
   # Copy custom_components to test_config
   cp -r custom_components test_config/
   ```

## Coding Standards

### Python Style Guide

We use the following tools to maintain code quality:

* **Black** for code formatting
* **isort** for import sorting
* **Flake8** for linting
* **mypy** for type checking

Run all checks:
```bash
black custom_components/pawcontrol
isort custom_components/pawcontrol
flake8 custom_components/pawcontrol
mypy
```

> **Note:** `mypy` is configured in `pyproject.toml` with a `files` setting that scopes
> type checking to `custom_components/pawcontrol`. Running `mypy` without arguments
> only validates this integration package. If you add typed code elsewhere in the
> repository, update that setting to extend coverage.

### Commit Messages

* Use the present tense ("Add feature" not "Added feature")
* Use the imperative mood ("Move cursor to..." not "Moves cursor to...")
* Limit the first line to 72 characters or less
* Reference issues and pull requests liberally after the first line

### Documentation

* Use clear and concise language
* Include code examples where appropriate
* Update the README.md if needed
* Add docstrings to all public functions and classes

## Testing

### Running Tests

```bash
pytest tests/
```

### Running Tests with Coverage

```bash
pytest tests/ --cov=custom_components.pawcontrol --cov-report=html
```

### Writing Tests

* Write tests for all new functionality
* Ensure tests are isolated and don't depend on external services
* Use fixtures for common test data
* Mock external dependencies

## Project Structure

```
pawcontrol/
├── custom_components/
│   └── pawcontrol/
│       ├── __init__.py          # Integration setup
│       ├── config_flow.py       # Configuration UI
│       ├── const.py             # Constants
│       ├── coordinator.py       # Data coordinator
│       ├── helpers/             # Helper modules
│       ├── sensor.py            # Sensor platform
│       ├── binary_sensor.py     # Binary sensor platform
│       ├── button.py            # Button platform
│       ├── number.py            # Number platform
│       ├── select.py            # Select platform
│       ├── text.py              # Text platform
│       ├── switch.py            # Switch platform
│       ├── services.yaml        # Service definitions
│       └── translations/        # Translations
├── tests/                       # Test files
├── blueprints/                  # Blueprint examples
├── examples/                    # Usage examples
└── docs/                        # Documentation

```

## Release Process

1. Update version in `custom_components/pawcontrol/manifest.json`
2. Update CHANGELOG.md
3. Create a pull request from `dev` to `main`
4. After merge, create a GitHub release with tag `v{version}`
5. The release workflow will automatically create the release assets

## Questions?

Feel free to open an issue for any questions about contributing!

## Recognition

Contributors will be recognized in the README.md file. Thank you for your contributions!
