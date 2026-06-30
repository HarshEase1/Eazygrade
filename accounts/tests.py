import base64
import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from accounts.models import CandidateDocument, CandidateProfile

TEMP_MEDIA_ROOT = tempfile.mkdtemp()

@override_settings(
    MEDIA_ROOT=TEMP_MEDIA_ROOT,
    STORAGES={
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    },
)
class CandidateProfileAPITests(APITestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEMP_MEDIA_ROOT, ignore_errors=True)

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="candidate@example.com",
            email="candidate@example.com",
            password="test-password",
        )
        self.other_user = User.objects.create_user(
            username="other@example.com",
            email="other@example.com",
            password="test-password",
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_profile_get_creates_candidate_profile(self):
        response = self.client.get(reverse("candidate-profile"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(CandidateProfile.objects.filter(user=self.user).exists())
        self.assertEqual(response.data["country"], "India")
        self.assertFalse(response.data["is_onboarding_completed"])

    def completed_payload(self):
        return {
            "phone": "9876543210",
            "city": "Pune",
            "state": "Maharashtra",
            "current_education_status": "class_12_passed",
            "current_stream": "pcm",
            "study_mode_preference": "regular",
            "relocation_preference": "anywhere_india",
            "preferred_states": ["Maharashtra", "Karnataka"],
            "interested_subjects": ["Computer Science", "Mathematics"],
            "target_careers": ["Software Engineer"],
            "max_annual_budget": 250000,
            "weekly_study_hours": 24,
            "maths_comfort": 4,
            "english_comfort": 4,
        }

    def test_profile_patch_requires_100_percent_and_documents_for_onboarding(self):
        payload = self.completed_payload()

        response = self.client.patch(reverse("candidate-profile"), payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["city"], "Pune")
        self.assertEqual(response.data["profile_completion_percentage"], 100)
        self.assertFalse(response.data["is_onboarding_completed"])
        self.assertEqual(
            response.data["missing_required_document_groups"],
            [["class_10_marksheet"], ["class_12_marksheet"]],
        )

    def test_profile_defaults_do_not_count_as_completed_fields(self):
        response = self.client.get(reverse("candidate-profile"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["profile_completion_percentage"], 0)

    def test_any_study_mode_counts_as_completed_preference(self):
        payload = self.completed_payload()
        payload["study_mode_preference"] = "any"

        response = self.client.patch(reverse("candidate-profile"), payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["profile_completion_percentage"], 100)

    def test_onboarding_completes_after_required_documents_are_uploaded(self):
        self.client.patch(reverse("candidate-profile"), self.completed_payload(), format="json")

        profile = CandidateProfile.objects.get(user=self.user)
        CandidateDocument.objects.create(
            candidate=profile,
            document_type="class_10_marksheet",
            file="candidate_documents/user_1/class_10_marksheet/class10.pdf",
        )
        CandidateDocument.objects.create(
            candidate=profile,
            document_type="class_12_marksheet",
            file="candidate_documents/user_1/class_12_marksheet/class12.pdf",
        )

        profile.save()
        response = self.client.get(reverse("candidate-profile"))

        self.assertEqual(response.data["profile_completion_percentage"], 100)
        self.assertEqual(response.data["missing_required_document_groups"], [])
        self.assertTrue(response.data["is_onboarding_completed"])

    def test_working_professional_accepts_undergraduate_or_graduation_document(self):
        payload = self.completed_payload()
        payload["current_education_status"] = "working"
        self.client.patch(reverse("candidate-profile"), payload, format="json")

        profile = CandidateProfile.objects.get(user=self.user)
        for document_type in [
            "class_10_marksheet",
            "class_12_marksheet",
            "graduation_marksheet",
        ]:
            CandidateDocument.objects.create(
                candidate=profile,
                document_type=document_type,
                file=f"candidate_documents/user_1/{document_type}/doc.pdf",
            )

        profile.save()
        response = self.client.get(reverse("candidate-profile"))

        self.assertEqual(response.data["missing_required_document_groups"], [])
        self.assertTrue(response.data["is_onboarding_completed"])

    def test_candidate_document_upload_uses_authenticated_candidate(self):
        upload = tempfile.NamedTemporaryFile(suffix=".pdf")
        upload.write(b"%PDF-1.4 test transcript")
        upload.seek(0)
        upload.name = "marksheet.pdf"

        response = self.client.post(
            reverse("candidate-documents"),
            {
                "document_type": "class_12_marksheet",
                "file": upload,
                "notes": "Class 12 board result",
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        document = CandidateDocument.objects.get(id=response.data["id"])
        self.assertEqual(document.candidate.user, self.user)
        self.assertEqual(document.original_filename, "marksheet.pdf")
        self.assertIn("candidate_documents/user_", document.file.name)
        self.assertEqual(response.data["notes"], "Class 12 board result")
        self.assertIn("file_url", response.data)

    def test_candidate_document_upload_accepts_base64_json(self):
        response = self.client.post(
            reverse("candidate-documents"),
            {
                "document_type": "class_10_marksheet",
                "filename": "class10.pdf",
                "content_type": "application/pdf",
                "file_data": base64.b64encode(b"%PDF-1.4 class 10").decode("ascii"),
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        document = CandidateDocument.objects.get(id=response.data["id"])
        self.assertEqual(document.candidate.user, self.user)
        self.assertEqual(document.original_filename, "class10.pdf")
        self.assertIn("candidate_documents/user_", document.file.name)

    def test_candidate_documents_are_scoped_to_authenticated_user(self):
        my_profile = CandidateProfile.objects.create(user=self.user)
        other_profile = CandidateProfile.objects.create(user=self.other_user)
        CandidateDocument.objects.create(
            candidate=my_profile,
            document_type="id_proof",
            file="candidate_documents/user_1/id_proof/me.pdf",
        )
        CandidateDocument.objects.create(
            candidate=other_profile,
            document_type="id_proof",
            file="candidate_documents/user_2/id_proof/other.pdf",
        )

        response = self.client.get(reverse("candidate-documents"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertIn("candidate_documents/user_1/id_proof/me.pdf", response.data[0]["file"])
