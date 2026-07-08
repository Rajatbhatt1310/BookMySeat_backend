from django.contrib import admin
from .models import Movie, Theater, Seat, Booking, Payment, Genre, Language, EmailDelivery


@admin.register(Movie)
class MovieAdmin(admin.ModelAdmin):
    list_display = ['name', 'rating', 'cast', 'description', 'trailer_url']
    list_filter = ['language', 'genres']
    search_fields = ['name', 'cast', 'description']
    filter_horizontal = ['genres']


@admin.register(Theater)
class TheaterAdmin(admin.ModelAdmin):
    list_display = ['name', 'movie', 'time']


@admin.register(Seat)
class SeatAdmin(admin.ModelAdmin):
    list_display = ['theater', 'seat_number', 'is_booked']


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ['user', 'seat', 'movie', 'theater', 'booked_at']

@admin.register(Genre)
class GenreAdmin(admin.ModelAdmin):
    list_display = ["name", "slug"]
    search_fields = ["name", "slug"]
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Language)
class LanguageAdmin(admin.ModelAdmin):
    list_display = ["name", "slug"]
    search_fields = ["name", "slug"]
    prepopulated_fields = {"slug": ("name",)}    

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = [
        "user",
        "theater",
        "amount_display",
        "status",
        "created_at",
    ]
    list_filter = ["status", "created_at"]
    search_fields = [
        "razorpay_order_id",
        "razorpay_payment_id",
        "idempotency_key",
    ]

    @admin.display(description="Amount")
    def amount_display(self, obj):
        return f"₹{obj.amount / 100:.2f}"

@admin.register(EmailDelivery)
class EmailDeliveryAdmin(admin.ModelAdmin):
    list_display = [
        "recipient_email",
        "payment",
        "status",
        "retry_count",
        "sent_at",
        "created_at",
    ]
    list_filter = ["status", "created_at", "sent_at"]
    search_fields = [
        "recipient_email",
        "payment__razorpay_order_id",
        "payment__razorpay_payment_id",
    ]
    readonly_fields = ["last_error", "created_at", "updated_at", "sent_at"]    