# Incident runbook

Для трёх классов инцидентов: privacy, production, governance. Каждая ветка — конкретные шаги, кто owner, какой timeline.

## Privacy incident

**Триггер:**
- `audit_log.action='privacy.violation_attempt'` ≥ N штук за день (где N зависит от размера группы — для 5-10 студентов N=2 уже подозрительно).
- Confirmed leak: аспирант сообщил, что научрук знает то, что он не должен.
- Потеря секретов (`.env`, БД-backup попал в git, в облако без encryption и т.п.).

**Шаги (в течение 1 рабочего дня):**

1. **Собрать факты.**
   ```sql
   SELECT * FROM audit_log
   WHERE action LIKE 'privacy.%' OR action = 'personal_data.access'
   AND occurred_at > NOW() - INTERVAL '7 days'
   ORDER BY occurred_at DESC;
   ```
   - Кто actor? Какой target? Через какой endpoint?
   - Был ли actor авторизован для target? (Через RBAC matrix.)

2. **Stop the bleed (если active leak).**
   - Bumpнуть `users.jwt_version` всех supervisor / tenant-admin → они выходят, надо перелогиниться.
   - Если LLM exposure — Rolling restart с очищенным prompt cache.
   - Если БД-leak — read-only flag (`tenants.status='read-only'`).

3. **Notify.**
   - Затронутый аспирант (если идентифицирован).
   - Tenant-admin кафедры.
   - DPO / responsible (по `docs/governance.md`).

4. **Root cause + fix.**
   - В коде: какой запрос пропустил защиту? Это bug, regression test mandatory.
   - В governance: нужен доп. control? (Например, max profile views per supervisor per day.)

5. **Post-mortem.**
   - `docs/pilot/incidents/{YYYY-MM-DD}-privacy.md` с timeline, корнем, фиксом, мерами.
   - Анонимизированно — не пишите имён в файле, который пойдёт в git.

## Production incident

**Триггер:**
- `/health` возвращает не 200 более 5 минут.
- Аспиранты репортят, что не могут залогиниться или что-то не работает.
- Massive 5xx в логах.
- Постгрес недоступен.

**Шаги (немедленно):**

1. **Триаж — что упало?**
   - `docker compose ps` — все ли контейнеры up?
   - `docker compose logs app | tail -100` — последние ошибки.
   - `docker compose logs postgres | tail -100`.
   - `htop` на VPS — RAM/CPU/диск.

2. **Quick recovery.**
   - Если app crashed: `docker compose restart app`.
   - Если postgres OOM: `docker compose restart postgres` + увеличить RAM (escalate VPS plan).
   - Если LLM провайдер down: акцептируем (не наша ответственность), сообщаем пользователям в чат «временные проблемы».

3. **Communicate.**
   - В Telegram-чат пилотной группы — короткое сообщение «работаем над этим, ETA ~15 мин».
   - Ничего не обещайте по конкретному времени, если не уверены.

4. **Если undue downtime > 1 час:**
   - Откат к предыдущему image: `docker compose pull && docker compose up -d`.
   - Восстановление БД из последнего pg_dump.
   - Сообщение с признанием простоя в Telegram + по email.

5. **Post-mortem.**
   - `docs/pilot/incidents/{YYYY-MM-DD}-prod.md`.
   - Что упало? Сколько простаивало? Что чиним чтобы не повторилось?

## Governance incident

**Триггер:**
- Аспирант отзывает согласие на обработку данных (BDD 7.3).
- Запрос на portability data export.
- Методист меняется (need to revoke + invite new).
- Конфликт между tenant-admin и supervisor по отображаемым данным.

### Согласие отозвано

Аспирант пишет «удалите мои данные» (через email tenant-admin или формальный запрос).

1. Tenant-admin подтверждает identity (email matches, или личная встреча).
2. Через `psql`:
   ```sql
   UPDATE users SET deleted_at = NOW() WHERE email = '<email>' AND tenant_id = ...;
   UPDATE selfcheck_attempts SET user_id = NULL WHERE user_id = '<user_id>';
   UPDATE qa_feedback SET user_id = NULL WHERE user_id = '<user_id>';
   ```
   Soft-delete + анонимизация (BDD 7.3): аспирант больше не может залогиниться, его попытки остаются в анонимизированной agg.
3. Записать в audit-log:
   ```sql
   INSERT INTO audit_log (action, target_type, target_id, details)
   VALUES ('user.delete', 'user', '<user_id>',
           '{"reason": "consent revoked", "method": "soft-delete + anonymization"}'::jsonb);
   ```
4. Подтвердить аспиранту по email что данные удалены.

### Data export request

Аспирант просит свои данные в machine-readable формате.

1. Соберите:
   ```sql
   SELECT * FROM users WHERE id = '<user_id>';
   SELECT * FROM selfcheck_attempts WHERE user_id = '<user_id>';
   SELECT * FROM qa_feedback WHERE user_id = '<user_id>';
   SELECT * FROM audit_log WHERE actor_id = '<user_id>' OR target_id = '<user_id>';
   ```
2. Экспортируйте в JSON / CSV. Передайте через защищённый канал (зашифрованный архив с паролем по другому каналу).
3. Логируем в audit:
   ```sql
   INSERT INTO audit_log (action, target_type, target_id, details)
   VALUES ('data.export', 'user', '<user_id>', '{"requested_by": "self"}'::jsonb);
   ```

### Смена tenant-admin'а

1. Создаём нового tenant-admin'а — отправляем invite с role='tenant-admin'.
2. После redemption — bump `jwt_version` старого tenant-admin'а (логаут):
   ```sql
   UPDATE users SET jwt_version = jwt_version + 1 WHERE email = '<old_admin_email>';
   ```
3. Меняем role старого:
   ```sql
   UPDATE users SET role = 'student' WHERE email = '<old_admin_email>';
   -- или просто soft-delete если он уходит совсем
   ```
4. Логируем:
   ```sql
   INSERT INTO audit_log (action, target_type, target_id, details)
   VALUES ('user.role.revoke', 'user', '<old_user_id>',
           '{"from": "tenant-admin", "to": "student", "reason": "succession"}'::jsonb);
   ```

---

## Принципы

1. **Сначала остановите кровь, потом разбирайтесь.** Если данные утекают — закрываем доступ за 5 минут, разбираемся за неделю.
2. **Документируйте все incident'ы.** `docs/pilot/incidents/{YYYY-MM-DD}-{type}.md` — обязательно. Это и для следующего цикла, и для governance.
3. **Не молчите.** Пользователи прощают сбои, но не прощают молчание. Telegram-сообщение «у нас инцидент, ETA 15 мин» — must.
4. **Не вините людей.** Privacy violation чаще всего bug в коде или процессах, а не злая воля. Найдите root cause, починьте, не охотьтесь на ведьм.
