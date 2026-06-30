from rest_framework import serializers

from recommendations.models import RankedCourseRecommendation, RecommendationRun


class ProgrammeSummarySerializer(serializers.Serializer):
    id = serializers.IntegerField()
    program_name = serializers.CharField()
    hei_name = serializers.CharField()
    hei_type = serializers.CharField()
    state = serializers.CharField()
    level = serializers.CharField()
    mode = serializers.CharField()
    year = serializers.CharField()
    university_id = serializers.IntegerField(allow_null=True)


class RankedCourseRecommendationSerializer(serializers.ModelSerializer):
    programme = serializers.SerializerMethodField()

    class Meta:
        model = RankedCourseRecommendation
        fields = [
            "id",
            "rank",
            "programme",
            "final_score",
            "match_percentage",
            "recommendation_type",
            "filter_status",
            "filter_reasons",
            "filter_penalties",
            "eligibility",
            "score_breakdown",
            "positive_factors",
            "negative_factors",
            "created_at",
        ]

    def get_programme(self, obj):
        programme = obj.programme
        return {
            "id": programme.id,
            "program_name": programme.program_name,
            "hei_name": programme.hei_name,
            "hei_type": programme.hei_type,
            "state": programme.state,
            "level": programme.level,
            "mode": programme.mode,
            "year": programme.year,
            "university_id": programme.university_id,
        }


class RecommendationRunSerializer(serializers.ModelSerializer):
    recommendations = RankedCourseRecommendationSerializer(many=True, read_only=True)

    class Meta:
        model = RecommendationRun
        fields = [
            "id",
            "candidate_id",
            "profile_signature",
            "status",
            "sections",
            "profile_snapshot",
            "ai_explanation",
            "error_message",
            "started_at",
            "completed_at",
            "created_at",
            "updated_at",
            "recommendations",
        ]
