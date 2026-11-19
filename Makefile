PY ?= python3
.PHONY: install install-ai run demo test lint bench eval calibrate-iqa export-scenarios

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
eval:           ## fall-rule evaluation: make eval DATASET=urfd ROOT=data/urfd
	$(PY) scripts/evaluate.py $(or $(DATASET),urfd) $(or $(ROOT),data/urfd)
calibrate-iqa:  ## prove/search IQA Overall weights on controlled degradations
	$(PY) scripts/calibrate_iqa.py --bases $(or $(BASES),8) --random $(or $(RANDOM),400)
export-scenarios:
	$(PY) scripts/export_scenarios.py
