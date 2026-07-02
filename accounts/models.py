from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class EducationStatus(models.TextChoices):
    CLASS_10 = "class_10", "Class 10"
    CLASS_11 = "class_11", "Class 11"
    CLASS_12 = "class_12", "Class 12"
    CLASS_12_PASSED = "class_12_passed", "Class 12 Passed"
    DIPLOMA = "diploma", "Diploma"
    UG = "ug", "Undergraduate"
    GRADUATE = "graduate", "Graduate"
    WORKING = "working", "Working Professional"
    UNSURE = "unsure", "Unsure"


class Stream(models.TextChoices):
    PCM = "pcm", "Science - PCM"
    PCB = "pcb", "Science - PCB"
    PCMB = "pcmb", "Science - PCMB"
    COMMERCE = "commerce", "Commerce"
    ARTS = "arts", "Arts / Humanities"
    VOCATIONAL = "vocational", "Vocational"
    OTHER = "other", "Other"
    UNSURE = "unsure", "Unsure"


class StudyModePreference(models.TextChoices):
    REGULAR = "regular", "Regular / On-campus"
    ONLINE = "online", "Online"
    DISTANCE = "distance", "Distance / ODL"
    HYBRID = "hybrid", "Hybrid"
    ANY = "any", "Any"


class RelocationPreference(models.TextChoices):
    SAME_CITY = "same_city", "Same city only"
    SAME_STATE = "same_state", "Same state"
    ANYWHERE_INDIA = "anywhere_india", "Anywhere in India"
    ONLINE_ONLY = "online_only", "Online only"
    UNSURE = "unsure", "Unsure"


class CurrentActivityType(models.TextChoices):
    STUDENT = "student", "Student"
    COLLEGE_STUDENT = "college_student", "College Student"
    EMPLOYED = "employed", "Employed"
    SELF_EMPLOYED = "self_employed", "Self Employed"
    FREELANCER = "freelancer", "Freelancer"
    BUSINESS_OWNER = "business_owner", "Business Owner"
    CONTENT_CREATOR = "content_creator", "Content Creator / YouTuber"
    FAMILY_BUSINESS = "family_business", "Family Business"
    UNEMPLOYED = "unemployed", "Unemployed / Career Gap"
    HOMEMAKER = "homemaker", "Homemaker / Career Restart"
    UNSURE = "unsure", "Unsure"

class CandidateProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="candidate_profile",
    )
    phone = models.CharField(max_length=20, blank=True, default="")
    city = models.CharField(max_length=150, blank=True, default="")
    state = models.CharField(max_length=150, blank=True, default="")
    country = models.CharField(max_length=100, blank=True, default="India")
    current_education_status = models.CharField(
        max_length=50,
        choices=EducationStatus.choices,
        default=EducationStatus.UNSURE,
        db_index=True,
    )
    current_stream = models.CharField(
        max_length=50,
        choices=Stream.choices,
        default=Stream.UNSURE,
        db_index=True,
    )
    study_mode_preference = models.CharField(
        max_length=50,
        choices=StudyModePreference.choices,
        default=StudyModePreference.ANY,
        db_index=True,
    )
    relocation_preference = models.CharField(
        max_length=50,
        choices=RelocationPreference.choices,
        default=RelocationPreference.UNSURE,
        db_index=True,
    )
    preferred_states = models.JSONField(default=list, blank=True)
    preferred_cities = models.JSONField(default=list, blank=True)
    max_annual_budget = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Maximum yearly budget in INR",
    )
    needs_scholarship = models.BooleanField(default=False)
    open_to_education_loan = models.BooleanField(default=False)
    interested_subjects = models.JSONField(
        default=list,
        blank=True,
        help_text="Example: ['Computer Science', 'Maths', 'Business']",
    )
    disliked_subjects = models.JSONField(
        default=list,
        blank=True,
        help_text="Example: ['Physics', 'Chemistry']",
    )
    skills = models.JSONField(
        default=list,
        blank=True,
        help_text="Example: ['coding', 'communication', 'design']",
    )
    hobbies = models.JSONField(default=list, blank=True)
    target_careers = models.JSONField(
        default=list,
        blank=True,
        help_text="Example: ['software engineer', 'data analyst', 'doctor']",
    )
    career_goal_text = models.TextField(
        blank=True,
        default="",
        help_text="Free text: what the student wants or is confused about",
    )
    current_activity_type = models.CharField(
        max_length=50,
        choices=CurrentActivityType.choices,
        default=CurrentActivityType.UNSURE,
        db_index=True,
    )
    wants_fast_job = models.BooleanField(default=False)
    wants_government_job = models.BooleanField(default=False)
    wants_abroad_option = models.BooleanField(default=False)
    wants_business_or_startup = models.BooleanField(default=False)
    weekly_study_hours = models.PositiveIntegerField(null=True, blank=True)
    maths_comfort = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text="1 weak, 5 strong",
    )
    english_comfort = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )
    computer_comfort = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )
    communication_comfort = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )
    profile_completion_percentage = models.PositiveSmallIntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    is_onboarding_completed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    REQUIRED_DOCUMENT_GROUPS = {
        EducationStatus.CLASS_12_PASSED: [
            ["class_10_marksheet"],
            ["class_12_marksheet"],
        ],
        EducationStatus.UG: [
            ["class_10_marksheet"],
            ["class_12_marksheet"],
        ],
        EducationStatus.GRADUATE: [
            ["class_10_marksheet"],
            ["class_12_marksheet"],
            ["undergraduate_marksheet", "graduation_marksheet"],
        ],
        EducationStatus.WORKING: [
            ["class_10_marksheet"],
            ["class_12_marksheet"],
            ["undergraduate_marksheet", "graduation_marksheet"],
        ],
    }

    def get_required_document_groups(self):
        return self.REQUIRED_DOCUMENT_GROUPS.get(self.current_education_status, [])

    def missing_required_document_groups(self):
        if not self.pk:
            return self.get_required_document_groups()

        uploaded_types = set(
            self.documents.exclude(file="").values_list("document_type", flat=True)
        )
        return [
            group
            for group in self.get_required_document_groups()
            if not uploaded_types.intersection(group)
        ]

    def has_required_documents(self):
        return not self.missing_required_document_groups()

    def calculate_completion(self):
        profile_values = [
            self.city,
            self.state,
            self.current_education_status
            if self.current_education_status != EducationStatus.UNSURE
            else "",
            self.current_stream if self.current_stream != Stream.UNSURE else "",
            self.study_mode_preference
            if self.study_mode_preference != StudyModePreference.ANY
            else "",
            self.relocation_preference
            if self.relocation_preference != RelocationPreference.UNSURE
            else "",
            self.interested_subjects,
            self.target_careers,
            self.max_annual_budget,
            self.weekly_study_hours,
            self.maths_comfort,
            self.english_comfort,
        ]

        academic_complete = False
        subject_complete = False
        work_complete = False

        if self.pk:
            primary_record = (
                self.academic_records.filter(is_primary=True)
                .order_by("-id")
                .first()
            )

            if primary_record:
                academic_complete = bool(
                    primary_record.level
                    and primary_record.status
                    and primary_record.stream != Stream.UNSURE
                    and primary_record.passing_year
                    and (primary_record.percentage is not None or primary_record.cgpa is not None)
                )

                valid_subject_count = primary_record.subject_scores.filter(
                    subject_name__isnull=False,
                ).exclude(
                    subject_name=""
                ).filter(
                    models.Q(marks_obtained__isnull=False)
                    | models.Q(percentage__isnull=False)
                    | models.Q(grade__gt="")
                ).count()

                subject_complete = valid_subject_count >= 5

            if self.current_activity_type in [
                CurrentActivityType.EMPLOYED,
                CurrentActivityType.SELF_EMPLOYED,
                CurrentActivityType.FREELANCER,
                CurrentActivityType.BUSINESS_OWNER,
                CurrentActivityType.CONTENT_CREATOR,
                CurrentActivityType.FAMILY_BUSINESS,
            ]:
                current_work = (
                    self.work_experiences.filter(is_current=True)
                    .order_by("-id")
                    .first()
                )

                if current_work:
                    work_complete = bool(
                        current_work.work_type
                        and current_work.industry
                        and current_work.role_title
                        and current_work.company_or_brand_name
                        and current_work.experience_years is not None
                        and current_work.skills_used
                        and current_work.description
                    )

        student_activity = self.current_activity_type in [
            CurrentActivityType.STUDENT,
            CurrentActivityType.COLLEGE_STUDENT,
        ]
        work_activity = self.current_activity_type in [
            CurrentActivityType.EMPLOYED,
            CurrentActivityType.SELF_EMPLOYED,
            CurrentActivityType.FREELANCER,
            CurrentActivityType.BUSINESS_OWNER,
            CurrentActivityType.CONTENT_CREATOR,
            CurrentActivityType.FAMILY_BUSINESS,
        ]
        activity_detail_complete = (
            subject_complete
            if student_activity
            else work_complete
            if work_activity
            else self.current_activity_type != CurrentActivityType.UNSURE
        )

        complete_values = profile_values + [academic_complete, activity_detail_complete]

        filled = sum(1 for value in complete_values if value not in [None, "", [], {}, False])

        return int((filled / len(complete_values)) * 100)

    def save(self, *args, **kwargs):
        self.profile_completion_percentage = self.calculate_completion()
        self.is_onboarding_completed = (
            self.profile_completion_percentage >= 100 and self.has_required_documents()
        )
        super().save(*args, **kwargs)

    def __str__(self):
        return f"CandidateProfile - {self.user.email}"


class CandidateWorkExperience(models.Model):
    candidate = models.ForeignKey(
        CandidateProfile,
        on_delete=models.CASCADE,
        related_name="work_experiences",
    )

    work_type = models.CharField(max_length=50, db_index=True)
    industry = models.CharField(max_length=150, blank=True, default="")
    role_title = models.CharField(max_length=150, blank=True, default="")
    company_or_brand_name = models.CharField(max_length=255, blank=True, default="")

    start_year = models.PositiveIntegerField(null=True, blank=True)
    end_year = models.PositiveIntegerField(null=True, blank=True)
    is_current = models.BooleanField(default=False)

    experience_years = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        null=True,
        blank=True,
    )

    monthly_income_range = models.CharField(max_length=100, blank=True, default="")
    skills_used = models.JSONField(default=list, blank=True)
    tools_used = models.JSONField(default=list, blank=True)

    description = models.TextField(blank=True, default="")
    proof_url = models.URLField(max_length=1000, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

class AcademicLevel(models.TextChoices):
    CLASS_10 = "class_10", "Class 10"
    CLASS_11 = "class_11", "Class 11"
    CLASS_12 = "class_12", "Class 12"
    DIPLOMA = "diploma", "Diploma"
    UG = "ug", "Undergraduate"
    PG = "pg", "Postgraduate"


class AcademicStatus(models.TextChoices):
    APPEARING = "appearing", "Appearing"
    PASSED = "passed", "Passed"
    FAILED = "failed", "Failed"
    RESULT_AWAITED = "result_awaited", "Result Awaited"


class CandidateAcademicRecord(models.Model):
    candidate = models.ForeignKey(
        CandidateProfile,
        on_delete=models.CASCADE,
        related_name="academic_records",
    )
    level = models.CharField(max_length=50, choices=AcademicLevel.choices, db_index=True)
    status = models.CharField(
        max_length=50,
        choices=AcademicStatus.choices,
        default=AcademicStatus.PASSED,
    )
    board_or_university = models.CharField(max_length=255, blank=True, default="")
    institution_name = models.CharField(max_length=255, blank=True, default="")
    stream = models.CharField(
        max_length=50,
        choices=Stream.choices,
        default=Stream.UNSURE,
        db_index=True,
    )
    passing_year = models.PositiveIntegerField(null=True, blank=True)
    percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    cgpa = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    max_cgpa = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        null=True,
        blank=True,
        default=10,
    )
    is_primary = models.BooleanField(
        default=False,
        help_text="Latest/highest relevant qualification",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["candidate", "level"]),
            models.Index(fields=["stream"]),
            models.Index(fields=["passing_year"]),
            models.Index(fields=["percentage"]),
        ]

    def __str__(self):
        return f"{self.candidate.user.email} - {self.level}"


class CandidateSubjectScore(models.Model):
    academic_record = models.ForeignKey(
        CandidateAcademicRecord,
        on_delete=models.CASCADE,
        related_name="subject_scores",
    )
    subject_name = models.CharField(max_length=150, db_index=True)
    marks_obtained = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
    )
    max_marks = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    grade = models.CharField(max_length=20, blank=True, default="")

    class Meta:
        indexes = [
            models.Index(fields=["subject_name"]),
            models.Index(fields=["percentage"]),
        ]

    def save(self, *args, **kwargs):
        if self.marks_obtained is not None and self.max_marks:
            self.percentage = (self.marks_obtained / self.max_marks) * 100
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.subject_name} - {self.percentage}"


class CandidateEntranceExamScore(models.Model):
    candidate = models.ForeignKey(
        CandidateProfile,
        on_delete=models.CASCADE,
        related_name="entrance_exam_scores",
    )
    exam_name = models.CharField(
        max_length=100,
        db_index=True,
        help_text="Example: CUET, JEE, NEET, CLAT, NATA",
    )
    year = models.PositiveIntegerField(null=True, blank=True)
    score = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    percentile = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    rank = models.PositiveIntegerField(null=True, blank=True)
    category_rank = models.PositiveIntegerField(null=True, blank=True)
    raw_data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["exam_name"]),
            models.Index(fields=["year"]),
            models.Index(fields=["percentile"]),
            models.Index(fields=["rank"]),
        ]

    def __str__(self):
        return f"{self.exam_name} - {self.candidate.user.email}"


def candidate_document_upload_path(instance, filename):
    return f"candidate_documents/user_{instance.candidate.user_id}/{instance.document_type}/{filename}"


class CandidateDocumentType(models.TextChoices):
    CLASS_10_MARKSHEET = "class_10_marksheet", "Class 10 Marksheet"
    CLASS_12_MARKSHEET = "class_12_marksheet", "Class 12 Marksheet"
    UNDERGRADUATE_MARKSHEET = "undergraduate_marksheet", "Undergraduate Marksheet"
    GRADUATION_MARKSHEET = "graduation_marksheet", "Graduation Marksheet"
    ENTRANCE_SCORECARD = "entrance_scorecard", "Entrance Exam Scorecard"
    ID_PROOF = "id_proof", "ID Proof"
    PHOTO = "photo", "Photo"
    DOMICILE_CERTIFICATE = "domicile_certificate", "Domicile Certificate"
    CATEGORY_CERTIFICATE = "category_certificate", "Category Certificate"
    INCOME_CERTIFICATE = "income_certificate", "Income Certificate"
    TRANSFER_CERTIFICATE = "transfer_certificate", "Transfer Certificate"
    MIGRATION_CERTIFICATE = "migration_certificate", "Migration Certificate"
    OTHER = "other", "Other"


class CandidateDocument(models.Model):
    candidate = models.ForeignKey(
        CandidateProfile,
        on_delete=models.CASCADE,
        related_name="documents",
    )
    document_type = models.CharField(
        max_length=100,
        choices=CandidateDocumentType.choices,
        db_index=True,
    )
    file = models.FileField(upload_to=candidate_document_upload_path)
    original_filename = models.CharField(max_length=255, blank=True, default="")
    notes = models.TextField(blank=True, default="")
    is_verified = models.BooleanField(default=False)
    verification_notes = models.TextField(blank=True, default="")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["candidate", "document_type"]),
            models.Index(fields=["is_verified"]),
        ]

    def save(self, *args, **kwargs):
        if self.file and not self.original_filename:
            self.original_filename = self.file.name.split("/")[-1]
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.document_type} - {self.candidate.user.email}"
