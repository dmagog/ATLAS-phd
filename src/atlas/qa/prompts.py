"""Prompt templates for Q&A answer generation."""

ANSWER_SYSTEM_PROMPT = """You are ATLAS, an academic study assistant for PhD exam preparation.
Answer the user's question using ONLY the provided context excerpts.
Rules:
1. Base every claim on the provided excerpts. Do not add external knowledge.
2. Cite each source inline using [Doc: <title>, p.<page>] or [Doc: <title>, §<section>].
3. If the context is insufficient to answer, say so clearly — do not fabricate.
4. Use markdown formatting. For mathematical formulas, use LaTeX ($$...$$).
5. Be precise and academically rigorous.
6. Respond in the same language as the user's question (Russian or English)."""


def build_answer_prompt(question: str, chunks: list[dict], response_profile: str = "detailed") -> list[dict]:
    """
    Build the messages list for the answer node.
    chunks: list of {"title": str, "section": str|None, "page": int|None, "text": str}
    """
    profile_instruction = {
        "brief": "Be concise — 2-4 sentences maximum.",
        "detailed": "Provide a thorough explanation with examples if present in the context.",
        "study": "Explain as if teaching — break down concepts step by step, highlight key terms.",
    }.get(response_profile, "Provide a thorough explanation.")

    context_parts = []
    for i, chunk in enumerate(chunks, 1):
        loc = f"p.{chunk['page']}" if chunk.get("page") else (f"§{chunk['section']}" if chunk.get("section") else "")
        header = f"[{i}] {chunk['title']}" + (f" — {loc}" if loc else "")
        context_parts.append(f"{header}\n{chunk['text']}")

    context_block = "\n\n---\n\n".join(context_parts)

    return [
        {"role": "system", "content": ANSWER_SYSTEM_PROMPT + f"\n\nResponse style: {profile_instruction}"},
        {"role": "user", "content": f"Context excerpts:\n\n{context_block}\n\n---\n\nQuestion: {question}"},
    ]
