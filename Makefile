PY ?= python3
.PHONY: install install-ai run test lint bench eval calibrate-iqa

install:        ## backend + dev tools (no AI models)
	cd backend && $(PY) -m pip install -e ".[dev]"
install-ai:     ## + YOLO / MediaPipe
	cd backend && $(PY) -m pip install -e ".[dev,ai]"
run:            ## start backend (needs YOLO for pose AI)
	cd backend && $(PY) -m echo_move
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
