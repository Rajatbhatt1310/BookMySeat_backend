from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError
from django.http import JsonResponse
from .models import (
    Movie,
    Theater,
    Seat,
    Booking,
    Payment,
    PaymentWebhookEvent,
    Genre,
    Language,
    EmailDelivery,
    
)
import threading
from .utilities import get_youtube_embed_url
from django.http import JsonResponse
import json, razorpay, hmac, hashlib, uuid
from django.conf import settings
from datetime import timedelta
from django.utils import timezone
from django.db import transaction
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import user_passes_test
from django.core.cache import cache
from django.db.models import Count, Sum, Q, F, FloatField, ExpressionWrapper
from django.db.models.functions import TruncDate, TruncWeek, TruncMonth, ExtractHour
from django.views.decorators.http import require_POST
from django.core.paginator import Paginator, EmptyPage
from .email_service import send_booking_confirmation


def movie_list(request):
    search_query = request.GET.get("search")

    if search_query:
        movies = Movie.objects.filter(name__icontains=search_query)
    else:
        movies = Movie.objects.all()

    return render(request, "movies/movie_list.html", {
        "movies": movies
    })


def movie_detail(request, movie_id):
    movie = get_object_or_404(Movie, id=movie_id)

    trailer_embed_url = get_youtube_embed_url(movie.trailer_url)

    return render(request, "movies/movie_detail.html", {
        "movie": movie,
        "trailer_embed_url": trailer_embed_url,
    })


def theater_list(request, movie_id):
    movie = get_object_or_404(Movie, id=movie_id)
    theaters = Theater.objects.filter(movie=movie)

    return render(request, "movies/theater_list.html", {
        "movie": movie,
        "theaters": theaters
    })


@login_required(login_url="/login/")
def book_seats(request, theater_id):
    theater = get_object_or_404(Theater, id=theater_id)
    seats = Seat.objects.filter(theater=theater)

    if request.method == "POST":
        selected_seats = request.POST.getlist("seats")
        error_seats = []

        if not selected_seats:
            return render(request, "movies/seat_selection.html", {
                "theater": theater,
                "seats": seats,
                "error": "No seat selected"
            })

        for seat_id in selected_seats:
            seat = get_object_or_404(Seat, id=seat_id, theater=theater)

            if seat.is_booked:
                error_seats.append(seat.seat_number)
                continue

            try:
                Booking.objects.create(
                    user=request.user,
                    seat=seat,
                    movie=theater.movie,
                    theater=theater
                )

                seat.is_booked = True
                seat.save()

            except IntegrityError:
                error_seats.append(seat.seat_number)

        if error_seats:
            error_message = f"The following seats are already booked: {', '.join(error_seats)}"

            return render(request, "movies/seat_selection.html", {
                "theater": theater,
                "seats": seats,
                "error": error_message
            })

        return redirect("profile")

    return render(request, "movies/seat_selection.html", {
        "theater": theater,
        "seats": seats
    })
def movie_detail_api(request, movie_id):
    movie = get_object_or_404(Movie, id=movie_id)

    trailer_embed_url = get_youtube_embed_url(movie.trailer_url)

    return JsonResponse({
        "id": movie.id,
        "name": movie.name,
        "image": movie.image.url if movie.image else None,
        "image_url": movie.image_url,
        "rating": str(movie.rating),
        "cast": movie.cast,
        "description": movie.description,
        "trailer_url": movie.trailer_url,
        "trailer_embed_url": trailer_embed_url,
    })
# Adding the react ui i made here using api
def movie_to_json(movie):
    return {
        "id": movie.id,
        "name": movie.name,
        "image": movie.image.url if movie.image else "",
        "image_url": movie.image_url,
        "rating": str(movie.rating),
        "cast": movie.cast,
        "description": movie.description,
        "trailer_url": movie.trailer_url,
        "trailer_embed_url": get_youtube_embed_url(movie.trailer_url),
        "genres": [
            {"id": genre.id, "name": genre.name, "slug": genre.slug}
            for genre in movie.genres.all()
        ],
        "language": {
            "id": movie.language.id,
            "name": movie.language.name,
            "slug": movie.language.slug,
        } if movie.language else None,
    }


def build_movie_queryset(request, exclude_filter=None):
    search = request.GET.get("search", "").strip()
    genre_slugs = request.GET.getlist("genre")
    language_slugs = request.GET.getlist("language")

    movies = (
        Movie.objects
        .select_related("language")
        .prefetch_related("genres")
        .all()
    )

    if search:
        movies = movies.filter(
            Q(name__icontains=search) |
            Q(cast__icontains=search) |
            Q(description__icontains=search)
        )

    if genre_slugs and exclude_filter != "genre":
        movies = movies.filter(genres__slug__in=genre_slugs)

    if language_slugs and exclude_filter != "language":
        movies = movies.filter(language__slug__in=language_slugs)

    return movies.distinct()


def api_movie_list(request):
    sort = request.GET.get("sort", "name")

    allowed_sorting = {
        "name": "name",
        "-name": "-name",
        "rating": "rating",
        "-rating": "-rating",
        "newest": "-id",
        "oldest": "id",
    }

    sort_field = allowed_sorting.get(sort, "name")

    try:
        page_number = int(request.GET.get("page", 1))
    except ValueError:
        page_number = 1

    try:
        page_size = int(request.GET.get("page_size", 12))
    except ValueError:
        page_size = 12

    page_size = min(page_size, 48)

    movies = build_movie_queryset(request).order_by(sort_field)

    paginator = Paginator(movies, page_size)

    try:
        page_obj = paginator.page(page_number)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)

    genre_count_queryset = build_movie_queryset(request, exclude_filter="genre")
    language_count_queryset = build_movie_queryset(request, exclude_filter="language")

    genre_counts = list(
        Genre.objects
        .filter(movies__in=genre_count_queryset)
        .annotate(count=Count("movies", distinct=True))
        .values("id", "name", "slug", "count")
        .order_by("name")
    )

    language_counts = list(
        Language.objects
        .filter(movies__in=language_count_queryset)
        .annotate(count=Count("movies", distinct=True))
        .values("id", "name", "slug", "count")
        .order_by("name")
    )

    return JsonResponse({
        "results": [movie_to_json(movie) for movie in page_obj.object_list],
        "pagination": {
            "page": page_obj.number,
            "page_size": page_size,
            "total_pages": paginator.num_pages,
            "total_results": paginator.count,
            "has_next": page_obj.has_next(),
            "has_previous": page_obj.has_previous(),
        },
        "filters": {
            "genres": genre_counts,
            "languages": language_counts,
        },
        "sorting": {
            "current": sort,
            "allowed": list(allowed_sorting.keys()),
        },
    })

def api_movie_detail(request, movie_id):
    movie = get_object_or_404(Movie, id=movie_id)
    return JsonResponse(movie_to_json(movie))


def api_theater_list(request):
    movie_id = request.GET.get("movie")
    theaters = Theater.objects.all()

    if movie_id:
        theaters = theaters.filter(movie_id=movie_id)

    data = [
        {
            "id": theater.id,
            "name": theater.name,
            "movie": theater.movie.id,
            "movie_name": theater.movie.name,
            "time": str(theater.time),
        }
        for theater in theaters
    ]

    return JsonResponse(data, safe=False)


def api_theater_detail(request, theater_id):
    theater = get_object_or_404(Theater, id=theater_id)

    return JsonResponse({
        "id": theater.id,
        "name": theater.name,
        "movie": theater.movie.id,
        "movie_name": theater.movie.name,
        "time": str(theater.time),
    })


def api_seat_list(request):
    theater_id = request.GET.get("theater")
    seats = Seat.objects.all()
    now = timezone.now()

    if theater_id:
        seats = seats.filter(theater_id=theater_id)

    data = [
        {
            "id": seat.id,
            "theater": seat.theater.id,
            "seat_number": seat.seat_number,
            "is_booked": seat.is_booked,
            "is_locked": bool(
                seat.locked_until
                and seat.locked_until > now
                and not seat.is_booked
            ),
            "locked_by_me": bool(
                request.user.is_authenticated
                and seat.locked_by == request.user
                and seat.locked_until
                and seat.locked_until > now
            ),
           "locked_until": seat.locked_until.isoformat() if seat.locked_until and not seat.is_booked else None,
        }
        for seat in seats
    ]

    return JsonResponse(data, safe=False)


@login_required(login_url="/login/")
def api_create_booking(request):
    if request.method != "POST":
        return JsonResponse({"error": "Only POST request allowed"}, status=405)

    body = json.loads(request.body)
    theater_id = body.get("theater")
    selected_seats = body.get("seats", [])

    theater = get_object_or_404(Theater, id=theater_id)
    booked = []

    for seat_id in selected_seats:
        seat = get_object_or_404(Seat, id=seat_id, theater=theater)

        if seat.is_booked:
            return JsonResponse({
                "error": f"Seat {seat.seat_number} is already booked"
            }, status=400)

        Booking.objects.create(
            user=request.user,
            seat=seat,
            movie=theater.movie,
            theater=theater
        )

        seat.is_booked = True
        seat.save()
        booked.append(seat.seat_number)

    return JsonResponse({
        "status": "Confirmed",
        "movie": theater.movie.name,
        "theater": theater.name,
        "seats": booked,
    })
from django.views.decorators.csrf import csrf_exempt

@csrf_exempt
@login_required(login_url="/login/")
def lock_seats(request):

    print("LOCK SEATS VIEW CALLED")

    if request.method != "POST":
        return JsonResponse(
            {"error": "Only POST request allowed"},
            status=405
        )

    try:
        body = json.loads(request.body)
    except:
        return JsonResponse(
            {"error": "Invalid JSON"},
            status=400
        )

    seat_ids = body.get("seats", [])

    if not seat_ids:
        return JsonResponse(
            {"error": "No seats selected"},
            status=400
        )

    now = timezone.now()
    lock_expiry = now + timedelta(minutes=2)

    with transaction.atomic():

        seats = Seat.objects.select_for_update().filter(
            id__in=seat_ids
        )

        for seat in seats:

            if seat.is_booked:
                return JsonResponse(
                    {"error": f"Seat {seat.seat_number} already booked"},
                    status=409
                )

            if (
                seat.locked_until
                and seat.locked_until > now
                and seat.locked_by != request.user
            ):
                return JsonResponse(
                    {"error": f"Seat {seat.seat_number} already locked"},
                    status=409
                )

        for seat in seats:
            seat.locked_by = request.user
            seat.locked_until = lock_expiry
            seat.save()

    return JsonResponse({
        "message": "Seats locked",
        "locked_until": lock_expiry.isoformat()
    })


@csrf_exempt
@login_required(login_url="/login/")
def confirm_booking(request):

    print("CONFIRM BOOKING VIEW CALLED")

    if request.method != "POST":
        return JsonResponse(
            {"error": "Only POST request allowed"},
            status=405
        )

    try:
        body = json.loads(request.body)
    except:
        return JsonResponse(
            {"error": "Invalid JSON"},
            status=400
        )

    theater_id = body.get("theater")
    seat_ids = body.get("seats", [])
    razorpay_order_id = body.get("order_id")
    razorpay_payment_id = body.get("payment_id")

    print("ORDER ID:", razorpay_order_id)
    print("PAYMENT ID:", razorpay_payment_id)
    print("SEAT IDS:", seat_ids)

    if not razorpay_order_id or not razorpay_payment_id:
        return JsonResponse(
            {"error": "Payment verification required before booking"},
            status=400
        )

    theater = get_object_or_404(Theater, id=theater_id)
    now = timezone.now()

    print("THEATER FOUND")

    payment = get_object_or_404(
        Payment,
        razorpay_order_id=razorpay_order_id,
        razorpay_payment_id=razorpay_payment_id,
        user=request.user,
        status="paid"
    )

    print("PAYMENT FOUND")

    with transaction.atomic():

        seats = Seat.objects.select_for_update().filter(
            id__in=seat_ids,
            theater=theater
        )

        print("SEATS FOUND:", seats.count())

        if seats.count() != len(seat_ids):
            print("INVALID SEAT COUNT")
            return JsonResponse(
                {"error": "Invalid seats selected"},
                status=400
            )

        booked = []

        for seat in seats:
            print("CHECKING SEAT:", seat.seat_number)

            if seat.is_booked:
                print("ALREADY BOOKED")
                return JsonResponse(
                    {"error": f"Seat {seat.seat_number} already booked"},
                    status=409
                )

            if seat.locked_by != request.user:
                print("LOCKED BY SOMEONE ELSE")
                return JsonResponse(
                    {"error": "Seat not reserved by you"},
                    status=403
                )

            if not seat.locked_until or seat.locked_until < now:
                print("LOCK EXPIRED")
                return JsonResponse(
                    {"error": "Reservation expired"},
                    status=409
                )

        print("STARTING BOOKING CREATION")

        for seat in seats:
            print("CREATING BOOKING:", seat.seat_number)

            Booking.objects.create(
                user=request.user,
                seat=seat,
                movie=theater.movie,
                theater=theater
            )

            seat.is_booked = True
            seat.locked_by = None
            seat.locked_until = None
            seat.save()

            booked.append(seat.seat_number)

        print("BOOKINGS CREATED")

        recipient_email = body.get("contact") or request.user.email

        print("RECIPIENT:", recipient_email)

        email_status = "failed"

        if recipient_email and "@" in recipient_email:
            try:
                print("CALLING send_booking_confirmation()")

                send_booking_confirmation(
                    payment=payment,
                    recipient_email=recipient_email,
                )

                print("EMAIL SENT SUCCESSFULLY")

                email_status = "sent"

            except Exception as e:
                print("=" * 60)
                print("BOOKING EMAIL FAILED")
                print(e)
                print("=" * 60)

    print("RETURNING SUCCESS RESPONSE")

    return JsonResponse({
        "id": f"BMS-{payment.id}",
        "status": "Confirmed",
        "movie": theater.movie.name,
        "theater": theater.name,
        "seats": booked,
        "payment_id": razorpay_payment_id,
        "order_id": razorpay_order_id,
        "email_status": email_status,
    })

@csrf_exempt
@login_required(login_url="/login/")
def create_payment_order(request):
    if request.method != "POST":
        return JsonResponse({"error": "Only POST request allowed"}, status=405)

    try:
        body = json.loads(request.body)
    except:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    theater_id = body.get("theater")
    seat_ids = body.get("seats", [])
    amount = body.get("amount")

    if not theater_id or not seat_ids or not amount:
        return JsonResponse(
            {"error": "Theater, seats and amount are required"},
            status=400
        )

    theater = get_object_or_404(Theater, id=theater_id)
    now = timezone.now()

    idempotency_source = f"{request.user.id}-{theater_id}-{sorted(seat_ids)}-{amount}"
    idempotency_key = hashlib.sha256(idempotency_source.encode()).hexdigest()

    existing_payment = Payment.objects.filter(
        idempotency_key=idempotency_key,
        status__in=["created", "paid"]
    ).first()

    if existing_payment:
        return JsonResponse({
            "key": "SIMULATED_KEY",
            "order_id": existing_payment.razorpay_order_id,
            "amount": existing_payment.amount,
            "currency": "INR",
            "status": existing_payment.status,
            "expires_at": existing_payment.expires_at.isoformat() if existing_payment.expires_at else None,
            "simulated": True,
        })

    with transaction.atomic():
        seats = Seat.objects.select_for_update().filter(
            id__in=seat_ids,
            theater=theater
        )

        if seats.count() != len(seat_ids):
            return JsonResponse({"error": "Invalid seat selected"}, status=400)

        for seat in seats:
            if seat.is_booked:
                return JsonResponse(
                    {"error": f"Seat {seat.seat_number} already booked"},
                    status=409
                )

            if seat.locked_by != request.user:
                return JsonResponse(
                    {"error": f"Seat {seat.seat_number} is not locked by you"},
                    status=403
                )

            if not seat.locked_until or seat.locked_until < now:
                return JsonResponse({"error": "Seat reservation expired"}, status=409)

        amount_in_paise = int(float(amount) * 100)
        simulated_order_id = f"order_sim_{uuid.uuid4().hex[:12]}"

        payment = Payment.objects.create(
            user=request.user,
            theater=theater,
            razorpay_order_id=simulated_order_id,
            amount=amount_in_paise,
            status="created",
            idempotency_key=idempotency_key,
            expires_at=now + timedelta(minutes=10),
        )

        payment.seats.set(seats)

    return JsonResponse({
        "key": "SIMULATED_KEY",
        "order_id": simulated_order_id,
        "amount": amount_in_paise,
        "currency": "INR",
        "status": "created",
        "expires_at": payment.expires_at.isoformat(),
        "simulated": True,
    })


@csrf_exempt
@login_required(login_url="/login/")
def verify_payment(request):
    if request.method != "POST":
        return JsonResponse({"error": "Only POST request allowed"}, status=405)

    try:
        body = json.loads(request.body)
    except:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    razorpay_order_id = body.get("razorpay_order_id")
    razorpay_payment_id = body.get("razorpay_payment_id")
    razorpay_signature = body.get("razorpay_signature")

    if not razorpay_order_id:
        return JsonResponse({"error": "Order ID missing"}, status=400)

    with transaction.atomic():
        payment = get_object_or_404(
            Payment.objects.select_for_update(),
            razorpay_order_id=razorpay_order_id,
            user=request.user,
        )

        # -----------------------------
        # IDEMPOTENCY
        # -----------------------------
        if payment.status == "paid":
            return JsonResponse({
                "status": "already_verified",
                "message": "Duplicate verification ignored",
                "razorpay_order_id": payment.razorpay_order_id,
                "razorpay_payment_id": payment.razorpay_payment_id,
                "razorpay_signature": payment.razorpay_signature,
            })

        now = timezone.now()

        if payment.status == "expired" or (
            payment.expires_at and payment.expires_at < now
        ):
            payment.status = "expired"
            payment.failure_reason = "Payment timeout before verification"
            payment.save(update_fields=[
                "status",
                "failure_reason",
                "updated_at",
            ])

            

            return JsonResponse({
                "error": "Payment expired. Please lock seats again and retry."
            }, status=409)

        if payment.status in ["failed", "cancelled"]:
            return JsonResponse({
                "error": f"Payment already {payment.status}"
            }, status=409)

        simulated_payment_id = (
            razorpay_payment_id
            or f"pay_sim_{uuid.uuid4().hex[:12]}"
        )

        expected_signature = hmac.new(
            settings.SECRET_KEY.encode(),
            f"{razorpay_order_id}|{simulated_payment_id}".encode(),
            hashlib.sha256,
        ).hexdigest()

        if razorpay_signature and razorpay_signature != expected_signature:
            payment.status = "failed"
            payment.failure_reason = "Invalid simulated payment signature"

            payment.save(update_fields=[
                "status",
                "failure_reason",
                "updated_at",
            ])

            

            return JsonResponse(
                {"error": "Invalid simulated signature"},
                status=400,
            )

        payment.razorpay_payment_id = simulated_payment_id
        payment.razorpay_signature = expected_signature
        payment.status = "paid"

        payment.save(update_fields=[
            "razorpay_payment_id",
            "razorpay_signature",
            "status",
            "updated_at",
        ])

    return JsonResponse({
        "status": "verified",
        "message": "Simulated payment verified successfully",
        "razorpay_order_id": payment.razorpay_order_id,
        "razorpay_payment_id": payment.razorpay_payment_id,
        "razorpay_signature": payment.razorpay_signature,
    })


@csrf_exempt
def razorpay_webhook(request):
    if request.method != "POST":
        return JsonResponse({"error": "Only POST request allowed"}, status=405)

    webhook_signature = request.headers.get("X-Razorpay-Signature", "")
    body = request.body

    expected_signature = hmac.new(
        settings.SECRET_KEY.encode(),
        body,
        hashlib.sha256
    ).hexdigest()

    if webhook_signature and webhook_signature != expected_signature:
        return JsonResponse({"error": "Invalid webhook signature"}, status=400)

    try:
        event_data = json.loads(body)
    except:
        return JsonResponse({"error": "Invalid webhook payload"}, status=400)

    event_id = event_data.get("event_id")
    event_type = event_data.get("event")
    razorpay_order_id = event_data.get("order_id")
    razorpay_payment_id = event_data.get("payment_id")

    if not razorpay_order_id:
        return JsonResponse({"status": "ignored"})

    with transaction.atomic():
        payment = Payment.objects.select_for_update().filter(
            razorpay_order_id=razorpay_order_id
        ).first()

        if not payment:
            return JsonResponse({"status": "payment_not_found"})

        if event_id:
            try:
                PaymentWebhookEvent.objects.create(
                    event_id=event_id,
                    payment=payment,
                    event_type=event_type or "unknown"
                )
            except IntegrityError:
                return JsonResponse({
                    "status": "duplicate_webhook_ignored"
                })

        if event_type == "payment.captured":
            if payment.status != "paid":
                payment.status = "paid"
                payment.razorpay_payment_id = razorpay_payment_id
                payment.failure_reason = None
                payment.cancel_reason = None

        elif event_type == "payment.failed":
            payment.status = "failed"
            payment.failure_reason = event_data.get(
                "failure_reason",
                "Payment failed"
            )

            payment.seats.select_for_update().filter(
                is_booked=False,
                locked_by=payment.user
            ).update(
                locked_by=None,
                locked_until=None
            )

        elif event_type == "payment.cancelled":
            payment.status = "cancelled"
            payment.cancel_reason = event_data.get(
                "cancel_reason",
                "Cancelled by user"
            )

            payment.seats.select_for_update().filter(
                is_booked=False,
                locked_by=payment.user
            ).update(
                locked_by=None,
                locked_until=None
            )

        elif event_type == "payment.expired":
            payment.status = "expired"
            payment.failure_reason = "Payment expired before completion"

            payment.seats.select_for_update().filter(
                is_booked=False,
                locked_by=payment.user
            ).update(
                locked_by=None,
                locked_until=None
            )

        else:
            return JsonResponse({"status": "unknown_event_ignored"})

        payment.save()

    return JsonResponse({"status": "webhook_processed"})

def is_admin_user(user):
    return user.is_authenticated and user.is_staff


@user_passes_test(is_admin_user, login_url="/admin/")
def admin_analytics_api(request):
    cache_key = "admin_analytics_dashboard_v1"
    cached_data = cache.get(cache_key)

    if cached_data:
        return JsonResponse(cached_data)
    paid_payments = Payment.objects.filter(status="paid")

    daily_revenue = list(
        paid_payments
        .annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(total_revenue=Sum("amount"))
        .order_by("-day")[:7]
    )

    weekly_revenue = list(
        paid_payments
        .annotate(week=TruncWeek("created_at"))
        .values("week")
        .annotate(total_revenue=Sum("amount"))
        .order_by("-week")[:4]
    )

    monthly_revenue = list(
        paid_payments
        .annotate(month=TruncMonth("created_at"))
        .values("month")
        .annotate(total_revenue=Sum("amount"))
        .order_by("-month")[:6]
    )

    popular_movies = list(
        Movie.objects
        .annotate(total_bookings=Count("booking"))
        .filter(total_bookings__gt=0)
        .values("id", "name", "total_bookings")
        .order_by("-total_bookings")[:5]
    )

    busiest_theaters = list(
    Theater.objects
    .annotate(
        total_seats=Count("seats"),
        booked_seats=Count("seats", filter=Q(seats__is_booked=True)),
    )
        .annotate(
            occupancy_rate=ExpressionWrapper(
                F("booked_seats") * 100.0 / F("total_seats"),
                output_field=FloatField()
            )
        )
        .filter(total_seats__gt=0)
        .values("id", "name", "movie__name", "booked_seats", "total_seats", "occupancy_rate")
        .order_by("-occupancy_rate")[:5]
    )

    peak_booking_hours = list(
        Booking.objects
        .annotate(hour=ExtractHour("booked_at"))
        .values("hour")
        .annotate(total_bookings=Count("id"))
        .order_by("-total_bookings")[:5]
    )

    total_payments = Payment.objects.count()
    cancelled_payments = Payment.objects.filter(
        status__in=["failed", "cancelled", "expired"]
    ).count()

    cancellation_rate = 0
    if total_payments > 0:
        cancellation_rate = round((cancelled_payments / total_payments) * 100, 2)

    data = {
        "revenue": {
            "daily": daily_revenue,
            "weekly": weekly_revenue,
            "monthly": monthly_revenue,
        },
        "popular_movies": popular_movies,
        "busiest_theaters": busiest_theaters,
        "peak_booking_hours": peak_booking_hours,
        "cancellation_rate": cancellation_rate,
        "total_bookings": Booking.objects.count(),
        "total_paid_revenue": paid_payments.aggregate(total=Sum("amount"))["total"] or 0,
    }

    cache.set(cache_key, data, timeout=60)

    return JsonResponse(data)
from django.http import JsonResponse
from django.conf import settings

def debug_view(request):
    return JsonResponse({
        "DEBUG": settings.DEBUG,
        "MEDIA_URL": settings.MEDIA_URL,
        "MEDIA_ROOT": str(settings.MEDIA_ROOT),
    })

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse

@login_required
def my_bookings(request):
    bookings = (
        Booking.objects
        .filter(user=request.user)
        .select_related("movie", "theater", "seat")
        .order_by("-booked_at")
    )

    data = []

    for booking in bookings:
        data.append({
            "id": booking.id,
            "movie": {
                "id": booking.movie.id,
                "name": booking.movie.name,
            },
            "theater": {
                "id": booking.theater.id,
                "name": booking.theater.name,
            },
            "selectedSeats": [
                {
                    "seat_number": booking.seat.seat_number
                }
            ],
            "total": 250,
            "status": "Confirmed",
            "booked_at": booking.booked_at.isoformat(),
        })

    return JsonResponse(data, safe=False)