import logging
import smtplib
import socket
import ssl
import time
from email.message import EmailMessage
from typing import Iterable

from app.config import Settings, settings

logger = logging.getLogger(__name__)


class EmailConfigError(RuntimeError):
    pass


def _validate_email_settings(config: Settings | None = None) -> None:
    config = config or settings
    mode = (config.email_mode or "smtp").strip().lower()
    if mode == "disabled":
        raise EmailConfigError("Email delivery is disabled for this installation.")
    if mode not in {"smtp", "log"}:
        raise EmailConfigError("Invalid EMAIL_MODE. Use 'smtp' or 'log'.")

    # Never allow silent "log" mode in production.
    if mode == "log":
        if config.is_production:
            raise EmailConfigError("EMAIL_MODE=log is not allowed in production.")
        return

    # Be forgiving about accidental whitespace in env vars.
    if not config.smtp_host.strip() or not config.smtp_from.strip():
        raise EmailConfigError(
            "Configure the SMTP host and sender in Email settings."
        )
    if config.smtp_user.strip() and not config.smtp_password:
        raise EmailConfigError("Configure an SMTP password when a username is set.")


def send_email(
    to_emails: Iterable[str],
    subject: str,
    body: str,
    *,
    raise_on_error: bool = True,
    config: Settings | None = None,
) -> None:
    config = config or settings
    _validate_email_settings(config)

    mode = (config.email_mode or "smtp").strip().lower()
    if mode == "log":
        # Use WARNING so it shows up even if no logging handlers are configured.
        logger.warning(
            "Email (log mode): from=%s to=%s subject=%s body=%s",
            config.smtp_from.strip() or "(unset)",
            ", ".join(to_emails),
            subject,
            (body or "").strip()[:2000],
        )
        return

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = config.smtp_from.strip()
    message["To"] = ", ".join(to_emails)
    message.set_content(body)

    host = config.smtp_host.strip()
    port = config.smtp_port
    user = config.smtp_user.strip()
    # Keep this short since it's running in an ASGI background task.
    timeout_seconds = 10
    max_attempts = 3

    for attempt in range(1, max_attempts + 1):
        try:
            smtp = smtplib.SMTP_SSL if config.smtp_use_ssl else smtplib.SMTP
            connect_options = {"timeout": timeout_seconds}
            if config.smtp_use_ssl:
                connect_options["context"] = ssl.create_default_context()
            with smtp(host, port, **connect_options) as server:
                # STARTTLS is the common mode for ports like 587/2525.
                if config.smtp_use_tls and not config.smtp_use_ssl:
                    server.starttls(context=ssl.create_default_context())
                if user:
                    server.login(user, config.smtp_password)
                server.send_message(message)
            return
        except smtplib.SMTPResponseException as exc:
            # Don't retry hard failures (e.g. 550 sender not verified, 530 auth required, etc.).
            # Retry only for 4xx responses which are more likely to be transient.
            code = getattr(exc, "smtp_code", None)
            is_transient = isinstance(code, int) and 400 <= code < 500
            if is_transient and attempt < max_attempts:
                time.sleep(0.5 * attempt)
                continue
            logger.error("Email send rejected (attempt=%s code=%s)", attempt, code)
            if raise_on_error:
                raise
            return
        except (
            socket.gaierror,
            TimeoutError,
            OSError,
            smtplib.SMTPConnectError,
            smtplib.SMTPServerDisconnected,
        ) as exc:
            if attempt < max_attempts:
                # Simple backoff for transient DNS/network hiccups.
                time.sleep(0.5 * attempt)
                continue
            logger.error("Email send failed after %s attempts (%s)", max_attempts, type(exc).__name__)
            if raise_on_error:
                raise
            return
        except Exception as exc:  # Defensive: never crash the response background task.
            logger.error("Email send failed (%s)", type(exc).__name__)
            if raise_on_error:
                raise
            return
