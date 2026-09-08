# Telegram Notification Idempotency Plan

## Confirmed Findings

1. `Payment` has one `post_save` notification receiver, guarded by `created`, and it is imported from the single `NotificationsConfig.ready()` hook. The separate customer payment signal only recalculates business totals and does not notify. No second notification registration or direct payment notification call was found.
2. The payment receiver correctly registers `transaction.on_commit`, so a rolled-back payment does not enqueue a notification. It does not itself explain three executions.
3. `NotificationLog` already has a database unique constraint on `(event_type, event_id)`, so concurrent signal callbacks cannot create three log rows for one payment. However, the row is created before dispatch and the dispatch path is unsafe: it probes `Worker.all()`, uses a daemon thread when no worker is visible, and starts another daemon-thread execution when RQ enqueue raises. A worker can be alive but not visible at probe time, and an enqueue can succeed before the caller observes an exception. These fallback paths can run the same log ID concurrently.
4. `send_notification_task` only checks `status == SENT` before the external call. Multiple workers/threads can all read `PENDING` and call Apprise before any one writes `SENT`; the status check is therefore not an idempotency lock.
5. The task explicitly loops through `NOTIFICATION_MAX_RETRIES`, whose default is `3`, and sleeps between attempts. Thus the three logged attempts are the configured retry loop, not evidence that Django emitted three payment signals. If Apprise reports a failure after Telegram accepted the request, the next call sends the same message again.
6. Apprise/Telegram has no transaction with the database and the current `send_telegram()` call has no provider-side idempotency key. A crash or timeout after Telegram accepts the message but before the DB update is fundamentally ambiguous. The requested strict at-most-once policy must claim the notification before calling Apprise and cannot automatically retry after that claim.
7. Production uses three Gunicorn web workers plus a separate RQ worker service. Multiple processes are expected and make database-level claiming mandatory; they are not by themselves a duplicate cause when the claim is atomic.

## Decisions

- Use strict at-most-once delivery for payment and sale notifications: one durable notification row, one enqueue attempt, and at most one Apprise invocation for that row.
- Remove the in-process retry loop. A send failure is recorded as terminal `FAILED` for manual/admin replay. Automatic replay is intentionally out of scope because it can duplicate a message after an ambiguous provider response.
- Keep notification failures completely outside the business transaction. Signal callbacks and enqueue callbacks must catch/log notification errors; payment creation must still commit.
- Use PostgreSQL/MySQL-compatible row locking and conditional updates for the send claim. Preserve SQLite test compatibility by handling unsupported locking as a normal single-process test path; do not use a process-local lock as the correctness mechanism.
- Do not use a “worker discovery” health check or daemon-thread fallback. Production delivery is through RQ only. If Redis/enqueue fails, leave the durable row pending/dispatch-failed for an explicit recovery command or admin action, without sending inline.

## Implementation Steps

1. Extend `NotificationLog` with explicit delivery state needed for an atomic claim, such as `CLAIMED`/`SENDING` or a `send_started_at` field, and retain `FAILED`/`SENT`. Add migration(s). Ensure the existing unique `(event_type, event_id)` constraint remains the canonical event idempotency key.
2. Refactor `services.notify()` to atomically create-or-ignore the event row, without a pre-check. Register RQ enqueue with `transaction.on_commit` when called inside a business transaction, or otherwise enqueue once immediately. Enqueue only the newly created row, never a fallback thread. Catch Redis/RQ errors, log them with event and row IDs, and mark the row as dispatch-failed/pending for recovery; never re-raise.
3. Make enqueueing deterministic and observable. Use a stable RQ job ID derived from the notification row ID (or an equivalent uniqueness mechanism supported by the installed RQ version), and configure the job not to be silently duplicated. Do not call `Worker.all()` to decide dispatch behavior. Document that one RQ worker process is sufficient; multiple workers are safe because the DB claim serializes delivery.
4. Rewrite `send_notification_task()` as a single-attempt state machine:
   - Fetch the row and return for `SENT` or terminal `FAILED`.
   - Atomically transition `PENDING`/dispatch-ready to `SENDING` only if it is not already claimed, then reload the row.
   - If another worker gets no updated row, return without calling Apprise.
   - Increment/persist `attempts` as one, call `send_telegram()` exactly once, and on success update `SENT`/`sent_at`.
   - On any Apprise/configuration exception, update `FAILED` and error details without raising into RQ or application code.
   - Update `TelegramSetting.last_notified_at` only after a successful send and make that bookkeeping failure non-fatal to the notification result.
5. Add a safe, explicit recovery path for operational failures: an admin action or management command may reset a `FAILED`/dispatch-failed row to `PENDING` only after an operator confirms Telegram did not receive it. It must create a new auditable replay event or require an explicit force flag; never automatically replay all failures.
6. Keep the signal structure but simplify it so each `post_save(created=True)` callback schedules only the durable notification creation after commit. Avoid doing configuration checks in the signal path that could cause a notification to be dropped merely because settings/cache are temporarily unavailable; record the event and let the task mark it failed when configuration is missing.
7. Add tests covering:
   - Payment creation causes exactly one `NotificationLog` row and one RQ enqueue, including repeated `notify()` calls and concurrent duplicate creation.
   - Payment updates and the customer payment recalculation signal do not create notifications.
   - Rollback creates neither a notification row nor a job.
   - Two task invocations for the same row result in only one mocked `send_telegram()` call and the loser exits.
   - A successful send is marked `SENT`; a failed send is marked `FAILED` with `attempts == 1`; no automatic second call occurs.
   - RQ enqueue/Redis failure does not raise into payment creation.
   - Apprise false/exception results are recorded safely.
   - Existing sale notification behavior remains deduplicated independently from payment notifications.
8. Update deployment/configuration documentation and `CLAUDE.md` to describe RQ-only dispatch, strict at-most-once semantics, manual replay, and the unavoidable crash window: a worker crash after Telegram accepts a message and before `SENT` is recorded leaves the row in `SENDING` and must not be automatically retried under this policy.

## Validation

- Run `python manage.py check` and `python manage.py makemigrations --check`.
- Run the notification test module and the affected payment/sales test modules, then the full Django suite.
- Exercise a real Redis/RQ worker with two concurrent invocations for one notification ID and verify one Apprise call and one Telegram message.
- Inspect production `NotificationLog` rows by `(event_type, event_id)`, RQ job IDs, status transitions, and attempt counts after deployment. Confirm there is no daemon-thread fallback and that payment HTTP responses/transactions are unaffected when Redis, Apprise, or Telegram is unavailable.

## Rollout Notes

- Deploy the schema migration before application code that writes the new state.
- Existing duplicate rows cannot exist under the current unique constraint; existing `SENT` rows must remain terminal. Existing `PENDING` rows should be reviewed before deployment and either sent once by the new task or marked for manual review.
- Historical Telegram duplicates cannot be removed by the application; use the new logs and attempt metadata to correlate the reported incident.
