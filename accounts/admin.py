from django.contrib import admin

from accounts.models import (
    CandidateAcademicRecord,
    CandidateDocument,
    CandidateEntranceExamScore,
    CandidateProfile,
    CandidateSubjectScore,
    candidate_document_upload_path,
)


class CandidateSubjectScoreInline(admin.TabularInline):
    model = CandidateSubjectScore
    extra = 0


@admin.register(CandidateAcademicRecord)
class CandidateAcademicRecordAdmin(admin.ModelAdmin):
    inlines = [CandidateSubjectScoreInline]
    list_display = ["candidate", "level", "stream", "passing_year", "percentage", "is_primary"]
    list_filter = ["level", "stream", "is_primary"]
    search_fields = ["candidate__user__email", "board_or_university", "institution_name"]


@admin.register(CandidateProfile)
class CandidateProfileAdmin(admin.ModelAdmin):
    list_display = [
        "user",
        "city",
        "state",
        "current_education_status",
        "profile_completion_percentage",
        "is_onboarding_completed",
    ]
    list_filter = [
        "current_education_status",
        "current_stream",
        "study_mode_preference",
        "is_onboarding_completed",
    ]
    search_fields = ["user__email", "phone", "city", "state"]


@admin.register(CandidateEntranceExamScore)
class CandidateEntranceExamScoreAdmin(admin.ModelAdmin):
    list_display = ["candidate", "exam_name", "year", "score", "percentile", "rank"]
    list_filter = ["exam_name", "year"]
    search_fields = ["candidate__user__email", "exam_name"]


@admin.register(CandidateDocument)
class CandidateDocumentAdmin(admin.ModelAdmin):
    list_display = ["candidate", "document_type", "original_filename", "is_verified", "uploaded_at"]
    list_filter = ["document_type", "is_verified"]
    search_fields = ["candidate__user__email", "original_filename"]
