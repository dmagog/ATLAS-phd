# Pilot timeline (8 недель)

Стандартный календарь пилотного запуска. Каждую неделю — фиксированный check-in, конкретные ожидаемые результаты, явные триггеры для эскалации.

Конкретные даты заполняются перед стартом (см. `pre-flight-checklist.md`).

---

## Week 0 — Soft launch

**До этой недели:** pre-flight checklist полностью зелёный.

**Цели:**
- Tenant-admin и научрук залогинены, прошли onboarding по welcome-guide.
- Tenant-admin сделал тестовый Q&A и self-check сам (без аспирантов) — проверил что система отвечает по корпусу.
- 1-2 аспиранта-«пилотных» приглашены, прошли регистрацию, сделали по 1 attempt.

**Check-in (конец недели):**
- Все ли инвайты redeemed?
- Есть ли technical issues (LLM timeout, retrieval пустой, audit-log не пишется)?
- Welcome-guide понятен или есть пробелы?

**Tригггер эскалации:** stack нестабилен (downtime > 1 час суммарно за неделю) → пауза, дебаг, перенос недели 1.

---

## Week 1 — Onboarding wave

**Цели:**
- Все остальные аспиранты приглашены и зарегистрированы.
- Каждый сделал ≥ 2 self-check attempts (по разным билетам).
- Аспиранты прошли по welcome-guide, понимают privacy и opt-in.

**Метрики на конец недели:**
- N_students_active: ожидаем ≥ 5 (для unlock heatmap; см. BDD 5.6).
- N_attempts_completed: ожидаем ≥ 10.
- Heatmap всё ещё `is_below_threshold: true` (это нормально — нужно больше данных).

**Check-in:**
- Какие билеты привлекают первые attempts? (signal о том, что аспиранты выбирают «на интуиции» — может, лучше дать им расписание).
- Какой % refusals на Q&A? Если > 50% — корпус недопокрыт или формулировки вопросов неудобны.
- Какие технические проблемы аспиранты репортят в чат?

**Триггер эскалации:** > 30% аспирантов не залогинились → проблема onboarding flow, разбираем.

---

## Week 2 — First heatmap signal

**Цели:**
- N_attempts_completed ≥ 30 → heatmap показывает реальные данные (BDD 5.6 unlock).
- Научрук смотрит heatmap впервые, делает первое drilldown.
- Появляется первый сигнал «топик X провален у большинства» → это вход в семинар.

**Check-in:**
- Что говорит heatmap? Какой fail_rate выше всего?
- Соответствует ли это ожиданиям научрука?
- Drilldown по проблемному топику: какие error_tags доминируют?

**Действие:** научрук обсуждает на семинаре проблемный топик. (Это важная веха — система **уже** даёт пользу до конца пилота).

**Триггер эскалации:** heatmap показывает unrealistic данные (всё 100% fail или 0% fail) → bug в evaluator или calibration ошибка.

---

## Week 3 — Mid-pilot survey #1

**Цели:**
- Каждый аспирант сделал ≥ 5 attempts (≈ 1 в день).
- 1-2 аспиранта попробовали opt-in для индивидуального профиля.

**Check-in: mid-pilot survey** (короткий опросник):
- Что работает хорошо?
- Что фрустрирует?
- Чего не хватает?
- Готовы ли продолжать использовать после пилота?

Анонимный, через Google Form / Typeform. Результаты обсуждаются в weekly check-in.

**Триггер эскалации:** ≥ 30% аспирантов в опросе скажут «не использую регулярно» → проблема вовлечённости, разбираем.

---

## Week 4 — Mid-pilot review

**Цели:**
- Всё ещё работает.
- Heatmap зрелый (≥ 50 attempts, ≥ 5 распределённых студентов).
- Научрук провёл 1-2 семинара, направленных по heatmap-сигналам.

**Check-in: 30-min retro:**
- Что мы узнали?
- Какие критические improvements на оставшиеся 4 недели?
- Какие технические дебты надо закрыть до конца пилота (M3.A.E self-check, false-refusals fixes, paid LLM)?

**Документация:** запись retro в `docs/pilot/notes/week-4-retro.md`.

---

## Week 5-7 — Steady state

Цели — поддержание ритма + сбор данных:
- Аспиранты делают ≥ 1 attempt в неделю в среднем.
- Научрук открывает heatmap ≥ 2 раз в неделю.
- Audit-log регулярно проверяется на privacy.violation_attempt.

Никаких big changes в эти недели — вы хотите чтобы аспиранты привыкли и дали стабильный сигнал.

---

## Week 8 — End-of-pilot

**Цели:**
- Final survey (то же что mid-pilot + «продолжаем?»).
- Финальный snapshot всех метрик.
- End-of-pilot report (см. `end-of-pilot-report-template.md`).

**Артефакты на конец пилота:**
- `docs/pilot/notes/end-of-pilot-report.md` — финальный документ.
- Снимки heatmap, drilldown, students list (CSV из `audit_log`).
- Ответы на survey'и (анонимизированные).
- Решение: продолжаем / меняем / закрываем.

---

## Cross-cutting: weekly check-in template

Каждую неделю в один и тот же день (например, четверг 18:00) — 30-минутная встреча:
- Tenant-admin (методист), научрук, разработчик.
- Шаблон протокола: `docs/pilot/weekly-checkin-template.md`.
- Заметки складываются в `docs/pilot/notes/week-N.md`.

## Cross-cutting: incident response

При любом из:
- Privacy violation (`audit_log` показал `privacy.violation_attempt` × N или confirmed leak)
- Production incident (downtime > 1 час, data corruption)
- Согласие аспиранта внезапно отозвано

→ см. `docs/pilot/incident-runbook.md`.
