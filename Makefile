.PHONY: setup
setup:
	uv sync --extra dev
	uv run python scripts/fetch_ocr.py