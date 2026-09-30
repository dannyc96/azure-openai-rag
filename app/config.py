"""Application settings, read once from the environment.

Every value here is an identifier (endpoint URL, deployment name, index
name). There are no keys or secrets: authentication is handled entirely
by DefaultAzureCredential, which resolves to the Container App's managed
identity in Azure and to your az login session locally.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    openai_endpoint: str
    chat_deployment: str
    embedding_deployment: str
    search_endpoint: str
    search_index: str
    api_version: str = "2024-10-21"


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(
            f"Missing required environment variable {name}. "
            "Populate it from 'terraform output' (see the README)."
        )
    return value


def load_settings() -> Settings:
    return Settings(
        openai_endpoint=_require("AZURE_OPENAI_ENDPOINT"),
        chat_deployment=_require("AZURE_OPENAI_CHAT_DEPLOYMENT"),
        embedding_deployment=_require("AZURE_OPENAI_EMBEDDING_DEPLOYMENT"),
        search_endpoint=_require("AZURE_SEARCH_ENDPOINT"),
        search_index=_require("AZURE_SEARCH_INDEX"),
    )
