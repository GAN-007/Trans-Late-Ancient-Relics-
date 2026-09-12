.PHONY: install run test check docker-build docker-run

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
	docker build -t eshb-ancient-egyptian-tutor .

docker-run:
	docker run --rm -p 8000:8000 eshb-ancient-egyptian-tutor
