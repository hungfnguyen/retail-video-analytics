.PHONY: help lint test test-cov run-vision docker-up docker-down docker-logs clean

# Default target
help:
	@echo "Retail Video Analytics — Development Commands"
	@echo ""
	@echo "  make lint          Run ruff linter and formatter check"
	@echo "  make format        Run ruff auto-fixer"
	@echo "  make test          Run all tests"
	@echo "  make test-cov      Run tests with coverage report"
	@echo "  make run-vision    Start multi-camera vision pipeline"
	@echo "  make docker-up     Start full infrastructure (AWS S3)"
	@echo "  make docker-down   Stop all infrastructure"
	@echo "  make docker-logs   Tail docker compose logs"
	@echo "  make sync          Install all workspace dependencies"
	@echo "  make clean         Remove __pycache__ and build artifacts"

lint:
	uv run ruff check . --extend-exclude='notebooks/*'

lint-all:
	uv run ruff check .

format:
	uv run ruff check . --extend-exclude='notebooks/*' --fix

test:
	uv run pytest tests/ -v

test-cov:
	uv run pytest tests/ -v --cov=. --cov-report=term-missing

run-vision:
	uv run --package rva-vision python services/vision/main.py

docker-up:
	docker compose up -d


docker-down:
	docker compose down

docker-logs:
	docker compose logs -f

sync:
	uv sync

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
