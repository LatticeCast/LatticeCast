.PHONY: e2e

# Start the E2E runner and remote Chromium, then run the complete suite.
e2e:
	docker compose --profile test up -d browser e2e
	docker compose exec -T e2e pytest --tb=short -q
