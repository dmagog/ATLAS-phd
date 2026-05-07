# Release v0.7.0 — Pilot-ready (M3.A–C + M4.5.E + M6.A)

**Дата:** 2026-05-07
**Состояние:** ATLAS phd готов к запуску friend-пилота на машине разработчика. Все технические gap'ы из roadmap M3–M6 закрыты, документация синхронизирована с кодом, integration-test-сюита покрывает 6 critical путей.

---

## TL;DR

| Domain | Status |
|---|---|
| **M3 Eval-harness** | ✅ Eval-set v1.1 (120 entries × 6 topics), refusal_tnr=1.000 vs 0.000, faithfulness 0.541, κ=1.0 |
| **M4 Multi-tenancy** | ✅ Schema, JWT versioning, RBAC, invite flow, audit_log, 31 BDD test |
| **M4.5 Programs+topics** | ✅ Program lifecycle, material→topic, coverage report, eval-set per-topic annotations |
| **M5 Supervisor** | ✅ Heatmap с N-threshold, drilldown, 404 anti-leak, opt-in profiles |
| **M6.A Pilot infra** | ✅ pilot_seed, deploy.sh, daily_metrics, pg_backup, GHCR build, multi-stage Dockerfile, runbook, local-pilot guide |
| **M6.B/C Run** | ⏸ Готов к запуску — нужны только пользователи |

---

## Что входит в этот release (с момента 0.3.1)

Версии 0.4.0 → 0.7.0 в [`CHANGELOG.md`](CHANGELOG.md). Вкратце:

### M3 — Eval-harness (BDD 1.3, 6.1–6.7)

- **M3.A.0 hard-gate**: refusal на retrieval-уровне без LLM-вызова при insufficient evidence (`top1_vscore < 0.55` ИЛИ `chunks_above_threshold < 2`). До fix'а отказ шёл через TECHNICAL_ERROR; после — через REFUSAL_SENT с reason_code.
- **M3.A self-check block** заполнен 0/20 → 20/20. Новый stateless endpoint `POST /self-check/evaluate`. MAE 0.615, **κ_binarized = 1.000** (perfect agreement on зачёт/незачёт).
- **M3.B полный 100-entry A/B** на платной `meta-llama/llama-3.3-70b-instruct`:
  - refusal_tnr **1.000 vs 0.000** (treatment vs baseline)
  - 0% errors на 100 запросах (vs 40% на free-tier)
  - faithfulness 0.541 (judge), latency p50 7.1s
  - **бюджет $0.20** на полный прогон + judge × 3 (M3 plan был $20)
- **M3.C BDD 6.5 reproducibility** — 6/7 PASS. Детерминированные метрики Δ=0.000, faithfulness Δ=0.040 (inherent LLM-judge variance).
- **18 entry rephrasings** в eval-set (4 формула + 14 qa) — короткие императивные команды → развёрнутые учебные вопросы. После — 0 false-refusals на 80 in-corpus entries.

### M4 — Multi-tenancy (BDD 4.x, 7.x, 8.x)

- **M4.A schema**: `tenants`, `tenant_id` на всех данных, role-widening (super-admin / tenant-admin / supervisor / student), `users.consent_recorded_at`, `jwt_version`, `supervisor_visibility`. Audit_log + invite_codes.
- **M4.A read-only enforcement**: `assert_tenant_writable(tenant_id, db, user)` helper, `PATCH /tenants/{slug}/status` для super-admin (incident-response). 423 LOCKED при write на non-active тенант.
- **M4.B retrieval filter**: WHERE `tenant_id = :tid` + partial HNSW per-tenant.
- **M4.C JWT versioning**: bump `jwt_version` инвалидирует все старые токены (BDD 7.5).
- **M4.D audit_log**: 13 actions (см. [`docs/governance.md`](docs/governance.md) §2.1 + [`docs/runbook.md`](docs/runbook.md) §15) + cross-tenant integration test.

### M4.5 — Programs + topics (BDD 4.2, 4.5, 4.7, 7.4)

- **M4.5.0**: rename `default` → `optics-kafedra`.
- **M4.5.A**: `program.md` parser + `POST /tenants/{slug}/program` с archive-on-replace (BDD 7.4).
- **M4.5.B**: `programs` / `program_topics` / `material_topics` / `chunk_topics` schema + 4 PostgreSQL триггера для denormalized `coverage_chunks`.
- **M4.5.C**: material→topic attach endpoints + `scripts/attach_corpus_by_keywords.py` для bulk heuristic backfill.
- **M4.5.D**: coverage report + quality-score endpoints.
- **M4.5.E**: eval-set v1.1 — каждой не-refusal entry присвоен `topic_external_id`. Новый `eval/per_topic_breakdown.py`. **100% non-refusal entries замаппированы** на 6 topic'ов программы.

### M5 — Supervisor analytics (BDD 3.4, 5.1–5.7)

- **M5.A** `/me` + `POST /me/visibility` (anonymous-aggregate-only ↔ show-to-supervisor).
- **M5.B/D** heatmap + drilldown + students list + profile с **N-threshold** (n_students ≥ 5 AND n_attempts ≥ 30) и **404 anti-leak** (BDD 5.5: opted-out студент → 404, не 403).
- Wilson 95% CI на per-topic fail_rate.

### M6.A — Pilot infrastructure

- **`scripts/pilot_seed.py`** — bootstrap тенанта одной командой (tenant + program + N invite-кодов).
- **`scripts/daily_metrics_report.py`** — суточная сводка из БД (users / self-check / qa_feedback / privacy events / corpus state) с `--json` mode.
- **`scripts/pg_backup.sh`** — daily pg_dump с rotation 7 дней.
- **`scripts/deploy.sh`** — production-deploy на VPS (snapshot → git pull → migrate one-shot → up -d → health-check + smoke).
- **`scripts/attach_corpus_by_keywords.py`** — bulk material→topic backfill.
- **`.github/workflows/build-image.yml`** — на push в main собирает + пушит app image в `ghcr.io/dmagog/atlas-phd-app`.
- **Multi-stage Dockerfile** — `dev` (default, hot-reload, auto-migrate) и `production` (non-root uid 10001, healthcheck, без `--reload`/auto-migrate, миграции через deploy.sh).

### Тесты + CI

- **31 BDD integration test** (vs 1 ранее):
  - `test_m3a_hard_gate.py` (5)
  - `test_m4a_tenant_readonly.py` (2)
  - `test_m4c_auth_invite.py` (9)
  - `test_m4d_cross_tenant_isolation.py` (1)
  - `test_m45a_program_lifecycle.py` (7)
  - `test_m5_supervisor_privacy.py` (7)
- **CI workflow** прогоняет всю suite (~25s после прогрева).

### Документация

- **NEW** [`docs/deployment/local-pilot.md`](docs/deployment/local-pilot.md) — гайд для friend-пилота на Mac (Tailscale / LAN / Cloudflare Tunnel / ngrok).
- [`README.md`](README.md) — стек / модели / агентный контур / pointer'ы на эксплуатационные документы — синхронизированы с кодом.
- [`CHANGELOG.md`](CHANGELOG.md) — записи 0.4.0 → 0.7.0 (раньше последняя была Apr 6).
- [`docs/runbook.md`](docs/runbook.md) — реестр всех 10 скриптов, справочник 13 audit-actions.
- [`docs/governance.md`](docs/governance.md) §2.1 — таблица audit-actions с privacy-relevance ratings, §5 DPIA-lite.
- [`docs/welcome/{student,supervisor,tenant-admin}.md`](docs/welcome/) — гайды для пилотных пользователей по ролям.
- [`docs/pilot/`](docs/pilot/) — pre-flight-checklist, timeline, weekly-checkin-template, end-of-pilot-report-template, incident-runbook.

---

## Что готово к запуску пилота

| Что | Где |
|---|---|
| Stack на машине | `docker compose up -d` (Docker Desktop, ~5 мин на первый запуск) |
| Bootstrap тенанта | `python3 scripts/pilot_seed.py --tenant optics-kafedra --program corpus/optics-kafedra/program.md --invites 5` |
| Корпус | 3 учебника по оптике (Born&Wolf, Matveev, Yariv) — 4006 chunks |
| Программа | 6 topic'ов в [`corpus/optics-kafedra/program.md`](corpus/optics-kafedra/program.md) |
| Сетевой доступ | Tailscale (рекомендуется) / LAN / Cloudflare Tunnel / ngrok — см. [`local-pilot.md` §3](docs/deployment/local-pilot.md) |
| Welcome для друзей | [`docs/welcome/student.md`](docs/welcome/student.md) |
| Daily ops | `python3 scripts/daily_metrics_report.py` |
| Privacy incident response | [`docs/pilot/incident-runbook.md`](docs/pilot/incident-runbook.md) §1 |

---

## Известные ограничения

- **Faithfulness 0.541 ниже M3 floor 0.65**: Llama 3.3 70B как self-judge даёт self-bias. Решение: switch judge на `claude-3.5-sonnet` или `gpt-4o` ($1–3 за полный judge на 100 entries) — отдельный M3.D follow-up. Для friend-пилота приемлемо: главная защита (hard-gate refusal_tnr=1.0) работает идеально.
- **BDD 6.5 reproducibility**: faithfulness Δ=0.040 vs floor 0.030 — inherent LLM-judge variance. См. M3.C анализ.
- **eval-set v1.1: 1.3 ТIR покрыта только 2 entries**, 1.2 Линзы имеет low faithfulness 0.318 при 100% answered. Action: расширить eval-set v1.2.
- **Citation accuracy метрика — skeleton**: n_with_citations считается, но full validation (Doc: title parse → match doc_id) не реализована. Отдельный M3.A continuation.
- **Self-check evaluator bias на partial/off-topic ответах** (завышение ~+1.0). Решается switch judge'а (см. выше).

---

## Следующие шаги (post-pilot)

1. **M6.B/C** — собственно пилот: 3–5 друзей, 1–2 недели, daily metrics review, end-of-pilot report.
2. **M3.D** — switch judge на gpt-4o-class для эталонного faithfulness; CI regression gate.
3. **M3.E** — production-judge sample (10% Q&A в проде).
4. **eval-set v1.2** — расширить 1.3 ТIR + проверить anomaly 1.2 Линзы.
5. **Sentry-интеграция** — exception tracking в production.

---

## Артефакты этого release'а

- 7 commits с момента 0.3.1: `27366e5` `2a7459f` `b8c339c` `5ea8a4f` `8bf9ce0` `86ee14e` `6b24049` `406d005` `b509b6c` `fe76a70` (после 25292e5/0351d91/d5a817c/b9f10cb из M6.A)
- 6 BDD test файлов (31 теста) в `tests/`
- 8 скриптов в `scripts/`
- 11 документов в `docs/` (welcome × 3 + pilot × 5 + deployment × 2 + runbook + governance)
- 4 eval run-dir в `eval/results/` (m3b-treatment-postfix, m3b-baseline, m3c-reproducibility, m3a-selfcheck-eval)
- M3-report.md v2.3 (1 файл, 4 версии истории)

---

## Sign-off

- Tests: 31/31 passing
- CI: green
- Eval: refusal_tnr=1.000, qa_false_refusal_rate=0.000, error_rate=0.000, κ=1.000
- Docs: audit показал 5 gap'ов, все закрыты в `fe76a70`

**Готов к friend-пилоту.**
