.PHONY: monitor-alert-test-on monitor-alert-test-off monitor-restart-prom api-test api-lint api-check

monitor-alert-test-on:
	python3 monitoring/scripts/toggle_test_alert.py on
	@echo "Restarting Prometheus to reload rules..."
	docker compose -f docker-compose.monitoring.yml --env-file .env.monitoring restart prometheus

monitor-alert-test-off:
	python3 monitoring/scripts/toggle_test_alert.py off
	@echo "Restarting Prometheus to reload rules..."
	docker compose -f docker-compose.monitoring.yml --env-file .env.monitoring restart prometheus

monitor-restart-prom:
	docker compose -f docker-compose.monitoring.yml --env-file .env.monitoring restart prometheus

# API Testing & Validation (Phase 5)
api-test:
	@echo "Running Schemathesis API contract tests..."
	cd backend && pytest -m schemathesis -v

api-lint:
	@echo "Running Spectral OpenAPI linter..."
	cd frontend && npm run api:lint

api-check:
	@echo "Running full API validation (tests + lint)..."
	$(MAKE) api-test
	$(MAKE) api-lint
