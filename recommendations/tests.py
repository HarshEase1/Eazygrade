from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient, APITestCase

from accounts.models import CandidateAcademicRecord, CandidateProfile
from institutions.models import UGCDEBProgramme
from recommendations.models import RecommendationRun
from recommendations.services.eligibility_engine import check_programme_eligibility


class EligibilityEngineTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="candidate@example.com",
            email="candidate@example.com",
            password="test-password",
        )
        self.profile = CandidateProfile.objects.create(
            user=self.user,
            city="Udaipur",
            state="Rajasthan",
            current_education_status="working",
            current_stream="pcb",
            study_mode_preference="any",
            relocation_preference="anywhere_india",
            preferred_states=["Delhi"],
            interested_subjects=["Computer Science", "Physics"],
            target_careers=["Software Engineer"],
            max_annual_budget=25000,
            weekly_study_hours=20,
            maths_comfort=5,
            english_comfort=5,
            computer_comfort=3,
            communication_comfort=5,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        CandidateAcademicRecord.objects.create(
            candidate=self.profile,
            level="ug",
            status="passed",
            stream="other",
            percentage=75,
            is_primary=True,
        )

    def test_sanskrit_acharya_is_not_eligible_for_computer_profile(self):
        programme = UGCDEBProgramme.objects.create(
            year="2025-26",
            mode="Online(OL)",
            hei_name="The Central Sanskrit University",
            state="Delhi",
            program_name="ACHARYA (SAHITYAM)",
            level="PG",
        )

        result = check_programme_eligibility(self.profile, programme)

        self.assertEqual(result["detected_course_family"], "sanskrit_acharya")
        self.assertEqual(result["eligibility_status"], "not_eligible")
        self.assertTrue(result["failed_rules"])

    def test_default_profile_terms_prefer_computer_programmes(self):
        UGCDEBProgramme.objects.create(
            year="2025-26",
            mode="Online(OL)",
            hei_name="The Central Sanskrit University",
            state="Delhi",
            program_name="ACHARYA (SAHITYAM)",
            level="PG",
        )
        computer_programme = UGCDEBProgramme.objects.create(
            year="2025-26",
            mode="Online(OL)",
            hei_name="Example University",
            state="Delhi",
            program_name="MASTER OF COMPUTER APPLICATIONS",
            level="PG",
        )

        response = self.client.get(
            reverse("candidate-programme-eligibility-list"),
            {"status": "eligible", "limit": 10},
        )

        self.assertEqual(response.status_code, 200)
        returned_ids = [item["programme"]["id"] for item in response.data["results"]]
        self.assertIn(computer_programme.id, returned_ids)
        self.assertTrue(response.data["applied_profile_terms"])
        self.assertNotIn("ACHARYA (SAHITYAM)", [
            item["programme"]["program_name"] for item in response.data["results"]
        ])

    def test_analysis_endpoint_runs_once_for_same_profile_signature(self):
        UGCDEBProgramme.objects.create(
            year="2025-26",
            mode="Online(OL)",
            hei_name="Example University",
            state="Delhi",
            program_name="MASTER OF COMPUTER APPLICATIONS",
            level="PG",
        )

        first_response = self.client.get(reverse("candidate-recommendation-analysis"))
        second_response = self.client.get(reverse("candidate-recommendation-analysis"))

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 200)
        self.assertTrue(first_response.data["executed"])
        self.assertFalse(second_response.data["executed"])
        self.assertTrue(second_response.data["cached"])
        self.assertEqual(RecommendationRun.objects.count(), 1)
        self.assertEqual(
            second_response.data["sections"]["ai_analysis"]["status"],
            "completed",
        )
        self.assertTrue(second_response.data["recommendations"])

    def test_report_pdf_endpoint_returns_pdf(self):
        UGCDEBProgramme.objects.create(
            year="2025-26",
            mode="Online(OL)",
            hei_name="Example University",
            state="Delhi",
            program_name="MASTER OF COMPUTER APPLICATIONS",
            level="PG",
        )

        response = self.client.get(reverse("candidate-recommendation-report-pdf"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response.content.startswith(b"%PDF"))

    def test_analysis_scores_are_decimal_and_not_flat_for_similar_courses(self):
        UGCDEBProgramme.objects.create(
            year="2025-26",
            mode="Open and Distance Learning (ODL)",
            hei_name="Central University of Rajasthan",
            state="Rajasthan",
            program_name="BACHELOR OF SCIENCE (COMPUTER SCIENCE)",
            level="UG",
        )
        UGCDEBProgramme.objects.create(
            year="2025-26",
            mode="Online(OL)",
            hei_name="Example Digital University",
            state="Delhi",
            program_name="BACHELOR OF SCIENCE (COMPUTER SCIENCE AND DATA SCIENCE)",
            level="UG",
        )

        response = self.client.get(reverse("candidate-recommendation-analysis"), {"force": "1"})

        self.assertEqual(response.status_code, 200)
        recommendations = response.data["recommendations"]
        self.assertGreaterEqual(len(recommendations), 2)
        scores = {str(item["match_percentage"]) for item in recommendations[:2]}
        self.assertGreater(len(scores), 1)
        self.assertIn("llm", recommendations[0]["score_breakdown"])
        self.assertFalse(response.data["sections"]["scoring"]["llm"]["used_for_scoring"])
