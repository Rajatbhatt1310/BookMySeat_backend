import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.html import strip_tags

from .models import Seat, Payment, EmailDelivery


logger = logging.getLogger("movies.email")


def release_expired_locks():
    now = timezone.now()

    count = Seat.objects.filter(
        is_booked=False,
        locked_until__isnull=False,
        locked_until__lt=now
    ).update(
        locked_by=None,
        locked_until=None
    )

    print(f"Expired locks released: {count}")


def expire_pending_payments():
    now = timezone.now()

    expired_payments = Payment.objects.filter(
        status="created",
        expires_at__isnull=False,
        expires_at__lt=now
    ).prefetch_related("seats")

    expired_count = 0
    released_seat_count = 0

    for payment in expired_payments:
        with transaction.atomic():
            locked_seats = payment.seats.select_for_update().filter(
                is_booked=False,
                locked_by=payment.user
            )

            released_seat_count += locked_seats.update(
                locked_by=None,
                locked_until=None
            )

            payment.status = "expired"
            payment.failure_reason = "Payment timeout. User did not complete payment within allowed time."
            payment.save(update_fields=["status", "failure_reason", "updated_at"])

            expired_count += 1

    print(f"Expired payments marked: {expired_count}")
    print(f"Seats released after payment timeout: {released_seat_count}")


def process_queued_booking_emails():
    queued_emails = (
        EmailDelivery.objects
        .select_related("payment", "payment__user", "payment__theater", "payment__theater__movie")
        .filter(status="queued", retry_count__lt=3)
        .order_by("created_at")[:10]
    )

    for email_delivery in queued_emails:
        try:
            send_booking_confirmation_email(email_delivery)

            email_delivery.status = "sent"
            email_delivery.sent_at = timezone.now()
            email_delivery.last_error = None
            email_delivery.save(
                update_fields=["status", "sent_at", "last_error", "updated_at"]
            )

            logger.info(
                "Booking confirmation email sent to %s for payment %s",
                email_delivery.recipient_email,
                email_delivery.payment.razorpay_order_id,
            )

        except Exception as error:
            import traceback
        
            print("=" * 60)
            print("EMAIL QUEUE EXCEPTION")
            traceback.print_exc()
            print("=" * 60)
        
            email_delivery.retry_count += 1
            email_delivery.last_error = str(error)
        
            if email_delivery.retry_count >= email_delivery.max_retries:
                email_delivery.status = "failed"
        
            email_delivery.save(
                update_fields=["retry_count", "last_error", "status", "updated_at"]
            )
        
            logger.exception(
                "Booking confirmation email failed for %s",
                email_delivery.recipient_email,
            )


def send_booking_confirmation_email(email_delivery):
    payment = email_delivery.payment
    theater = payment.theater
    movie = theater.movie

    seat_numbers = list(
        payment.seats.order_by("seat_number").values_list("seat_number", flat=True)
    )

    context = {
        "user_name": payment.user.username,
        "booking_id": f"BMS-{payment.id}",
        "movie_name": movie.name,
        "theater_name": theater.name,
        "theater_time": theater.time,
        "seats": ", ".join(seat_numbers),
        "amount": payment.amount // 100,
        "payment_id": payment.razorpay_payment_id,
    }

    html_body = render_to_string("emails/booking_confirmation.html", context)
    text_body = strip_tags(html_body)

    email = EmailMultiAlternatives(
        subject=email_delivery.subject,
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[email_delivery.recipient_email],
    )

    email.attach_alternative(html_body, "text/html")

    print("=" * 60)
    print("ABOUT TO SEND EMAIL")
    print("TO:", email_delivery.recipient_email)
    print("HOST:", settings.EMAIL_HOST)
    print("USER:", settings.EMAIL_HOST_USER)
    print("=" * 60)

    result = email.send(fail_silently=False)

    print("EMAIL SENT")
    print("SEND RESULT:", result)
    print("=" * 60)