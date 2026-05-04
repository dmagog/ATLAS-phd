# End-of-pilot report

**Tenant:** {slug}
**Pilot dates:** {start_date} — {end_date}
**Authors:** tenant-admin (методист), supervisor (научрук), developer

---

## 1. Краткое резюме (1 параграф)

{{Что было пилотом, что вышло, рекомендация: continue / iterate / sunset}}

---

## 2. Quantitative метрики

### 2.1 Активность

| Metric | Final value |
|---|---|
| Зарегистрировано аспирантов | |
| Активных (≥ 1 attempt за пилот) | |
| Средн. attempts на аспиранта | |
| Total attempts completed | |
| Total Q&A messages | |
| Q&A refusal rate | |

### 2.2 Качество (M3 metrics)

| Metric | Final value |
|---|---|
| Faithfulness (golden_set v1.0) | |
| Faithfulness (real prod sample) | |
| Citation accuracy | |
| Latency p50 / p95 | |

### 2.3 Coverage и quality-score

| Metric | Final value |
|---|---|
| Topics in green bucket | / total |
| Topics in red bucket | |
| Materials with low_quality flag | / total |

### 2.4 Privacy

| Event | Count over 8 weeks |
|---|---|
| user.visibility.toggle | |
| personal_data.access | |
| privacy.violation_attempt | |
| Confirmed leaks | (should be 0) |

---

## 3. Qualitative observations

### 3.1 Что хорошо

- (3-5 пунктов из weekly check-in retros)

### 3.2 Что не сработало

- (3-5 пунктов; для каждого — root cause если знаем)

### 3.3 Surveys

**Mid-pilot (week 4):** {N} respondents, {response_rate}% rate.
- Самые частые «работает»:
- Самые частые «фрустрирует»:

**End-of-pilot:** {N} respondents.
- «Продолжите ли использовать?» — Yes: ___% / No: ___% / Maybe: ___%
- Свободные комментарии: (в `notes/end-of-pilot-survey.md`)

---

## 4. Decisions framework

Каждое observation попадает в один из четырёх buckets:

### 4.1 Critical fix (must do до повторного запуска)

- [ ] {issue} — {owner} — {target}

### 4.2 UX backlog (важно, но не блокирующее)

- [ ] {issue} — {owner} — {target}

### 4.3 Зона роста (отложено в roadmap §5 / post-M6)

- {item}

### 4.4 Re-scope (нужен пересмотр подхода)

- {item}

---

## 5. Pilot success criteria

| Criterion | Target | Actual | Pass? |
|---|---|---|---|
| ≥ 80% активных за 8 недель | | | |
| ≥ 12 attempts на аспиранта | | | |
| Heatmap unlock (n ≥ 5 + ≥ 30 attempts) | | | |
| Privacy violations confirmed | 0 | | |
| Q&A faithfulness | ≥ 0.65 (M3 floor) | | |
| Supervisor использовал heatmap ≥ 4 раза | | | |
| End-of-pilot retention intent | ≥ 60% «yes» | | |

**Overall result:** PASS / PARTIAL / FAIL

---

## 6. Рекомендации

### 6.1 Что делать на следующем цикле (если PASS)

- (3-5 пунктов конкретных действий)

### 6.2 Что чинить до следующего пилота (если PARTIAL)

- (4.1 critical fixes раскрыты)

### 6.3 Что меняем фундаментально (если FAIL)

- (root cause + предложение, обычно требует roadmap-revision)

---

## 7. Артефакты

- `notes/week-N-*.md` × 8 — weekly check-in заметки
- `notes/end-of-pilot-survey.md` — анонимизированные ответы
- Snapshot БД (`pg_dump` на дату {end_date})
- audit_log dump для архива (CSV)
- heatmap snapshot (JSON) с финальными цифрами

---

**Sign-off:**
- Methodist (tenant-admin): ___________ дата: ___________
- Supervisor (научрук): ___________ дата: ___________
- Developer: ___________ дата: ___________
