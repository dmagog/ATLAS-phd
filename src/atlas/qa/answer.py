"""Answer node: generates a grounded answer from retrieved chunks."""
from dataclasses import dataclass, field
from atlas.llm.client import llm_client
from atlas.qa.prompts import build_answer_prompt
from atlas.retriever.retriever import ChunkCandidate
from atlas.core.config import settings
from atlas.core.logging import logger


@dataclass
class Citation:
    document_title: str
    section: str | None
    page: int | None
    snippet: str


@dataclass
class AnswerDraft:
    answer_markdown: str
    citations: list[Citation]
    chunks_used: int


async def generate_answer(
    question: str,
    candidates: list[ChunkCandidate],
    response_profile: str = "detailed",
    request_id: str = "",
    conversation_history: list[dict] | None = None,
) -> AnswerDraft:
    top_chunks = candidates[: settings.retriever_max_chunks_in_prompt]

    chunk_dicts = [
        {
            "title": c.document_title,
            "section": c.section,
            "page": c.page,
            "text": c.text,
        }
        for c in top_chunks
    ]

    messages = build_answer_prompt(question, chunk_dicts, response_profile, conversation_history)

    answer_text = await llm_client.chat(
        messages=messages,
        temperature=0.2,
        max_tokens=2048,
        request_id=request_id,
    )

    citations = [
        Citation(
            document_title=c.document_title,
            section=c.section,
            page=c.page,
            snippet=c.text[:200],
        )
        for c in top_chunks
    ]

    logger.info("answer_drafted", chunks_used=len(top_chunks), request_id=request_id)
    return AnswerDraft(answer_markdown=answer_text, citations=citations, chunks_used=len(top_chunks))
