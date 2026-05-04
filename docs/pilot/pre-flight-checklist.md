# Pilot pre-flight checklist

Контрольный список **до** приглашения первого аспиранта. Без всех галочек — пилот не запускаем.

## Infrastructure

- [ ] **VPS поднят** — Hetzner CX22 или эквивалент (2 vCPU, 4 ГБ RAM, ≥40 ГБ SSD). См. `docs/deployment/hetzner-setup.md`.
- [ ] **Domain + HTTPS** — `atlas.<domain>` с Let's Encrypt сертификатом (валиден ≥30 дней).
- [ ] **Docker stack запущен** — `docker compose up -d` отдаёт `/health` 200 OK.
- [ ] **Все миграции применены** — `alembic upgrade head` дошёл до `0008_m45_program_schema` (или новее).
- [ ] **Backup-cron активен** — `scripts/pg_backup.sh` в crontab, тестовый restore прошёл.
- [ ] **Sentry / structured logging** — приложение пишет в JSON, ошибки видны в Sentry (или эквивалент).
- [ ] **Resource monitoring** — `htop` / Hetzner dashboard показывает CPU < 60% в idle, RAM с запасом ≥1 ГБ.

## Tenant content

- [ ] **Tenant создан** — `slug=optics-kafedra` (или ваш direction); `display_name` соответствует кафедре.
- [ ] **Программа загружена** — `POST /tenants/{slug}/program`, frontmatter подписан (`ratified_at`).
- [ ] **Корпус загружен** — все материалы прошли ingestion, status='active'.
- [ ] **Coverage report зелёный** — каждый билет имеет ≥ K_self_check chunks (default 5). Жёлтые/красные топики разобраны: либо добавлен материал, либо acknowledged как known gap (записано в pilot timeline).
- [ ] **Quality-score проверен** для всех материалов — нет low_quality (или явно акцептированы как «OCR с шумом, но это лучшее, что есть»).
- [ ] **Программа версионирована в git** — `corpus/<slug>/program.md`, `sources.md` (если ведётся).

## Roles & access

- [ ] **Super-admin** — единственный, никаких лишних аккаунтов с этой ролью.
- [ ] **Tenant-admin** — назначен (методист кафедры), знает свой логин, прошёл onboarding по `docs/welcome/tenant-admin.md`.
- [ ] **Supervisor** — назначен (научрук), прошёл `docs/welcome/supervisor.md`. Подтвердил, что понимает privacy posture.
- [ ] **Invite-codes для аспирантов** — выпущены, у каждого свой одноразовый код. **НЕ** в общем чате — лично каждому.

## Governance

- [ ] **DPIA-lite подписан** ответственным с кафедры — `docs/governance.md` обновлён датой подписи и ФИО.
- [ ] **Welcome guides раздаются** — каждый аспирант получает `docs/welcome/student.md` (русский) при регистрации.
- [ ] **Privacy posture акцептирован** научруком — он знает, что не видит non-opted-in профили (но видит agg).
- [ ] **Аудит-канал настроен** — tenant-admin регулярно (раз в неделю) смотрит audit_log на `privacy.violation_attempt`.

## Communication

- [ ] **Telegram/email-канал пилотной группы** создан (для оперативной связи: «у меня не работает self-check»).
- [ ] **Расписание weekly check-in** согласовано — день недели + время на 8 недель вперёд.
- [ ] **Контакты эскалации** — кто отвечает на incident'ы; кто отвечает за governance вопросы.

## Test data cleanup

- [ ] **Тестовые тенанты удалены** — `slug LIKE 'test-%'` или `audit-test-%` из `tests/test_m4d_*` не должны быть в production БД.
- [ ] **Тестовые users удалены** — `email LIKE '%@example.com'` не должны remain.
- [ ] **Тестовые программы удалены** — нет `version='v0.test'` или подобных.

## Запуск

Когда все галочки — переходим к `docs/pilot/timeline.md` неделя 0.
