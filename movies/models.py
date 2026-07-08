from django.db import models
from django.contrib.auth.models import User
from django.conf import settings

class Genre(models.Model):
    name = models.CharField(max_length=80, unique=True, db_index=True)
    slug = models.SlugField(max_length=90, unique=True, db_index=True)

    def __str__(self):
        return self.name


class Language(models.Model):
    name = models.CharField(max_length=80, unique=True, db_index=True)
    slug = models.SlugField(max_length=90, unique=True, db_index=True)

    def __str__(self):
        return self.name

class Movie(models.Model):
    name = models.CharField(max_length=255)

    image = models.ImageField(
        upload_to="movies/",
        blank=True,
        null=True,
    )

    image_url = models.URLField(
        blank=True,
        null=True,
        help_text="Paste a direct image URL (TMDB, IMDb, etc.)",
    )

    rating = models.DecimalField(max_digits=3, decimal_places=1)
    cast = models.TextField()
    description = models.TextField(blank=True, null=True)
    trailer_url = models.URLField(blank=True, null=True)

    genres = models.ManyToManyField(
        Genre,
        related_name="movies",
        blank=True,
    )

    language = models.ForeignKey(
        Language,
        on_delete=models.SET_NULL,
        related_name="movies",
        null=True,
        blank=True,
    )

    def __str__(self):
        return self.name
    

    class Meta:
        indexes = [
            models.Index(fields=["name"]),
            models.Index(fields=["rating"]),
            models.Index(fields=["language"]),
        ]

class Theater(models.Model):
    name = models.CharField(max_length=255)
    movie = models.ForeignKey(
        Movie,
        on_delete=models.CASCADE,
        related_name="theaters"
    )
    time = models.DateTimeField()

    def __str__(self):
        return f"{self.name} - {self.movie.name} at {self.time}"


class Seat(models.Model):
    theater = models.ForeignKey(
        Theater,
        on_delete=models.CASCADE,
        related_name="seats"
    )
    seat_number = models.CharField(max_length=10)
    is_booked = models.BooleanField(default=False)

    locked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL
    )

    locked_until = models.DateTimeField(
        null=True,
        blank=True
    )

    def __str__(self):
        return f"{self.theater.name} - {self.seat_number}"

    class Meta:
        indexes = [
            models.Index(fields=["theater"]),
            models.Index(fields=["is_booked"]),
            models.Index(fields=["locked_until"]),
        ]


class Booking(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    seat = models.OneToOneField(Seat, on_delete=models.CASCADE)
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE)
    theater = models.ForeignKey(Theater, on_delete=models.CASCADE)
    booked_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return (
            f"Booking by {self.user.username} "
            f"for {self.seat.seat_number} "
            f"at {self.theater.name}"
        )

    class Meta:
        indexes = [
            models.Index(fields=["booked_at"]),
            models.Index(fields=["movie"]),
            models.Index(fields=["theater"]),
            models.Index(fields=["user"]),
        ]


class Payment(models.Model):
    STATUS_CHOICES = [
        ("created", "Created"),
        ("paid", "Paid"),
        ("failed", "Failed"),
        ("cancelled", "Cancelled"),
        ("expired", "Expired"),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE
    )

    theater = models.ForeignKey(
        Theater,
        on_delete=models.CASCADE
    )

    seats = models.ManyToManyField(
        Seat
    )

    razorpay_order_id = models.CharField(
        max_length=100,
        unique=True
    )

    razorpay_payment_id = models.CharField(
        max_length=100,
        blank=True,
        null=True
    )

    razorpay_signature = models.CharField(
        max_length=255,
        blank=True,
        null=True
    )

    amount = models.PositiveIntegerField()
    

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="created"
    )

    idempotency_key = models.CharField(
        max_length=64,
        unique=True
    )

    webhook_event_id = models.CharField(
        max_length=100,
        unique=True,
        blank=True,
        null=True
    )

    expires_at = models.DateTimeField(
        null=True,
        blank=True
    )

    failure_reason = models.TextField(
        blank=True,
        null=True
    )

    cancel_reason = models.TextField(
        blank=True,
        null=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    def __str__(self):
        return f"{self.razorpay_order_id} - {self.status}"
    @property
    def amount_rupees(self):
        return self.amount / 10

    class Meta:
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["created_at"]),
            models.Index(fields=["updated_at"]),
            models.Index(fields=["user"]),
            models.Index(fields=["theater"]),
        ]
class EmailDelivery(models.Model):
    STATUS_CHOICES = [
        ("queued", "Queued"),
        ("sent", "Sent"),
        ("failed", "Failed"),
    ]

    payment = models.OneToOneField(
        Payment,
        on_delete=models.CASCADE,
        related_name="email_delivery"
    )

    recipient_email = models.EmailField()

    subject = models.CharField(max_length=255)

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="queued"
    )

    retry_count = models.PositiveIntegerField(default=0)

    max_retries = models.PositiveIntegerField(default=3)

    last_error = models.TextField(blank=True, null=True)

    sent_at = models.DateTimeField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.recipient_email} - {self.status}"

    class Meta:
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["retry_count"]),
            models.Index(fields=["created_at"]),
        ]

class PaymentWebhookEvent(models.Model):
    event_id = models.CharField(
        max_length=100,
        unique=True
    )

    payment = models.ForeignKey(
        Payment,
        on_delete=models.CASCADE,
        related_name="webhook_events"
    )

    event_type = models.CharField(
        max_length=100
    )

    received_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return f"{self.event_id} - {self.event_type}"

    class Meta:
        indexes = [
            models.Index(fields=["event_id"]),
            models.Index(fields=["event_type"]),
            models.Index(fields=["received_at"]),
        ]        