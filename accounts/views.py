import base64
import binascii

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.parsers import FormParser, MultiPartParser
from accounts.models import (
    CandidateAcademicRecord,
    CandidateDocument,
    CandidateEntranceExamScore,
    CandidateProfile,
    CandidateSubjectScore,
    CandidateWorkExperience,
)
from accounts.serializers import (
    CandidateAcademicRecordSerializer,
    CandidateDocumentSerializer,
    CandidateEntranceExamScoreSerializer,
    CandidateProfileSerializer,
    CandidateSubjectScoreSerializer,
    CandidateWorkExperienceSerializer,
)
from django.db import transaction

ACCESS_COOKIE_NAME = "eazygrade_access"
REFRESH_COOKIE_NAME = "eazygrade_refresh"


def get_default_academic_level(profile):
    if profile.current_education_status in [
        "class_10",
        "class_11",
        "class_12",
        "class_12_passed",
    ]:
        return "class_12"

    if profile.current_education_status == "diploma":
        return "diploma"

    if profile.current_education_status in ["ug"]:
        return "ug"

    if profile.current_education_status in ["graduate", "working"]:
        return "ug"

    return "class_12"

def set_auth_cookies(response, refresh):
    access_token = refresh.access_token
    secure = settings.AUTH_COOKIE_SECURE
    same_site = settings.AUTH_COOKIE_SAMESITE

    response.set_cookie(
        ACCESS_COOKIE_NAME,
        str(access_token),
        max_age=int(settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"].total_seconds()),
        httponly=True,
        secure=secure,
        samesite=same_site,
        path="/",
    )
    response.set_cookie(
        REFRESH_COOKIE_NAME,
        str(refresh),
        max_age=int(settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds()),
        httponly=True,
        secure=secure,
        samesite=same_site,
        path="/",
    )


def delete_auth_cookies(response):
    response.delete_cookie(ACCESS_COOKIE_NAME, path="/", samesite=settings.AUTH_COOKIE_SAMESITE)
    response.delete_cookie(REFRESH_COOKIE_NAME, path="/", samesite=settings.AUTH_COOKIE_SAMESITE)


def serialize_user(user):
    return {
        "id": user.id,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "name": user.get_full_name() or user.email,
    }


@api_view(["POST"])
@permission_classes([AllowAny])
def google_login(request):
    credential = request.data.get("credential", "").strip()
    client_id = settings.GOOGLE_OAUTH_CLIENT_ID

    if not client_id:
        return Response(
            {"detail": "GOOGLE_OAUTH_CLIENT_ID is not configured."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    if not credential:
        return Response(
            {"detail": "Google credential is required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        google_user = id_token.verify_oauth2_token(
            credential,
            google_requests.Request(),
            client_id,
        )
    except ValueError:
        return Response(
            {"detail": "Invalid Google credential."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    email = google_user.get("email", "").strip().lower()

    if not email:
        return Response(
            {"detail": "Google account did not return an email."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not google_user.get("email_verified", False):
        return Response(
            {"detail": "Google email is not verified."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    User = get_user_model()
    first_name = google_user.get("given_name", "")
    last_name = google_user.get("family_name", "")
    username = email

    user, created = User.objects.get_or_create(
        email=email,
        defaults={
            "username": username,
            "first_name": first_name,
            "last_name": last_name,
        },
    )

    updates = {}

    if first_name and user.first_name != first_name:
        updates["first_name"] = first_name

    if last_name and user.last_name != last_name:
        updates["last_name"] = last_name

    if not user.username:
        updates["username"] = username

    if updates:
        for field, value in updates.items():
            setattr(user, field, value)
        user.save(update_fields=list(updates.keys()))

    refresh = RefreshToken.for_user(user)

    profile = get_or_create_candidate_profile(user)
    recalculated_completion = profile.calculate_completion()
    recalculated_onboarding_completed = (
        recalculated_completion >= 100 and profile.has_required_documents()
    )

    if (
        profile.profile_completion_percentage != recalculated_completion
        or profile.is_onboarding_completed != recalculated_onboarding_completed
    ):
        profile.save(
            update_fields=[
                "profile_completion_percentage",
                "is_onboarding_completed",
                "updated_at",
            ]
        )

    next_path = "/" if profile.is_onboarding_completed else "/onboarding"

    response = Response(
        {
            "is_new_user": created,
            "user": serialize_user(user),
            "next": next_path,
        }
    )
    set_auth_cookies(response, refresh)

    return response


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def me(request):
    return Response({"user": serialize_user(request.user)})


@api_view(["POST"])
@permission_classes([AllowAny])
def refresh_session(request):
    raw_refresh = request.COOKIES.get(REFRESH_COOKIE_NAME, "")

    if not raw_refresh:
        return Response(
            {"detail": "Refresh token is missing."},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    try:
        old_refresh = RefreshToken(raw_refresh)
        old_refresh.blacklist()
        user_id = old_refresh.get("user_id")
        User = get_user_model()
        user = User.objects.get(id=user_id)
        new_refresh = RefreshToken.for_user(user)
    except (TokenError, get_user_model().DoesNotExist):
        response = Response(
            {"detail": "Refresh token is invalid."},
            status=status.HTTP_401_UNAUTHORIZED,
        )
        delete_auth_cookies(response)
        return response

    response = Response({"detail": "Session refreshed."})
    set_auth_cookies(response, new_refresh)
    return response


@api_view(["POST"])
@permission_classes([AllowAny])
def logout(request):
    raw_refresh = request.COOKIES.get(REFRESH_COOKIE_NAME, "")

    if raw_refresh:
        try:
            RefreshToken(raw_refresh).blacklist()
        except TokenError:
            pass

    response = Response({"detail": "Logged out."})
    delete_auth_cookies(response)
    return response


def get_or_create_candidate_profile(user):
    profile, _ = CandidateProfile.objects.get_or_create(user=user)
    return profile


@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated])
def candidate_profile(request):
    profile = get_or_create_candidate_profile(request.user)

    if request.method == "GET":
        recalculated_completion = profile.calculate_completion()
        recalculated_onboarding_completed = (
            recalculated_completion >= 100 and profile.has_required_documents()
        )

        if (
            profile.profile_completion_percentage != recalculated_completion
            or profile.is_onboarding_completed != recalculated_onboarding_completed
        ):
            profile.save(
                update_fields=[
                    "profile_completion_percentage",
                    "is_onboarding_completed",
                    "updated_at",
                ]
            )

        serializer = CandidateProfileSerializer(
            profile,
            context={"request": request},
        )
        return Response(serializer.data)

    serializer = CandidateProfileSerializer(
        profile,
        data=request.data,
        partial=True,
        context={"request": request},
    )

    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def candidate_academic_records(request):
    profile = get_or_create_candidate_profile(request.user)

    if request.method == "GET":
        records = profile.academic_records.all().order_by("-is_primary", "-passing_year", "-id")
        serializer = CandidateAcademicRecordSerializer(records, many=True)
        return Response(serializer.data)

    serializer = CandidateAcademicRecordSerializer(data=request.data)

    if serializer.is_valid():
        record = serializer.save(candidate=profile)
        return Response(
            CandidateAcademicRecordSerializer(record).data,
            status=status.HTTP_201_CREATED,
        )

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(["PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def candidate_academic_record_detail(request, record_id):
    profile = get_or_create_candidate_profile(request.user)

    try:
        record = profile.academic_records.get(id=record_id)
    except CandidateAcademicRecord.DoesNotExist:
        return Response(
            {"detail": "Academic record not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    if request.method == "DELETE":
        record.delete()
        return Response({"detail": "Academic record deleted."})

    serializer = CandidateAcademicRecordSerializer(
        record,
        data=request.data,
        partial=True,
    )

    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def candidate_subject_scores(request, record_id):
    profile = get_or_create_candidate_profile(request.user)

    try:
        record = profile.academic_records.get(id=record_id)
    except CandidateAcademicRecord.DoesNotExist:
        return Response(
            {"detail": "Academic record not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    serializer = CandidateSubjectScoreSerializer(data=request.data)

    if serializer.is_valid():
        subject_score = serializer.save(academic_record=record)
        return Response(
            CandidateSubjectScoreSerializer(subject_score).data,
            status=status.HTTP_201_CREATED,
        )

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(["PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def candidate_subject_score_detail(request, record_id, subject_score_id):
    profile = get_or_create_candidate_profile(request.user)

    try:
        record = profile.academic_records.get(id=record_id)
        subject_score = record.subject_scores.get(id=subject_score_id)
    except CandidateAcademicRecord.DoesNotExist:
        return Response(
            {"detail": "Academic record not found."},
            status=status.HTTP_404_NOT_FOUND,
        )
    except CandidateSubjectScore.DoesNotExist:
        return Response(
            {"detail": "Subject score not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    if request.method == "DELETE":
        subject_score.delete()
        return Response({"detail": "Subject score deleted."})

    serializer = CandidateSubjectScoreSerializer(
        subject_score,
        data=request.data,
        partial=True,
    )

    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def candidate_entrance_exam_scores(request):
    profile = get_or_create_candidate_profile(request.user)

    if request.method == "GET":
        scores = profile.entrance_exam_scores.all().order_by("-year", "-id")
        serializer = CandidateEntranceExamScoreSerializer(scores, many=True)
        return Response(serializer.data)

    serializer = CandidateEntranceExamScoreSerializer(data=request.data)

    if serializer.is_valid():
        exam_score = serializer.save(candidate=profile)
        return Response(
            CandidateEntranceExamScoreSerializer(exam_score).data,
            status=status.HTTP_201_CREATED,
        )

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(["PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def candidate_entrance_exam_score_detail(request, score_id):
    profile = get_or_create_candidate_profile(request.user)

    try:
        exam_score = profile.entrance_exam_scores.get(id=score_id)
    except CandidateEntranceExamScore.DoesNotExist:
        return Response(
            {"detail": "Entrance exam score not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    if request.method == "DELETE":
        exam_score.delete()
        return Response({"detail": "Entrance exam score deleted."})

    serializer = CandidateEntranceExamScoreSerializer(
        exam_score,
        data=request.data,
        partial=True,
    )

    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def candidate_documents(request):
    profile = get_or_create_candidate_profile(request.user)

    if request.method == "GET":
        documents = profile.documents.all().order_by("-uploaded_at")
        serializer = CandidateDocumentSerializer(
            documents,
            many=True,
            context={"request": request},
        )
        return Response(serializer.data)

    document_data = request.data.copy()
    encoded_file = document_data.pop("file_data", None)

    if isinstance(encoded_file, list):
        encoded_file = encoded_file[0] if encoded_file else None

    if encoded_file:
        filename = document_data.pop("filename", None) or "document"
        content_type = document_data.pop("content_type", None) or "application/octet-stream"

        if isinstance(filename, list):
            filename = filename[0] if filename else "document"

        if isinstance(content_type, list):
            content_type = content_type[0] if content_type else "application/octet-stream"

        try:
            file_bytes = base64.b64decode(encoded_file, validate=True)
        except (binascii.Error, ValueError):
            return Response(
                {"file": ["Uploaded file data is invalid."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        document_data["file"] = SimpleUploadedFile(
            filename,
            file_bytes,
            content_type=content_type,
        )

    serializer = CandidateDocumentSerializer(
        data=document_data,
        context={"request": request},
    )

    if serializer.is_valid():
        document = serializer.save(candidate=profile)
        profile.save()
        return Response(
            CandidateDocumentSerializer(
                document,
                context={"request": request},
            ).data,
            status=status.HTTP_201_CREATED,
        )

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(["PATCH", "POST"])
@permission_classes([IsAuthenticated])
@transaction.atomic
def candidate_onboarding_submit(request):
    profile = get_or_create_candidate_profile(request.user)

    profile_fields = [
        "phone",
        "city",
        "state",
        "country",
        "current_activity_type",
        "current_education_status",
        "current_stream",
        "study_mode_preference",
        "relocation_preference",
        "preferred_states",
        "preferred_cities",
        "max_annual_budget",
        "needs_scholarship",
        "open_to_education_loan",
        "interested_subjects",
        "disliked_subjects",
        "skills",
        "hobbies",
        "target_careers",
        "career_goal_text",
        "wants_fast_job",
        "wants_government_job",
        "wants_abroad_option",
        "wants_business_or_startup",
        "weekly_study_hours",
        "maths_comfort",
        "english_comfort",
        "computer_comfort",
        "communication_comfort",
    ]

    profile_payload = {
        field: request.data[field]
        for field in profile_fields
        if field in request.data
    }

    profile_serializer = CandidateProfileSerializer(
        profile,
        data=profile_payload,
        partial=True,
        context={"request": request},
    )

    if not profile_serializer.is_valid():
        return Response(profile_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    profile = profile_serializer.save()

    academic_payload = request.data.get("academic_record") or {}

    if academic_payload:
        academic_level = academic_payload.get("level") or get_default_academic_level(profile)

        academic_payload["level"] = academic_level
        academic_payload["stream"] = academic_payload.get("stream") or profile.current_stream
        academic_payload["is_primary"] = True

        record = (
            profile.academic_records.filter(level=academic_level, is_primary=True)
            .order_by("-id")
            .first()
        )

        if record is None:
            record = CandidateAcademicRecord(candidate=profile)

        academic_serializer = CandidateAcademicRecordSerializer(
            record,
            data=academic_payload,
            partial=True,
        )

        if not academic_serializer.is_valid():
            return Response(
                {"academic_record": academic_serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        record = academic_serializer.save(candidate=profile)

        subject_scores = request.data.get("subject_scores", [])

        should_require_subjects = profile.current_activity_type in [
            "student",
            "college_student",
        ]

        valid_subjects = []

        if isinstance(subject_scores, list):
            valid_subjects = [
                subject
                for subject in subject_scores
                if str(subject.get("subject_name", "")).strip()
                and (
                    subject.get("marks_obtained") not in [None, ""]
                    or subject.get("percentage") not in [None, ""]
                    or subject.get("grade") not in [None, ""]
                )
            ]

        if should_require_subjects and len(valid_subjects) < 5:
            return Response(
                {
                    "subject_scores": [
                        "Please add marks/percentage for at least 5 subjects."
                    ]
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if isinstance(subject_scores, list):
            record.subject_scores.all().delete()

            for subject_payload in subject_scores:
                subject_name = str(subject_payload.get("subject_name", "")).strip()

                if not subject_name:
                    continue

                has_marks = subject_payload.get("marks_obtained") not in [None, ""]
                has_percentage = subject_payload.get("percentage") not in [None, ""]
                has_grade = subject_payload.get("grade") not in [None, ""]

                if not has_marks and not has_percentage and not has_grade:
                    continue

                subject_serializer = CandidateSubjectScoreSerializer(data=subject_payload)

                if not subject_serializer.is_valid():
                    return Response(
                        {
                            "subject_scores": subject_serializer.errors,
                            "subject": subject_name,
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                subject_serializer.save(academic_record=record)

    work_experience_payload = request.data.get("work_experience") or {}

    if work_experience_payload:
        work_experience = (
            profile.work_experiences.filter(is_current=True)
            .order_by("-id")
            .first()
        )

        if work_experience is None:
            work_experience = CandidateWorkExperience(candidate=profile)

        work_serializer = CandidateWorkExperienceSerializer(
            work_experience,
            data=work_experience_payload,
            partial=True,
        )

        if not work_serializer.is_valid():
            return Response(
                {"work_experience": work_serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        work_serializer.save(candidate=profile)

    profile.save()

    return Response(
        CandidateProfileSerializer(
            profile,
            context={"request": request},
        ).data
    )
