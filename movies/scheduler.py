from apscheduler.schedulers.background import BackgroundScheduler

from .tasks import (
    release_expired_locks,
    expire_pending_payments,
    process_queued_booking_emails,
)

scheduler = BackgroundScheduler()


def start():
    if scheduler.running:
        print("Scheduler already running")
        return

    scheduler.add_job(
        process_queued_booking_emails,
        "interval",
        seconds=20,
        id="process_queued_booking_emails",
        replace_existing=True,
    )

    scheduler.add_job(
        expire_pending_payments,
        "interval",
        seconds=30,
        id="expire_pending_payments",
        replace_existing=True,
    )

    scheduler.start()
    print("Scheduler Started")