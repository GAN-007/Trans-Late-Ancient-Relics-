.PHONY: install run test compile check docker

install:
	python -m pip install -r requirements.txt

run:
	uvicorn app.main:app --reload

test:
	pytest -q

compile:
	python -m compileall -q app cli.py

check: compile test

docker:
	docker compose up --build
