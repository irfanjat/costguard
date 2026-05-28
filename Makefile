.PHONY: install lint test clean package deploy

install:
	pip install -e ".[dev]"

lint:
	ruff check src/ tests/

lint-fix:
	ruff check --fix src/ tests/

test:
	pytest -v tests/

clean:
	rm -rf dist/ build/ *.egg-info .ruff_cache __pycache__ */__pycache__

package:
	rm -rf dist && mkdir -p dist
	pip install -r requirements.txt --target dist/
	cp -r src/* dist/
	cd dist && zip -r ../costguard.zip .

deploy: package
	terraform -chdir=terraform apply -auto-approve

deploy-plan:
	terraform -chdir=terraform plan
