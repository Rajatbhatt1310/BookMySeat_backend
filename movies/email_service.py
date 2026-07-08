import logging

import requests

from django.conf import settings
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.html import strip_tags

from .models import EmailDelivery

logger = logging.getLogger("movies.email")


def send_booking_confirmation(payment, recipient_email):
    """
    Sends booking confirmation email using Brevo API.
    Returns: "sent" or "failed"
    """

    email_delivery, _ = EmailDelivery.objects.get_or_create(
        payment=payment,
        defaults={
            "recipient_email": recipient_email,
            "subject": f"Booking Confirmed - {payment.theater.movie.name}",
            "status": "queued",
        },
    )

    try:
        context = {
            "user": payment.user,
            "payment": payment,
            "movie": payment.theater.movie,
            "theater": payment.theater,
            "seats": payment.seats.all(),
            "amount": payment.amount / 100,
        }

        html_content = render_to_string(
            "emails/booking_confirmation.html",
            context,
        )

        text_content = strip_tags(html_content)

        api_key = settings.BREVO_API_KEY

        headers = {
            "accept": "application/json",
            "api-key": api_key,
            "content-type": "application/json",
        }

        payload = {
            "sender": {
                "name": "BookMySeat",
                "email": "rajatbhatt1310@gmail.com",
            },
            "to": [
                {
                    "email": recipient_email,
                }
            ],
            "subject": email_delivery.subject,
            "htmlContent": html_content,
            "textContent": text_content,
        }

        print("=" * 60)
        print("CALLING BREVO EMAIL API")
        print("TO:", recipient_email)
        print("SUBJECT:", email_delivery.subject)
        print("=" * 60)

        response = requests.post(
            "https://api.brevo.com/v3/smtp/email",
            headers=headers,
            json=payload,
            timeout=20,
        )

        print("BREVO STATUS:", response.status_code)
        print("BREVO RESPONSE:", response.text)

        response.raise_for_status()

        email_delivery.status = "sent"
        email_delivery.sent_at = timezone.now()
        email_delivery.last_error = ""
        email_delivery.save()

        logger.info(
            "Booking confirmation email sent to %s",
            recipient_email,
        )

        return "sent"

    except Exception:
        import traceback

        full_error = traceback.format_exc()

        print("=" * 60)
        print("BREVO EMAIL FAILED")
        print(full_error)
        print("=" * 60)

        email_delivery.status = "failed"
        email_delivery.retry_count += 1
        email_delivery.last_error = full_error
        email_delivery.save()

        logger.exception(
            "Failed to send booking confirmation email."
        )

        return "failed"