from django.urls import path

from accounts import views

urlpatterns = [
    path("google/", views.google_login, name="google-login"),
    path("me/", views.me, name="me"),
    path("refresh/", views.refresh_session, name="refresh-session"),
    path("logout/", views.logout, name="logout"),


    path("candidate/profile/", views.candidate_profile, name="candidate-profile"),

    path("candidate/academic-records/", views.candidate_academic_records, name="candidate-academic-records"),
    path("candidate/academic-records/<int:record_id>/", views.candidate_academic_record_detail, name="candidate-academic-record-detail"),

    path("candidate/academic-records/<int:record_id>/subjects/", views.candidate_subject_scores, name="candidate-subject-scores"),
    path("candidate/academic-records/<int:record_id>/subjects/<int:subject_score_id>/", views.candidate_subject_score_detail, name="candidate-subject-score-detail"),

    path("candidate/entrance-exams/", views.candidate_entrance_exam_scores, name="candidate-entrance-exam-scores"),
    path("candidate/entrance-exams/<int:score_id>/", views.candidate_entrance_exam_score_detail, name="candidate-entrance-exam-score-detail"),

    path("candidate/documents/", views.candidate_documents, name="candidate-documents"),

    path(
    "candidate/onboarding/",
    views.candidate_onboarding_submit,
    name="candidate-onboarding-submit",
),
]
