# Paw Control Makefile
.PHONY: help install dev test lint format clean validate release docker

PYTHON := python3
PIP := $(PYTHON) -m pip
VENV := venv
CUSTOM_COMPONENTS := custom_components/pawcontrol

help: ## Show this help message
	@echo "Paw Control - Development Commands"
	@echo "=================================="
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install the integration to Home Assistant
	@echo "Installing Paw Control to Home Assistant..."
	@if [ -d "/config/custom_components" ]; then \
		cp -r $(CUSTOM_COMPONENTS) /config/custom_components/; \
		echo "✅ Installation complete. Restart Home Assistant."; \
	else \
		echo "❌ Home Assistant config directory not found. Run: make install-local"; \
	fi

install-local: ## Install to local Home Assistant (~/homeassistant)
	@echo "Installing to local Home Assistant..."
	@mkdir -p ~/homeassistant/custom_components
	@cp -r $(CUSTOM_COMPONENTS) ~/homeassistant/custom_components/
	@echo "✅ Installation complete."

dev: ## Setup development environment
	@echo "Setting up development environment..."
	@$(PYTHON) -m venv $(VENV)
	@. $(VENV)/bin/activate && $(PIP) install --upgrade pip
	@. $(VENV)/bin/activate && $(PIP) install -r requirements_dev.txt
	@. $(VENV)/bin/activate && pre-commit install
	@echo "✅ Development environment ready. Activate with: source $(VENV)/bin/activate"

test: ## Run tests with coverage
	@echo "Running tests..."
	@. $(VENV)/bin/activate && pytest tests/ \
		--cov=$(CUSTOM_COMPONENTS) \
		--cov-report=term-missing \
		--cov-report=html \
		--cov-report=xml

test-watch: ## Run tests in watch mode
	@echo "Running tests in watch mode..."
	@. $(VENV)/bin/activate && pytest-watch tests/ -c

lint: ## Run all linters
	@echo "Running linters..."
	@. $(VENV)/bin/activate && black --check $(CUSTOM_COMPONENTS)
	@. $(VENV)/bin/activate && isort --check-only $(CUSTOM_COMPONENTS)
	@. $(VENV)/bin/activate && flake8 $(CUSTOM_COMPONENTS)
	@. $(VENV)/bin/activate && mypy $(CUSTOM_COMPONENTS)
	@. $(VENV)/bin/activate && yamllint -c .yamllint $(CUSTOM_COMPONENTS)

format: ## Format code with black and isort
	@echo "Formatting code..."
	@. $(VENV)/bin/activate && black $(CUSTOM_COMPONENTS)
	@. $(VENV)/bin/activate && isort $(CUSTOM_COMPONENTS)
	@echo "✅ Code formatted."

validate: ## Validate with HACS and hassfest
	@echo "Validating integration..."
	@echo "Checking manifest..."
	@python scripts/validate_manifest.py
	@echo "Running hassfest..."
	@. $(VENV)/bin/activate && python -m script.hassfest
	@echo "✅ Validation complete."

clean: ## Clean up generated files
	@echo "Cleaning up..."
	@rm -rf $(VENV)
	@rm -rf .pytest_cache
	@rm -rf .mypy_cache
	@rm -rf htmlcov
	@rm -rf .coverage
	@rm -rf coverage.xml
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete
	@echo "✅ Cleanup complete."

docker: ## Run Home Assistant in Docker for testing
	@echo "Starting Home Assistant in Docker..."
	@docker run -d \
		--name homeassistant-test \
		-v $(PWD)/custom_components:/config/custom_components \
		-v $(PWD)/config:/config \
		-p 8123:8123 \
		--restart unless-stopped \
		homeassistant/home-assistant:latest
	@echo "✅ Home Assistant running at http://localhost:8123"

docker-stop: ## Stop Home Assistant Docker container
	@echo "Stopping Home Assistant Docker..."
	@docker stop homeassistant-test
	@docker rm homeassistant-test
	@echo "✅ Container stopped."

release: ## Create a release package
	@echo "Creating release package..."
	@rm -f pawcontrol.zip
	@cd custom_components && zip -r ../pawcontrol.zip pawcontrol/
	@echo "✅ Release package created: pawcontrol.zip"

check-all: lint test validate ## Run all checks
	@echo "✅ All checks passed!"

pre-commit: ## Run pre-commit hooks
	@. $(VENV)/bin/activate && pre-commit run --all-files

update-deps: ## Update dependencies
	@echo "Updating dependencies..."
	@. $(VENV)/bin/activate && $(PIP) install --upgrade -r requirements_dev.txt
	@. $(VENV)/bin/activate && pre-commit autoupdate
	@echo "✅ Dependencies updated."

version: ## Show version
	@grep '"version"' $(CUSTOM_COMPONENTS)/manifest.json | cut -d'"' -f4

bump-version: ## Bump version (usage: make bump-version VERSION=1.0.1)
	@if [ -z "$(VERSION)" ]; then \
		echo "❌ Please specify VERSION. Example: make bump-version VERSION=1.0.1"; \
		exit 1; \
	fi
	@echo "Bumping version to $(VERSION)..."
	@sed -i 's/"version": ".*"/"version": "$(VERSION)"/' $(CUSTOM_COMPONENTS)/manifest.json
	@sed -i 's/version = ".*"/version = "$(VERSION)"/' pyproject.toml
	@echo "✅ Version bumped to $(VERSION)"
