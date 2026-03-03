SHELL := /bin/bash
PYTHON := python3
VENV := .venv
PIP := $(VENV)/bin/pip
PYTEST := $(VENV)/bin/pytest
UVICORN := $(VENV)/bin/uvicorn

.PHONY: setup setup-python setup-node run test test-backend test-ui e2e

setup: setup-python setup-node

setup-python:
	@if [ ! -d "$(VENV)" ]; then $(PYTHON) -m venv $(VENV); fi
	@$(PIP) install -r requirements.txt
	@if [ ! -f ".env" ] && [ -f ".env.example" ]; then cp .env.example .env; fi

setup-node:
	@npm install

run:
	@source $(VENV)/bin/activate && uvicorn main:app --reload

test: test-backend test-ui

test-backend:
	@source $(VENV)/bin/activate && PYTHONPATH=. pytest -q

test-ui:
	@npm run test:ui

e2e:
	@source $(VENV)/bin/activate && PYTHONPATH=. pytest -q tests_e2e
