# Уведомления и внешняя доставка

Система использует transactional outbox: предметная транзакция фиксирует intent, а внешний сетевой вызов выполняется после commit отдельным worker.

## 1. Telegram outbox

NotificationOutbox хранит method, JSON payload, unique dedupe_key, status, attempts, available_at, claimed_at, claim_token, sent_at, last_error и timestamps.

Разрешённый method whitelist определяется backend и Telegram Gateway.

## 2. Enqueue

Dedupe key строится из business coordinates и SHA-256.

Обычный повтор того же intent не создаёт вторую row. DEAD intent может быть явно requeue тем же key через controlled upsert.

Enqueue выполняется в той же транзакции, что и business state, поэтому domain event и обязательный notification intent commit-ятся согласованно.

## 3. Claim

Worker:

1. ищет PENDING или expired PROCESSING rows;
2. использует FOR UPDATE SKIP LOCKED;
3. увеличивает attempts;
4. выставляет PROCESSING;
5. создаёт новый claim_token;
6. фиксирует claim transaction;
7. выполняет внешний HTTP call.

Claim TTL должен быть больше worst-case gateway timeout с safety margin.

## 4. Finalization

Success/failure update выполняется только если row всё ещё имеет ожидаемый claim_token.

Это защищает от ситуации, когда worker A завис, lease истёк, worker B reclaim-нул row, а worker A затем пытается перезаписать результат B.

Retry delay экспоненциальный и bounded. После max attempts row становится DEAD.

## 5. Telegram Gateway

Cloudflare Worker Gateway:

- принимает только POST;
- разрешает только фиксированный набор Telegram Bot API methods;
- проверяет отдельный shared credential;
- request body ограничен 64 KiB;
- JSON должен быть object;
- arbitrary URL proxy невозможен.

Bot credential хранится на Gateway side. Delivery worker обращается к Gateway, а не напрямую к произвольному upstream.

## 6. Telegram start welcome

Start-welcome защищён от stale worker.

Перед send worker проверяет, что update всё ещё является current start для chat.

После ответа message_id извлекается из Telegram response; outbox finalization и update last_welcome_message_id выполняются согласованно. Если за время send появился более новый start, устаревшее сообщение best-effort удаляется.

## 7. Email outbox

EmailOutbox использует тот же lease/token principle.

Email worker имеет отдельный DB role, отдельный egress и Microsoft Graph client credentials. Он стартует только при EMAIL_DELIVERY_ENABLED=true и требует полный Graph config.

Default:

```text
EMAIL_DELIVERY_ENABLED=false
```

## 8. Delivery semantics

Гарантия внешней доставки — at-least-once.

Dedupe предотвращает повторную запись logical outbox intent, но не может атомарно объединить PostgreSQL commit и commit внешнего Telegram/Graph.

Если provider выполнил запрос, а worker потерял response, retry может отправить сообщение повторно.

Exactly-once внешняя доставка не заявляется.

## 9. Ошибки

В БД/log сохраняется безопасная error summary без credentials.

Gateway client не следует redirect, требует HTTPS в production, ограничивает response size и задаёт timeout.

## 10. Monitoring

Нужно контролировать worker container health, heartbeat freshness, PENDING/PROCESSING age, DEAD count, attempts и external error rate.

Heartbeat notification/email worker обновляется после успешной worker iteration; отсутствие heartbeat — unhealthy container.

## 11. Maintenance

Retention worker может удалять завершённые старые technical outbox rows согласно policy, но не warehouse/procurement business history.
