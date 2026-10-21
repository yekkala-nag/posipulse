.PHONY: install run test lint vercel-build clean

install:
	python3 -m venv .venv
	. .venv/bin/activate && pip install --upgrade pip && pip install -r requirements.txt

run:
	./run_local.sh

test:
	. .venv/bin/activate && pytest -v

vercel-build:
	pip install -r requirements.txt

clean:
	rm -rf __pycache__ .pytest_cache *.pyc
