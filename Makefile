.PHONY: monitor-alert-test-on monitor-alert-test-off monitor-restart-prom

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
