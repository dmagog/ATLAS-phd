"""Prompt templates for Q&A answer generation."""

ANSWER_SYSTEM_PROMPT = """You are ATLAS, an academic study assistant for PhD exam preparation.
Answer the user's question using ONLY the provided context excerpts.
Rules:
1. Base every claim on the provided excerpts. Do not add external knowledge.
2. **MANDATORY citations**: every factual sentence MUST end with at least one
   inline citation marker in the EXACT format `[Doc: <title>, p.<page>]` or
   `[Doc: <title>, §<section>]`. The string `[Doc:` is required. An answer
   without citation markers is REJECTED — do not omit them under any
   circumstance.
3. If the context is insufficient to answer, say so clearly — do not fabricate.
4. Use markdown formatting. For mathematical formulas, use LaTeX ($$...$$).
5. Be precise and academically rigorous.
6. Respond in the same language as the user's question (Russian or English)."""


_MAX_HISTORY_TURNS = 5  # last N user+assistant pairs injected into the prompt


def build_answer_prompt(
    question: str,
    chunks: list[dict],
    response_profile: str = "detailed",
    conversation_history: list[dict] | None = None,
) -> list[dict]:
    """
    Build the messages list for the answer node.
    chunks: list of {"title": str, "section": str|None, "page": int|None, "text": str}
    conversation_history: list of {"role": "user"|"assistant", "content": str} (session memory)
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

    messages: list[dict] = [
        {"role": "system", "content": ANSWER_SYSTEM_PROMPT + f"\n\nResponse style: {profile_instruction}"},
    ]

    # Inject the tail of the session history so the model can resolve follow-up questions
    if conversation_history:
        max_msgs = _MAX_HISTORY_TURNS * 2  # each turn = 1 user + 1 assistant message
        messages.extend(conversation_history[-max_msgs:])

    # Citation reminder placed at the very end of the user message — long
    # context windows tend to push earlier instructions out of attention,
    # and Llama-class models in particular need the rule reiterated near
    # the question itself (observed in M3.B switch from free → paid Llama
    # 3.3 70B: prompts at 1.5K+ tokens dropped citations without this).
    citation_reminder = (
        "\n\nReminder: every factual sentence in your answer must end with at "
        "least one `[Doc: <title>, p.<page>]` (or `[Doc: <title>, §<section>]`) "
        "citation marker. Use the exact strings `[Doc:` and the document titles "
        "exactly as they appear in the excerpts above."
    )
    messages.append(
        {
            "role": "user",
            "content": (
                f"Context excerpts:\n\n{context_block}\n\n---\n\n"
                f"Question: {question}{citation_reminder}"
            ),
        }
    )
    return messages
