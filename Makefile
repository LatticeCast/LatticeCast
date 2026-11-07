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
	# Backend workers do not reload bind-mounted source; test the current checkout.
	$(COMPOSE) restart backend frontend
	# Resolve upstream container addresses only after both services have restarted.
	$(COMPOSE) restart lattice-cast
	$(COMPOSE) up -d --wait --wait-timeout 120 backend frontend lattice-cast
	# Container health can precede proxy readiness; test the same URL pytest uses.
	@for attempt in $$(seq 1 30); do \
		if $(COMPOSE) exec -T e2e python -c 'import os, requests; base = os.environ["BASE_URL"]; assert requests.get(base + "/api/v1/status", timeout=3).status_code == 200; assert requests.get(base + "/status", timeout=3).status_code == 200' >/dev/null 2>&1; then \
			break; \
		fi; \
		if [ "$$attempt" -eq 30 ]; then echo 'E2E target did not become ready' >&2; exit 1; fi; \
		sleep 2; \
	done

# Run the complete Playwright-backed E2E suite. Override E2E_PYTEST_ARGS as needed.
e2e: e2e-up
	$(COMPOSE) exec -T e2e pytest $(E2E_PYTEST_ARGS)
