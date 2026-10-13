"""Формулировки «по теме программы» для retrieval: подсказки в чате
(GET /me/program) и поиск материалов для полного прогона самопроверки."""

_PROMPT_CONCEPTS = 4


def study_prompt(title: str, section: str, key_concepts: list[str]) -> str:
    """Вопрос «по теме» для чата.

    Формулировка выбрана замером retrieval на программе IPMA (28 тем):
    «Что важно знать по теме «T»: k1, k2, k3, k4» проходит hard-gate на
    28/28 и приводит к собственному разделу темы в источнике, тогда как
    «Расскажи о теме: T (раздел)» — 26/28 и чаще цепляет оглавление.
    Ключевые понятия с тем же началом, что у уже взятых, пропускаются —
    в программе бывают варианты одного слова для автопривязки материалов.
    С названием темы не сравниваем: «дифракционная решётка» в теме
    «Дифракция…» нужна retrieval'у (без неё тема оптики не проходит gate).
    """
    picked: list[str] = []
    seen: set[str] = set()
    for kc in key_concepts:
        head = kc.lower()[:5]
        if head in seen:
            continue
        seen.add(head)
        picked.append(kc)
        if len(picked) == _PROMPT_CONCEPTS:
            break
    if not picked:
        return f"Расскажи о теме: {title} ({section})"
    return f"Что важно знать по теме «{title}»: {', '.join(picked)}"
