from django.core.mail import EmailMultiAlternatives
from django.core.mail.backends.base import BaseEmailBackend
from django.conf import settings

import requests


class ResendEmailBackend(BaseEmailBackend):
    def send_messages(self, email_messages):
        sent = 0

        for message in email_messages:
            html_content = None

            if isinstance(message, EmailMultiAlternatives):
                for content, mimetype in message.alternatives:
                    if mimetype == "text/html":
                        html_content = content
                        break

            response = requests.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {settings.RESEND_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "from": message.from_email,
                    "to": message.to,
                    "subject": message.subject,
                    "text": message.body,
                    "html": html_content,
                },
            )

            if response.ok:
                sent += 1

        return sent