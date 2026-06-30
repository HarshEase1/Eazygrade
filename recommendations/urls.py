from django.urls import path

from recommendations.views import (
    candidate_recommendation_analysis,
    candidate_recommendation_report_pdf,
    candidate_programme_eligibility_list,
    check_programme_eligibility_api,
)

urlpatterns = [
    path(
        "analysis/",
        candidate_recommendation_analysis,
        name="candidate-recommendation-analysis",
    ),
    path(
        "analysis/report/pdf/",
        candidate_recommendation_report_pdf,
        name="candidate-recommendation-report-pdf",
    ),
    path(
        "eligibility/programmes/",
        candidate_programme_eligibility_list,
        name="candidate-programme-eligibility-list",
    ),
    path(
        "eligibility/programmes/<int:programme_id>/",
        check_programme_eligibility_api,
        name="check-programme-eligibility",
    ),
]
