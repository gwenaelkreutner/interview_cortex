import logging
import uuid

from clients.base import EmailClientProtocol, EmailReceipt

logger = logging.getLogger(__name__)


class EmailClient(EmailClientProtocol):
    """
    Stub implementation of the email delivery client.
    Replace with a real SMTP / SES / SendGrid adapter in production.
    """

    def __init__(self, from_address: str, provider: str = "stub"):
        self._from_address = from_address
        self._provider = provider
        logger.info(f"[EmailClient] initialized (provider={provider}, from={from_address})")

    def send(self, to: str, subject: str, body_html: str, body_text: str) -> EmailReceipt:
        logger.info(f"[EmailClient] Sending email → to={to} | subject={subject!r}")
        return EmailReceipt(message_id=str(uuid.uuid4()), accepted=True)
