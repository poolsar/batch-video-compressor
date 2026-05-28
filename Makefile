.PHONY: install test lint format check dev

install:
	uv sync

test:
	uv run pytest tests/ -v

lint:
	uv run ruff check .

format:
	uv run ruff format .

check: lint test

dev:
	uv run python compress.py
