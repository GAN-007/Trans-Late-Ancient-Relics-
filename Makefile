.PHONY: install run test check docker-build docker-run clean

install:
	python -m pip install -r requirements.txt

run:
	uvicorn app.main:app --reload

test:
	python -m pytest -q

check:
	python -m compileall -q app cli.py
	python -m pytest -q

docker-build:
	docker build -t trans-late-ancient-relics:local .

docker-run:
	docker run --rm -p 8000:8000 -e ESHB_ENV=development -e ESHB_SECURE_COOKIES=false trans-late-ancient-relics:local

clean:
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	rm -rf .pytest_cache
