from __future__ import annotations

import asyncio
import hashlib
import html
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import quote

import httpx
from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.config import Settings, get_settings
from app.core.worker_health import write_worker_heartbeat
from app.db.engine import create_engine
from app.modules.procurement.models import EmailOutbox
from app.modules.procurement.notifications import composition_summary, procurement_deep_link
from app.modules.procurement.schemas import ProcurementEmailCreate
from app.modules.procurement.service import (
    ProcurementConflictError,
    ProcurementRecord,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ClaimedEmail:
    id: uuid.UUID
    claim_token: uuid.UUID
    to: list[str]
    cc: list[str]
    subject: str
    text_body: str
    html_body: str
    attempts: int


def email_dedupe_key(
    request_id: uuid.UUID, actor_user_id: uuid.UUID, client_request_id: str
) -> str:
    raw = f"procurement-email|{request_id}|{actor_user_id}|{client_request_id}"
    return hashlib.sha256(raw.encode()).hexdigest()


async def enqueue_procurement_email(
    db: AsyncSession,
    *,
    record: ProcurementRecord,
    payload: ProcurementEmailCreate,
    actor_user_id: uuid.UUID,
    settings: Settings,
) -> EmailOutbox:
    if record.request.status.value != "COMPLETED":
        raise ProcurementConflictError(
            "procurement email is available only after completion",
            code="email_before_completion",
        )
    client_request_id = " ".join(payload.client_request_id.split())
    key = email_dedupe_key(record.request.id, actor_user_id, client_request_id)
    link = procurement_deep_link(settings, record.request.id)
    lines = record.current_revision.lines
    plain_positions = composition_summary(lines)
    subject = f"Закупка {record.request.request_number} выполнена"
    text_body = (
        f"Закупка {record.request.request_number}\n\n"
        f"Позиции:\n{plain_positions}\n\n"
        f"Открыть заявку: {link}"
    )
    html_lines = "".join(
        f"<li>{html.escape(str(line.display_snapshot.get('name') or 'Позиция'))} "
        f"— {line.quantity} шт.</li>"
        for line in lines
    )
    html_body = (
        f"<h1>Закупка {html.escape(record.request.request_number)}</h1>"
        f"<ul>{html_lines}</ul>"
        f'<p><a href="{html.escape(link, quote=True)}">Открыть заявку</a></p>'
    )
    await db.execute(
        pg_insert(EmailOutbox)
        .values(
            id=uuid.uuid4(),
            request_id=record.request.id,
            to_addresses=payload.to,
            cc_addresses=payload.cc,
            subject=subject,
            text_body=text_body,
            html_body=html_body,
            dedupe_key=key,
        )
        .on_conflict_do_nothing(index_elements=[EmailOutbox.dedupe_key])
    )
    row = await db.scalar(select(EmailOutbox).where(EmailOutbox.dedupe_key == key))
    if row is None:
        raise RuntimeError("email outbox insert was not visible")
    return row


async def claim_email_batch(
    db: AsyncSession,
    *,
    batch_size: int,
    claim_ttl_seconds: int,
    max_attempts: int,
    now: datetime | None = None,
) -> list[ClaimedEmail]:
    current = now or datetime.now(UTC)
    stale = current - timedelta(seconds=claim_ttl_seconds)

    rows = list(
        (
            await db.scalars(
                select(EmailOutbox)
                .where(
                    EmailOutbox.status == "PENDING",
                    EmailOutbox.available_at <= current,
                    or_(
                        EmailOutbox.attempts < max_attempts,
                        (
                            (EmailOutbox.attempts >= max_attempts)
                            & EmailOutbox.claimed_at.is_not(None)
                            & (EmailOutbox.claimed_at < stale)
                        ),
                    ),
                    or_(
                        EmailOutbox.claimed_at.is_(None),
                        EmailOutbox.claimed_at < stale,
                    ),
                )
                .order_by(
                    EmailOutbox.available_at,
                    EmailOutbox.created_at,
                    EmailOutbox.id,
                )
                .limit(batch_size)
                .with_for_update(skip_locked=True)
            )
        ).all()
    )

    claims: list[ClaimedEmail] = []

    for row in rows:
        token = uuid.uuid4()
        was_stale_final_attempt = (
            row.attempts >= max_attempts and row.claimed_at is not None and row.claimed_at < stale
        )

        row.claimed_at = current
        row.claim_token = token

        if not was_stale_final_attempt:
            row.attempts += 1

        claims.append(
            ClaimedEmail(
                id=row.id,
                claim_token=token,
                to=list(row.to_addresses),
                cc=list(row.cc_addresses),
                subject=row.subject,
                text_body=row.text_body,
                html_body=row.html_body,
                attempts=row.attempts,
            )
        )

    await db.flush()
    return claims


async def finalize_email(
    db: AsyncSession,
    claim: ClaimedEmail,
    *,
    error: str | None,
    max_attempts: int,
) -> bool:
    row = await db.scalar(
        select(EmailOutbox)
        .where(
            EmailOutbox.id == claim.id,
            EmailOutbox.claim_token == claim.claim_token,
            EmailOutbox.status == "PENDING",
        )
        .with_for_update()
    )
    if row is None:
        return False
    row.claimed_at = None
    row.claim_token = None
    if error is None:
        row.status = "SENT"
        row.sent_at = datetime.now(UTC)
        row.last_error = None
    else:
        row.last_error = error[:1000]
        if row.attempts >= max_attempts:
            row.status = "DEAD"
        else:
            row.available_at = datetime.now(UTC) + timedelta(
                seconds=min(300, 1 << min(max(0, row.attempts - 1), 8))
            )
    await db.flush()
    return True


class MicrosoftGraphError(RuntimeError):
    pass


class MicrosoftGraphClient:
    def __init__(
        self,
        *,
        tenant_id: str,
        client_id: str,
        client_secret: str,
        sender: str,
        timeout_seconds: int,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.client_secret = client_secret
        self.sender = sender
        self.timeout_seconds = timeout_seconds
        self.client = httpx.AsyncClient(
            timeout=float(timeout_seconds), follow_redirects=False, transport=transport
        )

    async def _token(self) -> str:
        try:
            tenant = quote(self.tenant_id, safe="")
            response = await self.client.post(
                f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "scope": "https://graph.microsoft.com/.default",
                    "grant_type": "client_credentials",
                },
            )
            response.raise_for_status()
            value = response.json().get("access_token")
        except (httpx.HTTPError, ValueError) as error:
            raise MicrosoftGraphError("Microsoft Graph OAuth request failed") from error
        if not isinstance(value, str) or not value:
            raise MicrosoftGraphError("Microsoft Graph OAuth response has no access token")
        return value

    async def send(self, claim: ClaimedEmail) -> None:
        token = await self._token()
        message = {
            "subject": claim.subject,
            "body": {"contentType": "HTML", "content": claim.html_body},
            "toRecipients": [{"emailAddress": {"address": address}} for address in claim.to],
            "ccRecipients": [{"emailAddress": {"address": address}} for address in claim.cc],
        }
        try:
            response = await self.client.post(
                f"https://graph.microsoft.com/v1.0/users/{quote(self.sender, safe='')}/sendMail",
                headers={"Authorization": f"Bearer {token}"},
                json={"message": message, "saveToSentItems": True},
            )
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise MicrosoftGraphError("Microsoft Graph sendMail request failed") from error

    async def aclose(self) -> None:
        await self.client.aclose()


def validate_email_worker_config(settings: Settings) -> None:
    missing = [
        name
        for name, value in (
            ("MICROSOFT_GRAPH_TENANT_ID", settings.microsoft_graph_tenant_id_value),
            ("MICROSOFT_GRAPH_CLIENT_ID", settings.microsoft_graph_client_id_value),
            ("MICROSOFT_GRAPH_CLIENT_SECRET", settings.microsoft_graph_client_secret_value),
            ("MICROSOFT_GRAPH_SENDER", settings.microsoft_graph_sender_value),
        )
        if value is None
    ]
    if missing:
        raise RuntimeError(
            "Microsoft Graph email worker configuration is incomplete: " + ", ".join(missing)
        )
    if settings.email_worker_claim_ttl_seconds < settings.microsoft_graph_timeout_seconds * 2 + 5:
        raise RuntimeError("EMAIL_WORKER_CLAIM_TTL_SECONDS is too short")


def configured_graph_client(settings: Settings) -> MicrosoftGraphClient:
    validate_email_worker_config(settings)
    assert settings.microsoft_graph_tenant_id_value is not None
    assert settings.microsoft_graph_client_id_value is not None
    assert settings.microsoft_graph_client_secret_value is not None
    assert settings.microsoft_graph_sender_value is not None
    return MicrosoftGraphClient(
        tenant_id=settings.microsoft_graph_tenant_id_value,
        client_id=settings.microsoft_graph_client_id_value,
        client_secret=settings.microsoft_graph_client_secret_value,
        sender=settings.microsoft_graph_sender_value,
        timeout_seconds=settings.microsoft_graph_timeout_seconds,
    )


async def run_email_worker_once(
    engine: AsyncEngine,
    client: MicrosoftGraphClient,
    settings: Settings,
) -> int:
    processed = 0

    for _ in range(settings.email_worker_batch_size):
        async with (
            AsyncSession(engine, expire_on_commit=False) as db,
            db.begin(),
        ):
            claims = await claim_email_batch(
                db,
                batch_size=1,
                claim_ttl_seconds=settings.email_worker_claim_ttl_seconds,
                max_attempts=settings.email_worker_max_attempts,
            )

        if not claims:
            break

        claim = claims[0]
        error: str | None = None

        try:
            await client.send(claim)
        except Exception as exc:
            error = type(exc).__name__
            logger.warning(
                "Email delivery failed id=%s attempt=%s error=%s",
                claim.id,
                claim.attempts,
                error,
            )

        async with (
            AsyncSession(engine, expire_on_commit=False) as db,
            db.begin(),
        ):
            await finalize_email(
                db,
                claim,
                error=error,
                max_attempts=settings.email_worker_max_attempts,
            )

        processed += 1

    return processed


async def run_email_worker() -> None:
    settings = get_settings()
    client = configured_graph_client(settings)
    engine = create_engine(settings, application_name="dc-inventory-email-worker")
    try:
        while True:
            try:
                processed = await run_email_worker_once(engine, client, settings)
            except Exception:
                logger.exception("Email worker iteration failed")
                processed = 0
            else:
                write_worker_heartbeat()
            if processed == 0:
                await asyncio.sleep(settings.email_worker_poll_seconds)
    finally:
        await client.aclose()
        await engine.dispose()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_email_worker())


if __name__ == "__main__":
    main()
