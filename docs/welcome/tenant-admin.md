# Welcome — tenant-admin (методист кафедры)

Вы — оператор тенанта (кафедры). Загружаете программу кандэкзамена, привязываете материалы к билетам, приглашаете аспирантов и научруков, следите за качеством корпуса.

## Получение доступа

Super-admin платформы создаёт тенант (`POST /tenants`) и отправляет вам инвайт-ссылку. Регистрация стандартная (email/пароль/согласие), после — вы залогинены.

## Pre-flight (до приглашения первых аспирантов)

Чек-лист готовности тенанта к пилоту:

1. **Программа загружена** — `POST /tenants/{slug}/program` с текстом `program.md`. Шаблон: `corpus/optics-kafedra/program.md`.
2. **Материалы загружены** через старый M2 ingestion (`POST /admin/ingestion-jobs`). PDF / DOCX / TXT / MD / JSONL.
3. **Материалы привязаны к билетам** — для каждого material'а:
   ```
   POST /tenants/{slug}/materials/{material_id}/topics
   {"topic_external_ids": ["1.1", "2.1", "2.2"]}
   ```
   Триггер автоматически распространяет topic-теги на все chunks этого материала.
4. **Coverage report зелёный** — `GET /tenants/{slug}/coverage`. Цель: каждый билет в bucket `green` (≥ K_self_check chunks). Жёлтые/красные билеты — недопокрыты, добавьте материал или уточните привязки.
5. **Quality-score проверен** — для каждого material'а `POST /tenants/{slug}/materials/{material_id}/quality-score`. Если `low_quality: true` — посмотрите, что в материале (OCR-артефакты, неправильный язык, слишком короткие фрагменты).
6. **Программа подписана** ответственным — frontmatter `ratified_at: YYYY-MM-DD`. Это не техническое поле, но юридически важное (DPIA-lite).
7. **Welcome guides доступны** студентам и научрукам — раздайте `docs/welcome/student.md` и `docs/welcome/supervisor.md`.

## Day-to-day операции

### Загрузка нового материала

```
POST /admin/ingestion-jobs (multipart upload)
→ POST /tenants/{slug}/materials/{material_id}/topics  (привязка)
→ GET  /tenants/{slug}/coverage                         (проверка)
→ POST /tenants/{slug}/materials/{material_id}/quality-score
```

### Bulk-привязка материалов к topic'ам по ключевым словам (M4.5.C)

Если только что загружен большой корпус и привязывать каждый файл к
topic'ам вручную долго — есть heuristic-скрипт:

```bash
python3 scripts/attach_corpus_by_keywords.py --tenant optics-kafedra
```

Скрипт смотрит на key_concepts каждого topic'а в активной программе и
ищет их в text'е chunks материалов. Триггеры в БД пересчитают
`coverage_chunks`. После — проверь `GET /tenants/{slug}/coverage`.

### Per-topic анализ eval-набора (M4.5.E)

Если хочешь увидеть, как эталонный eval-set распределён по topic'ам твоей
программы (faithfulness/answered/refused per-topic), запусти:

```bash
python3 eval/per_topic_breakdown.py \
    --run eval/results/<latest-run-dir> \
    --set eval/golden_set_v1/golden_set_v1.0.jsonl
```

Это даёт раннее представление, какие topic'ы программы хорошо покрыты,
а какие — слабо (low faithfulness или мало entries в eval-set'е). Сигнал
к расширению корпуса или eval-set'а.

### Замена устаревшего материала

Текущий API не поддерживает «удалить материал» (это в зоне роста — `material.delete` action). Пока: загружаете новый, привязываете к тем же билетам, старый оставляете. Coverage-counter автоматически обновится; в retrieval работают оба, и это нормально для пилота.

### Обновление программы

Загружайте через `POST /tenants/{slug}/program`. Старая программа автоматически архивируется (BDD 7.4):
- старые попытки остаются привязанными к старым topic_id (FK RESTRICT)
- новые попытки используют новые topic_id
- supervisor heatmap всегда показывает топики **активной** программы

### Приглашения

```
POST /invites
{"role": "student"}
GET /invites
```

Один код — одна регистрация, после redeem'а инвалидируется (BDD 4.6). Срок жизни — 7 дней по умолчанию (можно override через `expires_in_days`).

### Просмотр audit log

Все важные действия логируются. Для своего тенанта:
```sql
SELECT * FROM audit_log
WHERE tenant_id = '<your-tenant-id>'
ORDER BY occurred_at DESC LIMIT 50;
```

Особо важные events:
- `personal_data.access` — научрук открывал профиль аспиранта (когда + кого)
- `privacy.violation_attempt` — кто-то попытался обойти privacy (нужен разбор!)
- `user.role.grant` / `user.visibility.toggle` — кто дал/убрал видимость

## Полномочия

Вы можете:
- управлять программой и материалами своего тенанта
- приглашать в свой тенант (любую роль кроме super-admin)
- видеть аналитику супервайзера для своего тенанта (heatmap, drilldown, students list)

Вы **не** можете:
- видеть профили аспирантов без их opt-in (даже tenant-admin под privacy-маской — это by design)
- управлять чужими тенантами
- создавать новые тенанты (это super-admin)

## Границы

- Любая попытка cross-tenant запроса → 403.
- Удаление material'а или аспиранта пока через `psql` напрямую (с soft-delete pattern для users; для materials — нет API, ингeстим новый и не используем старый).
- Bulk-операции по привязке к топикам пока через скрипты, не UI.

## Поддержка

- Технические — разработчик (за пределами системы).
- Privacy/governance — `docs/governance.md`.
- Pilot процедуры — `docs/pilot/`.
