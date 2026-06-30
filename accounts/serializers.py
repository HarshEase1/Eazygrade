from rest_framework import serializers

from accounts.models import (
    CandidateAcademicRecord,
    CandidateDocument,
    CandidateEntranceExamScore,
    CandidateProfile,
    CandidateSubjectScore,
    CandidateWorkExperience
)


class CandidateSubjectScoreSerializer(serializers.ModelSerializer):
    class Meta:
        model = CandidateSubjectScore
        fields = [
            "id",
            "subject_name",
            "marks_obtained",
            "max_marks",
            "percentage",
            "grade",
        ]
        read_only_fields = ["id"]


class CandidateAcademicRecordSerializer(serializers.ModelSerializer):
    subject_scores = CandidateSubjectScoreSerializer(many=True, read_only=True)

    class Meta:
        model = CandidateAcademicRecord
        fields = [
            "id",
            "level",
            "status",
            "board_or_university",
            "institution_name",
            "stream",
            "passing_year",
            "percentage",
            "cgpa",
            "max_cgpa",
            "is_primary",
            "subject_scores",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class CandidateEntranceExamScoreSerializer(serializers.ModelSerializer):
    class Meta:
        model = CandidateEntranceExamScore
        fields = [
            "id",
            "exam_name",
            "year",
            "score",
            "percentile",
            "rank",
            "category_rank",
            "raw_data",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class CandidateDocumentSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = CandidateDocument
        fields = [
            "id",
            "document_type",
            "file",
            "file_url",
            "original_filename",
            "notes",
            "is_verified",
            "verification_notes",
            "uploaded_at",
        ]
        read_only_fields = [
            "id",
            "file_url",
            "original_filename",
            "is_verified",
            "verification_notes",
            "uploaded_at",
        ]

    def get_file_url(self, obj):
        request = self.context.get("request")

        if not obj.file:
            return ""

        if request:
            return request.build_absolute_uri(obj.file.url)

        return obj.file.url

class CandidateWorkExperienceSerializer(serializers.ModelSerializer):
    class Meta:
        model = CandidateWorkExperience
        fields = [
            "id",
            "work_type",
            "industry",
            "role_title",
            "company_or_brand_name",
            "start_year",
            "end_year",
            "is_current",
            "experience_years",
            "monthly_income_range",
            "skills_used",
            "tools_used",
            "description",
            "proof_url",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

class CandidateProfileSerializer(serializers.ModelSerializer):
    academic_records = CandidateAcademicRecordSerializer(many=True, read_only=True)
    entrance_exam_scores = CandidateEntranceExamScoreSerializer(many=True, read_only=True)
    documents = CandidateDocumentSerializer(many=True, read_only=True)
    required_document_groups = serializers.SerializerMethodField()
    missing_required_document_groups = serializers.SerializerMethodField()
    work_experiences = CandidateWorkExperienceSerializer(many=True, read_only=True)

    class Meta:
        model = CandidateProfile
        fields = [
            "id",
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
            "work_experiences",
            "wants_government_job",
            "wants_abroad_option",
            "wants_business_or_startup",
            "weekly_study_hours",
            "maths_comfort",
            "english_comfort",
            "computer_comfort",
            "communication_comfort",
            "profile_completion_percentage",
            "is_onboarding_completed",
            "required_document_groups",
            "missing_required_document_groups",
            "academic_records",
            "entrance_exam_scores",
            "documents",
            "created_at",
            "updated_at",
        ]

        read_only_fields = [
            "id",
            "profile_completion_percentage",
            "is_onboarding_completed",
            "required_document_groups",
            "missing_required_document_groups",
            "created_at",
            "updated_at",
        ]

    def get_required_document_groups(self, obj):
        return obj.get_required_document_groups()

    def get_missing_required_document_groups(self, obj):
        return obj.missing_required_document_groups()
