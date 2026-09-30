# Azure OpenAI RAG reference app.
#
# Typical flow:
#   make deploy      provision everything with Terraform
#   make env         print the export lines for local runs
#   make ingest      chunk + embed + index sample_docs/ (needs env vars, see 'make env')
#   make run-local   run the API + UI on http://localhost:8000
#   make destroy     tear it all down, back to $0
#
# Auth everywhere is 'az login' + DefaultAzureCredential. No keys, no .env
# files with secrets. The env vars below are endpoints and names only.

SHELL     := /bin/bash
TF_DIR    := terraform
IMAGE     ?= ghcr.io/dannyc96/azure-openai-rag:latest
ENV_VARS  := AZURE_OPENAI_ENDPOINT AZURE_OPENAI_CHAT_DEPLOYMENT AZURE_OPENAI_EMBEDDING_DEPLOYMENT AZURE_SEARCH_ENDPOINT AZURE_SEARCH_INDEX

.PHONY: deploy destroy ingest run-local build-image fmt validate lint env check-env

deploy:
	terraform -chdir=$(TF_DIR) init
	terraform -chdir=$(TF_DIR) apply

destroy:
	terraform -chdir=$(TF_DIR) destroy

# Print copy-pasteable exports from terraform outputs. Usage:
#   eval "$$(make -s env)"
env:
	@echo "export AZURE_OPENAI_ENDPOINT=$$(terraform -chdir=$(TF_DIR) output -raw azure_openai_endpoint)"
	@echo "export AZURE_OPENAI_CHAT_DEPLOYMENT=$$(terraform -chdir=$(TF_DIR) output -raw chat_deployment_name)"
	@echo "export AZURE_OPENAI_EMBEDDING_DEPLOYMENT=$$(terraform -chdir=$(TF_DIR) output -raw embedding_deployment_name)"
	@echo "export AZURE_SEARCH_ENDPOINT=$$(terraform -chdir=$(TF_DIR) output -raw azure_search_endpoint)"
	@echo "export AZURE_SEARCH_INDEX=$$(terraform -chdir=$(TF_DIR) output -raw search_index_name)"

check-env:
	@missing=0; for v in $(ENV_VARS); do \
		if [ -z "$${!v}" ]; then echo "Missing $$v (run: eval \"\$$(make -s env)\")"; missing=1; fi; \
	done; exit $$missing

ingest: check-env
	python3 ingestion/ingest.py

run-local: check-env
	pip install -q -r app/requirements.txt
	uvicorn app.main:app --reload --port 8000

build-image:
	docker build -t $(IMAGE) app/
	@echo "Push it, then re-apply with the image set:"
	@echo "  docker push $(IMAGE)"
	@echo "  terraform -chdir=$(TF_DIR) apply -var container_image=$(IMAGE)"

fmt:
	terraform fmt -recursive $(TF_DIR)

validate:
	terraform -chdir=$(TF_DIR) init -backend=false -input=false
	terraform -chdir=$(TF_DIR) validate

lint:
	tflint --chdir=$(TF_DIR)
	ruff check app/ ingestion/
	python3 -m py_compile app/*.py ingestion/*.py
