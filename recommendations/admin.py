from django.contrib import admin

from recommendations.models import RankedCourseRecommendation, RecommendationRun


class RankedCourseRecommendationInline(admin.TabularInline):
    model = RankedCourseRecommendation
    extra = 0
    fields = ["rank", "programme", "final_score", "match_percentage", "recommendation_type"]
    readonly_fields = fields
    can_delete = False


@admin.register(RecommendationRun)
class RecommendationRunAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "candidate",
        "requested_by",
        "status",
        "created_at",
        "completed_at",
    ]
    list_filter = ["status", "created_at", "completed_at"]
    search_fields = ["candidate__user__email", "requested_by__email", "profile_signature"]
    readonly_fields = [
        "profile_signature",
        "sections",
        "profile_snapshot",
        "ai_explanation",
        "error_message",
        "started_at",
        "completed_at",
        "created_at",
        "updated_at",
    ]
    inlines = [RankedCourseRecommendationInline]


@admin.register(RankedCourseRecommendation)
class RankedCourseRecommendationAdmin(admin.ModelAdmin):
    list_display = [
        "rank",
        "candidate",
        "programme",
        "final_score",
        "match_percentage",
        "recommendation_type",
    ]
    list_filter = ["recommendation_type", "filter_status", "created_at"]
    search_fields = ["candidate__user__email", "programme__program_name", "programme__hei_name"]
    readonly_fields = [
        "eligibility",
        "score_breakdown",
        "positive_factors",
        "negative_factors",
        "filter_reasons",
        "filter_penalties",
    ]
