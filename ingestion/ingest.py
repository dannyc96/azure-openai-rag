"""Ingest sample_docs/ into Azure AI Search.

Pipeline: read markdown -> chunk by headings with overlap -> embed with
Azure OpenAI text-embedding-3-large -> upsert into the search index.

Chunking strategy
-----------------
Markdown docs have natural semantic boundaries at headings, so we split
there first: each h1/h2/h3 section becomes a candidate chunk. Sections
longer than MAX_CHUNK_CHARS are further split on paragraph boundaries,
with OVERLAP_CHARS of trailing text carried into the next chunk so that
sentences near a split stay retrievable from either side. Every chunk
keeps its document title and heading, which the app surfaces as citations.

Idempotency
-----------
Document IDs are deterministic (sha1 of source path + chunk position), so
re-running upserts in place. The index is created if missing; pass
--recreate-index to drop and rebuild it after a schema change.

Auth: DefaultAzureCredential everywhere. Run 'az login' first, and make
sure your object ID was passed to Terraform as developer_object_id.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from azure.core.exceptions import ResourceNotFoundError
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    HnswAlgorithmConfiguration,
    SearchableField,
    SearchField,
    SearchFieldDataType,
    SearchIndex,
    SemanticConfiguration,
    SemanticField,
    SemanticPrioritizedFields,
    SemanticSearch,
    SimpleField,
    VectorSearch,
    VectorSearchProfile,
)
from openai import AzureOpenAI

COGNITIVE_SERVICES_SCOPE = "https://cognitiveservices.azure.com/.default"
EMBEDDING_DIMENSIONS = 3072  # text-embedding-3-large
MAX_CHUNK_CHARS = 2000
OVERLAP_CHARS = 200
EMBED_BATCH_SIZE = 16

HEADING_RE = re.compile(r"^(#{1,3})\s+(.*)$", re.MULTILINE)


@dataclass(frozen=True)
class Chunk:
    doc_id: str
    title: str
    source: str
    content: str


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------


def _split_long_section(text: str) -> list[str]:
    """Split an oversized section on paragraph boundaries, carrying a small
    overlap forward so context near the split survives retrieval."""
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    pieces: list[str] = []
    current = ""
    for paragraph in paragraphs:
        candidate = f"{current}\n\n{paragraph}".strip() if current else paragraph
        if len(candidate) <= MAX_CHUNK_CHARS:
            current = candidate
            continue
        if current:
            pieces.append(current)
            current = current[-OVERLAP_CHARS:] + "\n\n" + paragraph
        else:
            # Single paragraph longer than the limit: hard-split it.
            current = paragraph
            while len(current) > MAX_CHUNK_CHARS:
                pieces.append(current[:MAX_CHUNK_CHARS])
                current = current[MAX_CHUNK_CHARS - OVERLAP_CHARS :]
    if current:
        pieces.append(current)
    return pieces


def chunk_markdown(path: Path) -> list[Chunk]:
    """Split one markdown file into heading-scoped chunks."""
    text = path.read_text(encoding="utf-8")
    matches = list(HEADING_RE.finditer(text))
    doc_title = matches[0].group(2).strip() if matches else path.stem

    sections: list[tuple[str, str]] = []  # (heading, body)
    if not matches:
        sections.append((doc_title, text.strip()))
    else:
        for i, match in enumerate(matches):
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            body = text[match.end() : end].strip()
            if body:
                sections.append((match.group(2).strip(), body))

    chunks: list[Chunk] = []
    for heading, body in sections:
        for piece in _split_long_section(body):
            position = len(chunks)
            raw_id = f"{path.name}:{position}"
            chunks.append(
                Chunk(
                    doc_id=hashlib.sha1(raw_id.encode()).hexdigest(),
                    title=f"{doc_title}: {heading}" if heading != doc_title else doc_title,
                    source=path.name,
                    content=piece,
                )
            )
    return chunks


# ---------------------------------------------------------------------------
# Index management
# ---------------------------------------------------------------------------


def build_index_schema(name: str) -> SearchIndex:
    return SearchIndex(
        name=name,
        fields=[
            SimpleField(name="id", type=SearchFieldDataType.String, key=True),
            SearchableField(name="title", type=SearchFieldDataType.String),
            SimpleField(
                name="source",
                type=SearchFieldDataType.String,
                filterable=True,
                facetable=True,
            ),
            SearchableField(name="content", type=SearchFieldDataType.String),
            SearchField(
                name="contentVector",
                type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
                searchable=True,
                vector_search_dimensions=EMBEDDING_DIMENSIONS,
                vector_search_profile_name="default-profile",
            ),
        ],
        vector_search=VectorSearch(
            algorithms=[HnswAlgorithmConfiguration(name="default-hnsw")],
            profiles=[
                VectorSearchProfile(
                    name="default-profile",
                    algorithm_configuration_name="default-hnsw",
                )
            ],
        ),
        semantic_search=SemanticSearch(
            configurations=[
                SemanticConfiguration(
                    name="default",
                    prioritized_fields=SemanticPrioritizedFields(
                        title_field=SemanticField(field_name="title"),
                        content_fields=[SemanticField(field_name="content")],
                    ),
                )
            ]
        ),
    )


def ensure_index(index_client: SearchIndexClient, name: str, recreate: bool) -> None:
    exists = True
    try:
        index_client.get_index(name)
    except ResourceNotFoundError:
        exists = False

    if exists and recreate:
        print(f"Deleting index '{name}' (--recreate-index)")
        index_client.delete_index(name)
        exists = False

    if not exists:
        print(f"Creating index '{name}'")
        index_client.create_index(build_index_schema(name))
    else:
        print(f"Index '{name}' exists, upserting in place")


# ---------------------------------------------------------------------------
# Embedding and upload
# ---------------------------------------------------------------------------


def embed_chunks(
    openai_client: AzureOpenAI, deployment: str, chunks: list[Chunk]
) -> list[list[float]]:
    vectors: list[list[float]] = []
    for start in range(0, len(chunks), EMBED_BATCH_SIZE):
        batch = chunks[start : start + EMBED_BATCH_SIZE]
        response = openai_client.embeddings.create(
            model=deployment,
            input=[f"{c.title}\n\n{c.content}" for c in batch],
        )
        vectors.extend(item.embedding for item in response.data)
        print(f"Embedded {min(start + EMBED_BATCH_SIZE, len(chunks))}/{len(chunks)} chunks")
    return vectors


def upload(search_client: SearchClient, chunks: list[Chunk], vectors: list[list[float]]) -> None:
    documents = [
        {
            "id": chunk.doc_id,
            "title": chunk.title,
            "source": chunk.source,
            "content": chunk.content,
            "contentVector": vector,
        }
        for chunk, vector in zip(chunks, vectors)
    ]
    results = search_client.merge_or_upload_documents(documents)
    failed = [r for r in results if not r.succeeded]
    if failed:
        raise RuntimeError(f"{len(failed)} of {len(documents)} uploads failed: {failed[0].error_message}")
    print(f"Uploaded {len(documents)} chunks")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        sys.exit(f"Missing environment variable {name}. Populate from 'terraform output' (see README).")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest sample docs into Azure AI Search.")
    parser.add_argument(
        "--docs-dir",
        type=Path,
        default=Path(__file__).parent.parent / "sample_docs",
        help="Directory of markdown files to ingest.",
    )
    parser.add_argument(
        "--recreate-index",
        action="store_true",
        help="Drop and rebuild the index. Required after schema changes, otherwise upserts in place.",
    )
    args = parser.parse_args()

    openai_endpoint = require_env("AZURE_OPENAI_ENDPOINT")
    embedding_deployment = require_env("AZURE_OPENAI_EMBEDDING_DEPLOYMENT")
    search_endpoint = require_env("AZURE_SEARCH_ENDPOINT")
    index_name = require_env("AZURE_SEARCH_INDEX")

    paths = sorted(args.docs_dir.glob("*.md"))
    if not paths:
        sys.exit(f"No markdown files found in {args.docs_dir}")

    chunks: list[Chunk] = []
    for path in paths:
        doc_chunks = chunk_markdown(path)
        print(f"{path.name}: {len(doc_chunks)} chunks")
        chunks.extend(doc_chunks)

    credential = DefaultAzureCredential()
    openai_client = AzureOpenAI(
        azure_endpoint=openai_endpoint,
        azure_ad_token_provider=get_bearer_token_provider(credential, COGNITIVE_SERVICES_SCOPE),
        api_version="2024-10-21",
    )
    index_client = SearchIndexClient(endpoint=search_endpoint, credential=credential)
    search_client = SearchClient(endpoint=search_endpoint, index_name=index_name, credential=credential)

    ensure_index(index_client, index_name, recreate=args.recreate_index)
    vectors = embed_chunks(openai_client, embedding_deployment, chunks)
    upload(search_client, chunks, vectors)
    print("Done. Open the app URL from 'terraform output app_url' and ask a question.")


if __name__ == "__main__":
    main()
