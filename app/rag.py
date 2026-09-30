"""Retrieval-augmented generation engine.

The pipeline for each question:

  1. Embed the user's question with Azure OpenAI (text-embedding-3-large).
  2. Run a hybrid query against Azure AI Search: the vector and the raw
     keywords in one request, fused with Reciprocal Rank Fusion, then
     reordered by the semantic ranker.
  3. Build a grounded prompt from the top chunks and ask gpt-4o to answer
     using only that context.
  4. Return the answer plus the source chunks so the UI can cite them.

Both clients authenticate with DefaultAzureCredential. No keys exist
anywhere in this process.
"""

from __future__ import annotations

from dataclasses import dataclass

from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery
from openai import AzureOpenAI

from app.config import Settings

COGNITIVE_SERVICES_SCOPE = "https://cognitiveservices.azure.com/.default"

SYSTEM_PROMPT = """\
You are the Northwind Robotics knowledge assistant. Answer questions using
ONLY the sources provided below. Rules:

- If the sources do not contain the answer, say so plainly. Never invent
  policies, numbers, names, or procedures.
- Cite sources inline as [1], [2] matching the numbered sources.
- Be concise: a short direct answer first, then supporting detail.
- If the question is ambiguous, answer the most likely reading and note
  the assumption.
"""

MAX_HISTORY_TURNS = 6
TOP_K = 4


@dataclass(frozen=True)
class SourceChunk:
    """One retrieved chunk, returned to the UI as a citation."""

    title: str
    source: str
    content: str
    score: float

    def as_dict(self) -> dict[str, object]:
        return {
            "title": self.title,
            "source": self.source,
            "content": self.content,
            "score": round(self.score, 4),
        }


@dataclass(frozen=True)
class RagAnswer:
    answer: str
    sources: list[SourceChunk]


class RagEngine:
    """Owns the OpenAI and Search clients for the process lifetime."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        credential = DefaultAzureCredential()

        # The openai package accepts a callable token provider, so Entra ID
        # tokens are fetched and refreshed automatically. No api_key anywhere.
        self._openai = AzureOpenAI(
            azure_endpoint=settings.openai_endpoint,
            azure_ad_token_provider=get_bearer_token_provider(
                credential, COGNITIVE_SERVICES_SCOPE
            ),
            api_version=settings.api_version,
        )

        self._search = SearchClient(
            endpoint=settings.search_endpoint,
            index_name=settings.search_index,
            credential=credential,
        )

    # -- retrieval ---------------------------------------------------------

    def _embed(self, text: str) -> list[float]:
        response = self._openai.embeddings.create(
            model=self._settings.embedding_deployment,
            input=text,
        )
        return response.data[0].embedding

    def retrieve(self, query: str, top_k: int = TOP_K) -> list[SourceChunk]:
        """Hybrid retrieval: vector similarity + BM25 keywords in one call,
        re-ranked by the semantic ranker for better ordering on natural
        language questions."""
        vector_query = VectorizedQuery(
            vector=self._embed(query),
            k_nearest_neighbors=top_k * 2,
            fields="contentVector",
        )
        results = self._search.search(
            search_text=query,
            vector_queries=[vector_query],
            query_type="semantic",
            semantic_configuration_name="default",
            select=["title", "source", "content"],
            top=top_k,
        )
        return [
            SourceChunk(
                title=doc["title"],
                source=doc["source"],
                content=doc["content"],
                score=doc["@search.score"],
            )
            for doc in results
        ]

    # -- generation --------------------------------------------------------

    @staticmethod
    def _build_messages(
        question: str,
        sources: list[SourceChunk],
        history: list[dict[str, str]],
    ) -> list[dict[str, str]]:
        numbered = "\n\n".join(
            f"[{i}] {chunk.title} ({chunk.source})\n{chunk.content}"
            for i, chunk in enumerate(sources, start=1)
        )
        grounded_question = (
            f"Sources:\n\n{numbered}\n\nQuestion: {question}"
            if sources
            else f"No sources were retrieved.\n\nQuestion: {question}"
        )
        messages: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
        # Keep a short window of prior turns for follow-up questions,
        # without the earlier turns' source dumps (they were answered already).
        for turn in history[-MAX_HISTORY_TURNS:]:
            if turn.get("role") in ("user", "assistant") and turn.get("content"):
                messages.append({"role": turn["role"], "content": turn["content"]})
        messages.append({"role": "user", "content": grounded_question})
        return messages

    def answer(self, question: str, history: list[dict[str, str]]) -> RagAnswer:
        sources = self.retrieve(question)
        response = self._openai.chat.completions.create(
            model=self._settings.chat_deployment,
            messages=self._build_messages(question, sources, history),
            temperature=0.2,
            max_tokens=800,
        )
        content = response.choices[0].message.content or ""
        return RagAnswer(answer=content.strip(), sources=sources)
