PY ?= python3
.PHONY: install install-ai run demo test lint bench export-scenarios

install:        ## backend + dev tools (no AI models)
	cd backend && $(PY) -m pip install -e ".[dev]"
install-ai:     ## + YOLO / MediaPipe
	cd backend && $(PY) -m pip install -e ".[dev,ai]"
run:            ## start backend (AI if models installed, otherwise demo)
	cd backend && $(PY) -m echo_move
demo:           ## force demo mode
	cd backend && ECHO_DEMO_MODE=1 $(PY) -m echo_move
test:
	cd backend && $(PY) -m pytest -q
lint:
	cd backend && $(PY) -m ruff check src tests && $(PY) -m mypy src
bench:
	$(PY) scripts/benchmark.py
export-scenarios:
	$(PY) scripts/export_scenarios.py
