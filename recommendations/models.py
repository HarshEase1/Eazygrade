from django.conf import settings
from django.db import models

from accounts.models import CandidateProfile
from institutions.models import UGCDEBProgramme


class RecommendationRun(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    candidate = models.ForeignKey(
        CandidateProfile,
        on_delete=models.CASCADE,
        related_name="recommendation_runs",
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="recommendation_runs",
    )
    profile_signature = models.CharField(max_length=64, db_index=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    sections = models.JSONField(default=dict, blank=True)
    profile_snapshot = models.JSONField(default=dict, blank=True)
    ai_explanation = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True, default="")
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["candidate", "profile_signature"]),
            models.Index(fields=["requested_by", "status"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"RecommendationRun #{self.id} - {self.candidate.user.email}"


class RankedCourseRecommendation(models.Model):
    class RecommendationType(models.TextChoices):
        STRONG = "strong_recommendation", "Strong Recommendation"
        GOOD = "good_option", "Good Option"
        BACKUP = "backup_option", "Backup Option"
        FUTURE_PATH = "future_path", "Future Path"
        NOT_RECOMMENDED = "not_recommended", "Not Recommended"

    run = models.ForeignKey(
        RecommendationRun,
        on_delete=models.CASCADE,
        related_name="recommendations",
    )
    candidate = models.ForeignKey(
        CandidateProfile,
        on_delete=models.CASCADE,
        related_name="ranked_recommendations",
    )
    programme = models.ForeignKey(
        UGCDEBProgramme,
        on_delete=models.CASCADE,
        related_name="ranked_recommendations",
    )
    rank = models.PositiveIntegerField(db_index=True)
    final_score = models.DecimalField(max_digits=5, decimal_places=2, db_index=True)
    match_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        db_index=True,
    )
    recommendation_type = models.CharField(
        max_length=40,
        choices=RecommendationType.choices,
        db_index=True,
    )
    filter_status = models.CharField(max_length=30, db_index=True)
    filter_reasons = models.JSONField(default=list, blank=True)
    filter_penalties = models.JSONField(default=list, blank=True)
    eligibility = models.JSONField(default=dict, blank=True)
    score_breakdown = models.JSONField(default=dict, blank=True)
    positive_factors = models.JSONField(default=list, blank=True)
    negative_factors = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["rank", "-final_score"]
        constraints = [
            models.UniqueConstraint(
                fields=["run", "programme"],
                name="unique_recommendation_run_programme",
            )
        ]
        indexes = [
            models.Index(fields=["candidate", "recommendation_type"]),
            models.Index(fields=["run", "rank"]),
            models.Index(fields=["programme", "final_score"]),
        ]

    def __str__(self):
        return f"{self.rank}. {self.programme.program_name}"


class DemoProgramme(models.Model):
    program_name = models.CharField(max_length=180, unique=True)
    provider = models.CharField(max_length=180, db_index=True)
    degree_type = models.CharField(max_length=40, db_index=True)
    duration = models.CharField(max_length=80, db_index=True)
    fee_range = models.CharField(max_length=120)
    min_fee = models.PositiveIntegerField(default=0, db_index=True)
    max_fee = models.PositiveIntegerField(default=0, db_index=True)
    mode = models.CharField(max_length=80, db_index=True)
    career_tags = models.JSONField(default=list, blank=True)
    background_tags = models.JSONField(default=list, blank=True)
    degree_tags = models.JSONField(default=list, blank=True)
    duration_years = models.DecimalField(max_digits=4, decimal_places=1, default=3)
    description = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["program_name"]
        indexes = [
            models.Index(fields=["degree_type", "mode"]),
            models.Index(fields=["is_active", "program_name"]),
        ]

    def __str__(self):
        return f"{self.program_name} - {self.provider}"
