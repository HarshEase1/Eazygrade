from django.contrib.postgres.search import SearchVector
from django.test import TestCase
from django.urls import reverse

from institutions.management.commands.rebuild_search_documents import (
    build_university_document,
)
from institutions.models import (
    SearchDocument,
    SearchEntityType,
    UGCDEBProgramme,
    University,
    UniversityType,
)


class SearchDocumentAPITests(TestCase):
    def setUp(self):
        self.university = University.objects.create(
            name="Example Technology University",
            university_type=UniversityType.PRIVATE,
            state="Delhi",
            district="New Delhi",
            ugc_status="Recognized",
        )

        SearchDocument.objects.create(
            entity_type=SearchEntityType.UNIVERSITY,
            source_id=self.university.id,
            university=self.university,
            title=self.university.name,
            body="Example Technology University computer science UGC university",
            source="ugc_aishe",
            is_active=True,
        )
        SearchDocument.objects.create(
            entity_type=SearchEntityType.UGC_DEB_PROGRAMME,
            source_id=1,
            title="Bachelor of Computer Applications",
            body="Bachelor of Computer Applications computer science UGC-DEB",
            source="ugc_deb",
            is_active=True,
        )
        SearchDocument.objects.update(
            search_vector=(
                SearchVector("title", weight="A", config="english")
                + SearchVector("body", weight="C", config="english")
            )
        )

    def test_ugc_source_filter_matches_ugc_aishe_documents(self):
        response = self.client.get(
            reverse("search-documents"),
            {"q": "computer science", "source": "ugc"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["source"], "ugc_aishe")
        self.assertEqual(response.data["results"][0]["entity_type"], "university")

    def test_ugc_aishe_source_filter_matches_university_documents(self):
        response = self.client.get(
            reverse("search-documents"),
            {"q": "computer science", "source": "ugc_aishe"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["source"], "ugc_aishe")


class SearchDocumentIndexTests(TestCase):
    def test_university_document_includes_linked_programme_keywords(self):
        university = University.objects.create(
            name="Applied Learning University",
            university_type=UniversityType.PRIVATE,
            state="Karnataka",
            ugc_status="Recognized",
        )
        UGCDEBProgramme.objects.create(
            year="2025-26",
            mode="Online",
            hei_name=university.name,
            state=university.state,
            program_name="Bachelor of Computer Applications",
            level="UG",
            university=university,
        )

        document = build_university_document(university)

        self.assertIn("Bachelor of Computer Applications", document["body"])
        self.assertIn("computer science", document["body"])
        self.assertIn("offers UGC-DEB approved programmes", document["body"])
