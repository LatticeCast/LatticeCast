COMPOSE ?= docker compose
E2E_PYTEST_ARGS ?= --tb=short -q

.PHONY: e2e e2e-up lint lint-be lint-fe lint-db

# Run the same backend, frontend, and migration linters enforced by pre-commit.
lint: lint-be lint-fe lint-db

lint-be:
	$(COMPOSE) exec -T backend uv run ruff check src tests

lint-fe:
	$(COMPOSE) exec -T frontend npm run lint:check

lint-db:
	$(COMPOSE) --profile migration run --rm --entrypoint python migration linter.py

# Start the remote Chromium and E2E runner required by the test suite.
e2e-up:
	$(COMPOSE) --profile test up -d browser e2e

# Run the complete Playwright-backed E2E suite. Override E2E_PYTEST_ARGS as needed.
e2e: e2e-up
	$(COMPOSE) exec -T e2e pytest $(E2E_PYTEST_ARGS)
