from django.contrib.postgres.search import SearchVector
from django.core.management.base import BaseCommand
from django.db import transaction
import re
from institutions.models import (
    University,
    UGCDEBProgramme,
    NIRFRanking,
    SearchDocument,
    SearchEntityType,
)


def clean_text(value):
    if value is None:
        return ""
    return str(value).strip()
PROGRAM_SYNONYMS = {
    # Computer / IT
    "master of computer applications": [
        "MCA",
        "computer applications",
        "computer science",
        "software",
        "software development",
        "IT",
        "information technology",
        "programming",
        "coding",
        "backend",
        "developer",
    ],
    "master of computer application": [
        "MCA",
        "computer applications",
        "computer science",
        "software",
        "IT",
    ],
    "bachelor of computer applications": [
        "BCA",
        "computer applications",
        "computer science",
        "software",
        "IT",
        "programming",
    ],
    "bachelor of computer application": [
        "BCA",
        "computer applications",
        "computer science",
        "software",
        "IT",
    ],
    "computer science": [
        "CS",
        "CSE",
        "computer science engineering",
        "software",
        "programming",
        "IT",
    ],
    "information technology": [
        "IT",
        "computer science",
        "software",
        "programming",
        "technology",
    ],
    "data science": [
        "data analytics",
        "machine learning",
        "AI",
        "artificial intelligence",
        "analytics",
        "python",
        "statistics",
    ],
    "artificial intelligence": [
        "AI",
        "machine learning",
        "ML",
        "data science",
        "deep learning",
    ],
    "machine learning": [
        "ML",
        "AI",
        "artificial intelligence",
        "data science",
    ],

    # Management / Business
    "master of business administration": [
        "MBA",
        "management",
        "business administration",
        "business management",
        "leadership",
        "marketing",
        "finance",
        "hr",
        "operations",
    ],
    "masters of business administration": [
        "MBA",
        "management",
        "business administration",
        "business management",
    ],
    "bachelor of business administration": [
        "BBA",
        "business administration",
        "management",
        "business management",
    ],
    "business administration": [
        "MBA",
        "BBA",
        "management",
        "business management",
    ],
    "business analytics": [
        "analytics",
        "data analytics",
        "business intelligence",
        "BI",
        "MBA analytics",
    ],
    "human resource": [
        "HR",
        "human resources",
        "people management",
        "recruitment",
    ],
    "marketing": [
        "digital marketing",
        "sales",
        "brand management",
        "advertising",
    ],
    "finance": [
        "financial management",
        "banking",
        "investment",
        "accounting",
        "commerce",
    ],

    # Commerce
    "master of commerce": [
        "MCOM",
        "M.Com",
        "commerce",
        "finance",
        "accounting",
        "taxation",
        "banking",
    ],
    "bachelor of commerce": [
        "BCOM",
        "B.Com",
        "commerce",
        "finance",
        "accounting",
        "taxation",
        "banking",
    ],
    "accounting": [
        "accounts",
        "commerce",
        "finance",
        "taxation",
    ],
    "taxation": [
        "tax",
        "commerce",
        "accounting",
        "finance",
    ],

    # Arts / Humanities
    "master of arts": [
        "MA",
        "arts",
        "humanities",
        "social science",
    ],
    "bachelor of arts": [
        "BA",
        "arts",
        "humanities",
        "social science",
    ],
    "english": [
        "english literature",
        "literature",
        "language",
        "communication",
    ],
    "hindi": [
        "hindi literature",
        "literature",
        "language",
    ],
    "history": [
        "ancient history",
        "modern history",
        "humanities",
    ],
    "political science": [
        "politics",
        "public administration",
        "governance",
        "civil services",
    ],
    "public administration": [
        "governance",
        "administration",
        "civil services",
        "political science",
    ],
    "sociology": [
        "society",
        "social science",
        "humanities",
    ],
    "psychology": [
        "counselling",
        "mental health",
        "behavioral science",
    ],
    "economics": [
        "economy",
        "finance",
        "statistics",
        "public policy",
    ],

    # Science
    "master of science": [
        "MSC",
        "M.Sc",
        "science",
        "research",
    ],
    "bachelor of science": [
        "BSC",
        "B.Sc",
        "science",
        "research",
    ],
    "mathematics": [
        "maths",
        "math",
        "statistics",
        "quantitative",
    ],
    "statistics": [
        "data science",
        "analytics",
        "mathematics",
        "probability",
    ],
    "physics": [
        "physical science",
        "science",
        "research",
    ],
    "chemistry": [
        "chemical science",
        "science",
        "research",
    ],
    "botany": [
        "plant science",
        "biology",
        "life science",
    ],
    "zoology": [
        "animal science",
        "biology",
        "life science",
    ],
    "biotechnology": [
        "biotech",
        "life science",
        "biology",
        "genetics",
    ],
    "microbiology": [
        "microbes",
        "life science",
        "biology",
        "biotechnology",
    ],

    # Education
    "bachelor of education": [
        "B.Ed",
        "BED",
        "teacher training",
        "teaching",
        "education",
    ],
    "master of education": [
        "M.Ed",
        "MED",
        "teacher training",
        "teaching",
        "education",
    ],
    "education": [
        "teaching",
        "teacher",
        "teacher training",
        "school education",
    ],

    # Law
    "bachelor of laws": [
        "LLB",
        "law",
        "legal studies",
        "advocate",
        "lawyer",
    ],
    "master of laws": [
        "LLM",
        "law",
        "legal studies",
        "advocate",
        "lawyer",
    ],
    "law": [
        "legal",
        "legal studies",
        "advocate",
        "lawyer",
    ],

    # Library / Journalism / Social Work
    "library science": [
        "BLIS",
        "MLIS",
        "library",
        "information science",
    ],
    "journalism": [
        "mass communication",
        "media",
        "communication",
        "reporting",
    ],
    "mass communication": [
        "journalism",
        "media",
        "communication",
        "advertising",
    ],
    "social work": [
        "MSW",
        "social service",
        "ngo",
        "community development",
    ],

    # Health / Medical / Pharmacy
    "pharmacy": [
        "B.Pharm",
        "M.Pharm",
        "pharmaceutical",
        "medicine",
        "drug",
    ],
    "nursing": [
        "healthcare",
        "medical",
        "patient care",
    ],
    "public health": [
        "healthcare",
        "community health",
        "health administration",
    ],
    "nutrition": [
        "food science",
        "dietetics",
        "health",
    ],

    # Agriculture
    "agriculture": [
        "farming",
        "agri",
        "agricultural science",
        "rural development",
    ],
    "horticulture": [
        "agriculture",
        "plants",
        "crop science",
    ],

    # General degree acronyms
    "post graduate diploma": [
        "PG Diploma",
        "PGD",
        "PG diploma course",
        "postgraduate diploma",
    ],
    "diploma": [
        "certificate",
        "short term course",
        "skill course",
    ],
}


DIRECT_ACRONYM_SYNONYMS = {
    "MCA": ["master of computer applications", "computer applications", "software", "IT"],
    "BCA": ["bachelor of computer applications", "computer applications", "software", "IT"],
    "MBA": ["master of business administration", "management", "business"],
    "BBA": ["bachelor of business administration", "management", "business"],
    "MCOM": ["master of commerce", "commerce", "finance", "accounting"],
    "BCOM": ["bachelor of commerce", "commerce", "finance", "accounting"],
    "MA": ["master of arts", "arts", "humanities"],
    "BA": ["bachelor of arts", "arts", "humanities"],
    "MSC": ["master of science", "science"],
    "BSC": ["bachelor of science", "science"],
    "LLB": ["law", "legal studies", "bachelor of laws"],
    "LLM": ["law", "legal studies", "master of laws"],
    "BED": ["bachelor of education", "teaching", "teacher training"],
    "MED": ["master of education", "teaching", "teacher training"],
    "MSW": ["master of social work", "social work", "ngo"],
    "BLIS": ["library science", "library", "information science"],
    "MLIS": ["library science", "library", "information science"],
}


def normalize_program_text(value):
    value = clean_text(value).lower()
    value = value.replace("&", " and ")
    value = value.replace(".", "")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def get_program_synonyms(program_name):
    normalized_name = normalize_program_text(program_name)
    synonyms = []

    for key, values in PROGRAM_SYNONYMS.items():
        normalized_key = normalize_program_text(key)

        if normalized_key and normalized_key in normalized_name:
            synonyms.extend(values)

    # Catch acronyms already present in source programme name
    upper_name = clean_text(program_name).upper().replace(".", "")

    for acronym, values in DIRECT_ACRONYM_SYNONYMS.items():
        if acronym in upper_name.split() or acronym in upper_name:
            synonyms.extend([acronym])
            synonyms.extend(values)

    # De-duplicate while preserving order
    seen = set()
    final_synonyms = []

    for synonym in synonyms:
        key = normalize_program_text(synonym)

        if key and key not in seen:
            seen.add(key)
            final_synonyms.append(synonym)

    return final_synonyms

def build_university_document(university):
    title = university.name

    subtitle_parts = [
        university.get_university_type_display(),
        university.state,
        university.district,
        university.aishe_code,
    ]

    body_parts = [
        university.name,
        university.get_university_type_display(),
        university.address,
        university.state,
        university.district,
        university.zip_code,
        university.ugc_status,
        university.aishe_code,
        university.year_of_establishment,
        university.location,
        "fake university" if university.is_fake else "recognized university",
        "UGC university",
        "AISHE university",
    ]

    programme_terms = []

    for programme in university.deb_programmes.filter(is_active=True).only(
        "program_name",
        "level",
        "mode",
    ):
        programme_terms.extend(
            [
                programme.program_name,
                *get_program_synonyms(programme.program_name),
                programme.level,
                programme.mode,
            ]
        )

    if programme_terms:
        body_parts.extend(
            [
                "offers UGC-DEB approved programmes",
                "approved courses",
                "distance education programmes",
                "online programmes",
                *programme_terms,
            ]
        )

    return {
        "entity_type": SearchEntityType.UNIVERSITY,
        "source_id": university.id,
        "university": university,
        "ugc_deb_programme": None,
        "nirf_ranking": None,
        "title": clean_text(title),
        "subtitle": clean_text(" | ".join(filter(None, subtitle_parts))),
        "body": clean_text(" ".join(filter(None, body_parts))),
        "state": university.state,
        "district": university.district,
        "city": "",
        "category": university.university_type,
        "level": "",
        "mode": "regular",
        "year": university.year_of_establishment,
        "rank": "",
        "score": None,
        "source": "ugc_aishe",
        "source_url": university.source_url or university.website_url or university.aishe_website,
        "metadata": {
            "university_id": university.id,
            "university_type": university.university_type,
            "ugc_status": university.ugc_status,
            "aishe_code": university.aishe_code,
            "is_fake": university.is_fake,
            "website_url": university.website_url,
            "aishe_website": university.aishe_website,
        },
        "is_active": university.is_active,
    }


def build_ugc_deb_document(programme):
    title = programme.program_name

    subtitle_parts = [
        programme.hei_name,
        programme.level,
        programme.mode,
        programme.state,
        programme.year,
        programme.session,
    ]

    program_synonyms = get_program_synonyms(programme.program_name)

    body_parts = [
        programme.program_name,
        *program_synonyms,
        programme.hei_name,
        programme.hei_type,
        programme.state,
        programme.level,
        programme.mode,
        programme.year,
        programme.session,
        "UGC-DEB",
        "UGC DEB",
        "Distance Education Bureau",
        "online programme",
        "online course",
        "distance education",
        "distance learning",
        "ODL",
        "approved programme",
        "approved course",
        "recognized programme",
        "recognised programme",
        "UGC approved",
        "UGC recognized",
    ]

    if programme.university:
        body_parts.extend(
            [
                programme.university.name,
                programme.university.district,
                programme.university.ugc_status,
                programme.university.aishe_code,
            ]
        )

    return {
        "entity_type": SearchEntityType.UGC_DEB_PROGRAMME,
        "source_id": programme.id,
        "university": programme.university,
        "ugc_deb_programme": programme,
        "nirf_ranking": None,
        "title": clean_text(title),
        "subtitle": clean_text(" | ".join(filter(None, subtitle_parts))),
        "body": clean_text(" ".join(filter(None, body_parts))),
        "state": programme.state,
        "district": programme.university.district if programme.university else "",
        "city": "",
        "category": "ugc_deb_programme",
        "level": programme.level,
        "mode": programme.mode,
        "year": programme.year,
        "rank": "",
        "score": None,
        "source": "ugc_deb",
        "source_url": "",
        "metadata": {
            "ugc_deb_programme_id": programme.id,
            "hei_name": programme.hei_name,
            "hei_type": programme.hei_type,
            "program_name": programme.program_name,
            "level": programme.level,
            "mode": programme.mode,
            "session": programme.session,
            "matched_university_id": programme.university_id,
        },
        "is_active": programme.is_active,
    }


def build_nirf_document(ranking):
    title = ranking.name

    subtitle_parts = [
        f"NIRF {ranking.year}",
        ranking.category,
        f"Rank {ranking.rank}" if ranking.rank else "",
        f"Score {ranking.score}" if ranking.score else "",
        ranking.city,
        ranking.state,
    ]

    body_parts = [
        ranking.name,
        ranking.institute_id,
        ranking.category,
        ranking.city,
        ranking.state,
        str(ranking.year),
        f"rank {ranking.rank}",
        f"score {ranking.score}",
        "NIRF ranking",
        "India ranking",
        "top ranked institution",
        "best university",
        "best college",
        "engineering ranking" if ranking.category == "engineering" else "",
        "management ranking" if ranking.category == "management" else "",
        "medical ranking" if ranking.category == "medical" else "",
        "law ranking" if ranking.category == "law" else "",
        "pharmacy ranking" if ranking.category == "pharmacy" else "",
        "overall ranking" if ranking.category == "overall" else "",
    ]

    if ranking.university:
        body_parts.extend(
            [
                ranking.university.name,
                ranking.university.district,
                ranking.university.ugc_status,
                ranking.university.aishe_code,
            ]
        )

    return {
        "entity_type": SearchEntityType.NIRF_RANKING,
        "source_id": ranking.id,
        "university": ranking.university,
        "ugc_deb_programme": None,
        "nirf_ranking": ranking,
        "title": clean_text(title),
        "subtitle": clean_text(" | ".join(filter(None, subtitle_parts))),
        "body": clean_text(" ".join(filter(None, body_parts))),
        "state": ranking.state,
        "district": ranking.university.district if ranking.university else "",
        "city": ranking.city,
        "category": ranking.category,
        "level": "",
        "mode": "",
        "year": str(ranking.year),
        "rank": ranking.rank,
        "score": ranking.score,
        "source": "nirf",
        "source_url": ranking.source_url,
        "metadata": {
            "nirf_ranking_id": ranking.id,
            "institute_id": ranking.institute_id,
            "category": ranking.category,
            "rank": ranking.rank,
            "score": str(ranking.score) if ranking.score else "",
            "tlr_score": str(ranking.tlr_score) if ranking.tlr_score else "",
            "rpc_score": str(ranking.rpc_score) if ranking.rpc_score else "",
            "go_score": str(ranking.go_score) if ranking.go_score else "",
            "oi_score": str(ranking.oi_score) if ranking.oi_score else "",
            "perception_score": str(ranking.perception_score) if ranking.perception_score else "",
            "pdf_url": ranking.pdf_url,
            "graph_url": ranking.graph_url,
            "matched_university_id": ranking.university_id,
        },
        "is_active": True,
    }


class Command(BaseCommand):
    help = "Rebuild global searchable documents and PostgreSQL tsvector index."

    def add_arguments(self, parser):
        parser.add_argument(
            "--type",
            choices=["all", "universities", "ugc_deb", "nirf"],
            default="all",
        )

        parser.add_argument(
            "--clear",
            action="store_true",
            help="Delete existing SearchDocument rows before rebuilding.",
        )

    def handle(self, *args, **options):
        selected_type = options["type"]
        clear = options["clear"]

        if clear:
            if selected_type == "all":
                SearchDocument.objects.all().delete()
            elif selected_type == "universities":
                SearchDocument.objects.filter(
                    entity_type=SearchEntityType.UNIVERSITY
                ).delete()
            elif selected_type == "ugc_deb":
                SearchDocument.objects.filter(
                    entity_type=SearchEntityType.UGC_DEB_PROGRAMME
                ).delete()
            elif selected_type == "nirf":
                SearchDocument.objects.filter(
                    entity_type=SearchEntityType.NIRF_RANKING
                ).delete()

        total_created = 0
        total_updated = 0

        builders = []

        if selected_type in ["all", "universities"]:
            builders.append(
                (
                    "universities",
                    University.objects.all().iterator(chunk_size=1000),
                    build_university_document,
                )
            )

        if selected_type in ["all", "ugc_deb"]:
            builders.append(
                (
                    "ugc_deb",
                    UGCDEBProgramme.objects.select_related("university").all().iterator(chunk_size=1000),
                    build_ugc_deb_document,
                )
            )

        if selected_type in ["all", "nirf"]:
            builders.append(
                (
                    "nirf",
                    NIRFRanking.objects.select_related("university").all().iterator(chunk_size=1000),
                    build_nirf_document,
                )
            )

        for label, queryset, builder in builders:
            self.stdout.write(self.style.WARNING(f"Building search documents for {label}"))

            created_count = 0
            updated_count = 0

            with transaction.atomic():
                for obj in queryset:
                    data = builder(obj)

                    document, created = SearchDocument.objects.update_or_create(
                        entity_type=data["entity_type"],
                        source_id=data["source_id"],
                        defaults=data,
                    )

                    if created:
                        created_count += 1
                    else:
                        updated_count += 1

            total_created += created_count
            total_updated += updated_count

            self.stdout.write(
                self.style.SUCCESS(
                    f"{label}: Created={created_count}, Updated={updated_count}"
                )
            )

        self.stdout.write(self.style.WARNING("Updating PostgreSQL tsvector values"))

        SearchDocument.objects.update(
            search_vector=(
                SearchVector("title", weight="A", config="english")
                + SearchVector("subtitle", weight="B", config="english")
                + SearchVector("body", weight="C", config="english")
                + SearchVector("state", weight="B", config="english")
                + SearchVector("city", weight="B", config="english")
                + SearchVector("district", weight="B", config="english")
                + SearchVector("category", weight="C", config="english")
                + SearchVector("mode", weight="C", config="english")
                + SearchVector("level", weight="C", config="english")
            )
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Search rebuild completed. Created={total_created}, Updated={total_updated}"
            )
        )
