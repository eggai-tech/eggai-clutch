"""
RAG Offline Pipeline Example - Typed API
Processing documents for a RAG system. Only the summarization step needs AI.
5 nodes, 1 LLM call.
"""

import asyncio
import hashlib

from pydantic import BaseModel

from eggai_clutch import Clutch, Terminate


async def mock_llm(prompt: str) -> str:
    return "[AI Summary] This document discusses key topics including data processing."


async def mock_embedding(chunks: list[str]) -> list[list[float]]:
    return [[0.1, 0.2, 0.3] for _ in chunks]


class Document(BaseModel):
    path: str
    content: str = ""
    doc_id: str = ""
    chunks: list[str] = []
    embeddings: list[list[float]] = []
    summary: str = ""


class MockVectorDB:
    storage = {}

    @classmethod
    async def upsert(cls, doc: Document):
        cls.storage[doc.doc_id] = doc
        print(f"    [VectorDB] Stored {doc.doc_id}")


clutch = Clutch("rag-indexer")


@clutch.agent()
async def loader(doc: Document) -> Document:
    """Load document. Pure code."""
    doc.content = f"[CONTENT OF {doc.path}] Lorem ipsum dolor sit amet. " * 10
    doc.doc_id = hashlib.md5(doc.path.encode()).hexdigest()[:8]
    print(f"    [Loader] Loaded {len(doc.content)} chars")
    return doc


@clutch.agent()
async def chunker(doc: Document) -> Document:
    """Split into chunks. Pure code."""
    chunk_size = 200
    doc.chunks = [doc.content[i : i + chunk_size] for i in range(0, len(doc.content), chunk_size)]
    print(f"    [Chunker] Created {len(doc.chunks)} chunks")
    return doc


@clutch.agent()
async def embedder(doc: Document) -> Document:
    """Generate embeddings. Code calling embedding API."""
    doc.embeddings = await mock_embedding(doc.chunks)
    print(f"    [Embedder] Generated {len(doc.embeddings)} embeddings")
    return doc


@clutch.agent()
async def summarizer(doc: Document) -> Document:
    """Generate summary. LLM call."""
    doc.summary = await mock_llm(f"Summarize:\n\n{doc.content[:1000]}")
    print("    [Summarizer] Generated summary")
    return doc


@clutch.agent()
async def indexer(doc: Document) -> Document:
    """Store in vector DB. Pure code."""
    await MockVectorDB.upsert(doc)
    raise Terminate(doc)


async def main():
    print("=" * 60)
    print("RAG PIPELINE EXAMPLE (TYPED)")
    print("=" * 60)

    result = await clutch.run(Document(path="/docs/quarterly-report.pdf"))

    print("\n" + "-" * 60)
    print("Pipeline completed!")
    print(f"  Document ID: {result['doc_id']}")
    print(f"  Chunks: {len(result['chunks'])}")
    print(f"  Summary: {result['summary'][:50]}...")
    print("-" * 60)


if __name__ == "__main__":
    asyncio.run(main())
