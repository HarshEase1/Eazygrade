import hashlib
import random

from django.conf import settings
from django.core import signing
from django.core.mail import send_mail
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from vendors.models import VendorCourse, VendorInstitute
from vendors.serializers import VendorCourseSerializer, VendorInstituteSerializer
from vendors.services import deepseek_course_analysis, rank_candidates_for_course


PUBLIC_EMAIL_DOMAINS = {
    "gmail.com",
    "googlemail.com",
    "yahoo.com",
    "yahoo.co.in",
    "outlook.com",
    "hotmail.com",
    "live.com",
    "icloud.com",
    "aol.com",
    "proton.me",
    "protonmail.com",
    "rediffmail.com",
    "zoho.com",
    "mail.com",
}

OTP_SALT = "vendors.email-otp"
OTP_MAX_AGE_SECONDS = 10 * 60


def normalise_email(value):
    return str(value or "").strip().lower()


def email_domain(email):
    return email.rsplit("@", 1)[-1] if "@" in email else ""


def is_vendor_email(email):
    domain = email_domain(email)
    return "@" in email and "." in domain and domain not in PUBLIC_EMAIL_DOMAINS


def otp_digest(email, otp):
    value = f"{email}:{otp}:{settings.SECRET_KEY}".encode("utf-8")
    return hashlib.sha256(value).hexdigest()


def is_demo_vendor_email(email):
    return email == getattr(settings, "DEMO_VENDOR_EMAIL", "admissions@demo-eazygrade.edu")


@api_view(["POST"])
@permission_classes([AllowAny])
def send_vendor_otp(request):
    email = normalise_email(request.data.get("email"))

    if not is_vendor_email(email):
        return Response(
            {"detail": "Use an official institute email address."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if is_demo_vendor_email(email):
        vendor = VendorInstitute.objects.filter(official_email=email).first()

        if vendor is None:
            return Response(
                {
                    "detail": "Demo vendor account is not ready. Run generate_vendor_demo_data first.",
                    "demo_login": True,
                    "email": email,
                    "has_profile": False,
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(
            {
                "detail": "Demo vendor login ready.",
                "demo_login": True,
                "email": email,
                "has_profile": True,
                "vendor": VendorInstituteSerializer(vendor).data,
            }
        )

    if not settings.EMAIL_HOST_USER or not settings.EMAIL_HOST_PASSWORD:
        return Response(
            {
                "detail": "Email is not configured yet. Add EMAIL_HOST_USER and EMAIL_HOST_PASSWORD, then try again."
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    otp = str(random.SystemRandom().randint(100000, 999999))
    token = signing.dumps(
        {
            "email": email,
            "otp": otp_digest(email, otp),
            "created_at": timezone.now().isoformat(),
        },
        salt=OTP_SALT,
    )

    send_mail(
        "Your EazyGrade vendor login code",
        f"Your EazyGrade vendor login code is {otp}. It expires in 10 minutes.",
        settings.DEFAULT_FROM_EMAIL,
        [email],
        fail_silently=False,
    )

    return Response({"detail": "Code sent to your official email.", "otp_token": token})


@api_view(["POST"])
@permission_classes([AllowAny])
def verify_vendor_otp(request):
    email = normalise_email(request.data.get("email"))
    otp = str(request.data.get("otp") or "").strip()
    token = str(request.data.get("otp_token") or "").strip()

    if not email or not otp or not token:
        return Response(
            {"detail": "Email, code, and verification token are required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        payload = signing.loads(token, salt=OTP_SALT, max_age=OTP_MAX_AGE_SECONDS)
    except signing.BadSignature:
        return Response(
            {"detail": "The code has expired. Please request a new code."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if payload.get("email") != email or payload.get("otp") != otp_digest(email, otp):
        return Response(
            {"detail": "The code does not match. Please try again."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    vendor = VendorInstitute.objects.filter(official_email=email).first()

    return Response(
        {
            "detail": "Email confirmed.",
            "email": email,
            "has_profile": vendor is not None,
            "vendor": VendorInstituteSerializer(vendor).data if vendor else None,
        }
    )


@api_view(["GET", "POST"])
@permission_classes([AllowAny])
def save_vendor_profile(request):
    if request.method == "GET":
        email = normalise_email(request.query_params.get("email"))

        if not is_vendor_email(email):
            return Response(
                {"detail": "Vendor email is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            vendor = VendorInstitute.objects.get(official_email=email)
        except VendorInstitute.DoesNotExist:
            return Response(
                {"detail": "Vendor profile has not been created yet."},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response({"vendor": VendorInstituteSerializer(vendor).data})

    email = normalise_email(request.data.get("email"))
    profile = request.data.get("profile") or {}
    courses = request.data.get("courses") or []

    if not is_vendor_email(email):
        return Response(
            {"detail": "Use an official institute email address."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    required_profile_fields = ["name", "providerType", "city", "state", "description"]
    missing_profile_fields = [
        field for field in required_profile_fields if not str(profile.get(field, "")).strip()
    ]

    if missing_profile_fields:
        return Response(
            {"detail": "Complete the institute profile before saving."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not isinstance(courses, list) or not courses:
        return Response(
            {"detail": "Add at least one course before saving."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    valid_courses = []

    for course in courses:
        if not isinstance(course, dict):
            continue

        if not all(str(course.get(field, "")).strip() for field in ["title", "subjects", "syllabus"]):
            continue

        valid_courses.append(course)

    if not valid_courses:
        return Response(
            {"detail": "Each saved course needs a name, subjects, and syllabus."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    vendor, _ = VendorInstitute.objects.update_or_create(
        official_email=email,
        defaults={
            "is_email_verified": bool(request.data.get("is_email_verified", False)),
            "name": str(profile.get("name", "")).strip(),
            "provider_type": str(profile.get("providerType", "")).strip(),
            "website": str(profile.get("website", "")).strip(),
            "city": str(profile.get("city", "")).strip(),
            "state": str(profile.get("state", "")).strip(),
            "contact_name": str(profile.get("contactName", "")).strip(),
            "contact_phone": str(profile.get("contactPhone", "")).strip(),
            "description": str(profile.get("description", "")).strip(),
            "image_url": str(profile.get("imageUrl", "")).strip(),
        },
    )

    vendor.courses.all().delete()

    for course in valid_courses:
        VendorCourse.objects.create(
            vendor=vendor,
            title=str(course.get("title", "")).strip(),
            level=str(course.get("level", "")).strip(),
            mode=str(course.get("mode", "")).strip(),
            duration=str(course.get("duration", "")).strip(),
            subjects=str(course.get("subjects", "")).strip(),
            seats=str(course.get("seats", "")).strip(),
            fees=str(course.get("fees", "")).strip(),
            syllabus=str(course.get("syllabus", "")).strip(),
            ideal_student=str(course.get("idealStudent", "")).strip(),
        )

    return Response(
        {
            "detail": "Vendor profile saved.",
            "vendor": VendorInstituteSerializer(vendor).data,
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(["POST"])
@permission_classes([AllowAny])
def create_vendor_course(request):
    email = normalise_email(request.data.get("email"))
    course = request.data.get("course") or {}

    if not is_vendor_email(email):
        return Response(
            {"detail": "Vendor login is required."},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    try:
        vendor = VendorInstitute.objects.get(official_email=email)
    except VendorInstitute.DoesNotExist:
        return Response(
            {"detail": "Complete vendor profile before adding courses."},
            status=status.HTTP_404_NOT_FOUND,
        )

    if not all(str(course.get(field, "")).strip() for field in ["title", "subjects", "syllabus"]):
        return Response(
            {"detail": "Course name, subjects, and syllabus are required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    saved_course = VendorCourse.objects.create(
        vendor=vendor,
        title=str(course.get("title", "")).strip(),
        level=str(course.get("level", "")).strip() or "Postgraduate",
        mode=str(course.get("mode", "")).strip() or "Online",
        duration=str(course.get("duration", "")).strip(),
        subjects=str(course.get("subjects", "")).strip(),
        seats=str(course.get("seats", "")).strip(),
        fees=str(course.get("fees", "")).strip(),
        syllabus=str(course.get("syllabus", "")).strip(),
        ideal_student=str(course.get("idealStudent", "")).strip(),
    )

    return Response(
        {
            "detail": "Course added.",
            "course": VendorCourseSerializer(saved_course).data,
            "vendor": VendorInstituteSerializer(vendor).data,
        },
        status=status.HTTP_201_CREATED,
    )


def vendor_from_email(email):
    if not is_vendor_email(email):
        return None

    return VendorInstitute.objects.filter(official_email=email).first()


def course_payload_from_request(request):
    return request.data.get("course") or request.data


@api_view(["GET", "PATCH", "DELETE"])
@permission_classes([AllowAny])
def vendor_course_detail(request, course_id):
    email = normalise_email(request.data.get("email") or request.query_params.get("email"))
    vendor = vendor_from_email(email)

    if vendor is None:
        return Response(
            {"detail": "Vendor login is required."},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    try:
        course = vendor.courses.get(id=course_id)
    except VendorCourse.DoesNotExist:
        return Response(
            {"detail": "Course not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    if request.method == "GET":
        return Response({"course": VendorCourseSerializer(course).data})

    if request.method == "DELETE":
        course.delete()
        return Response({"detail": "Course deleted."})

    payload = course_payload_from_request(request)

    for field, default in [
        ("title", course.title),
        ("level", course.level),
        ("mode", course.mode),
        ("duration", course.duration),
        ("subjects", course.subjects),
        ("seats", course.seats),
        ("fees", course.fees),
        ("syllabus", course.syllabus),
        ("ideal_student", course.ideal_student),
    ]:
        setattr(course, field, str(payload.get(field, default) or "").strip())

    if not course.title or not course.subjects or not course.syllabus:
        return Response(
            {"detail": "Course name, subjects, and syllabus are required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    course.save()
    return Response({"detail": "Course updated.", "course": VendorCourseSerializer(course).data})


@api_view(["GET"])
@permission_classes([AllowAny])
def vendor_course_matches(request, course_id):
    email = normalise_email(request.query_params.get("email"))
    vendor = vendor_from_email(email)

    if vendor is None:
        return Response(
            {"detail": "Vendor login is required."},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    try:
        course = vendor.courses.get(id=course_id)
    except VendorCourse.DoesNotExist:
        return Response(
            {"detail": "Course not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    matches = rank_candidates_for_course(course)
    analysis = deepseek_course_analysis(course, matches)

    return Response(
        {
            "course": VendorCourseSerializer(course).data,
            "matches": matches,
            "analysis": analysis,
        }
    )
