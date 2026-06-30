import json
import random
import re
import urllib.error
import urllib.request

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import (
    CandidateAcademicRecord,
    CandidateProfile,
    CandidateSubjectScore,
)
from vendors.models import VendorCourse, VendorInstitute


ACTIVITY_TYPES = [
    "student",
    "college_student",
    "employed",
    "self_employed",
    "freelancer",
    "business_owner",
    "unemployed",
]
EDUCATION_STATUSES = [
    "class_12_passed",
    "diploma",
    "ug",
    "graduate",
    "working",
]
STREAMS = ["pcm", "pcb", "pcmb", "commerce", "arts", "vocational", "other"]
STUDY_MODES = ["regular", "online", "distance", "hybrid", "any"]
RELOCATION = ["same_city", "same_state", "anywhere_india", "online_only", "unsure"]
ACADEMIC_LEVELS = ["class_12", "diploma", "ug", "pg"]
ACADEMIC_STATUSES = ["passed", "appearing", "result_awaited"]


def clean_json_text(value):
    text = str(value or "").strip()
    text = re.sub(r"^```(?:json)?", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"```$", "", text).strip()
    return text


def limit_text(value, max_length):
    return str(value or "").strip()[:max_length]


def list_value(value, fallback=None, limit=8):
    fallback = fallback or []

    if isinstance(value, list):
        cleaned = [str(item).strip() for item in value if str(item).strip()]
        return cleaned[:limit] or fallback

    if value:
        cleaned = [item.strip() for item in str(value).split(",") if item.strip()]
        return cleaned[:limit] or fallback

    return fallback


def choice_value(value, allowed, fallback):
    value = str(value or "").strip()
    return value if value in allowed else fallback


def int_range(value, minimum, maximum, fallback):
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = fallback

    return max(minimum, min(maximum, number))


def decimal_range(value, minimum, maximum, fallback):
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = fallback

    return max(minimum, min(maximum, number))


class Command(BaseCommand):
    help = "Generate demo vendor courses and candidate profiles using DeepSeek."

    def add_arguments(self, parser):
        parser.add_argument(
            "--vendor-email",
            default=getattr(settings, "DEMO_VENDOR_EMAIL", "admissions@demo-eazygrade.edu"),
        )
        parser.add_argument("--vendor-name", default="EazyGrade Demo University")
        parser.add_argument("--courses", type=int, default=20)
        parser.add_argument("--profiles", type=int, default=100)
        parser.add_argument(
            "--batch-size",
            type=int,
            default=20,
            help="Number of candidate profiles to request from DeepSeek per batch.",
        )
        parser.add_argument(
            "--reset-demo",
            action="store_true",
            help="Delete demo vendor courses and demo candidate users before generating.",
        )

    def handle(self, *args, **options):
        if not settings.DEEPSEEK_API_KEY:
            raise CommandError("DEEPSEEK_API_KEY is not configured in backend .env.")

        self.vendor_email = options["vendor_email"].strip().lower()
        self.vendor_name = options["vendor_name"].strip()
        self.course_count = max(1, int(options["courses"]))
        self.profile_count = max(1, int(options["profiles"]))
        self.batch_size = max(5, int(options["batch_size"]))

        courses_data = self.generate_courses()
        profiles_data = self.generate_profiles_from_course_data(courses_data)

        with transaction.atomic():
            vendor = self.get_vendor(options["reset_demo"])
            courses = self.save_courses(vendor, courses_data)
            created_count = self.save_profiles(profiles_data)

        self.stdout.write(
            self.style.SUCCESS(
                f"Generated {len(courses)} courses and {created_count} candidate profiles for {vendor.official_email}."
            )
        )

    def call_deepseek(self, prompt):
        body = json.dumps(
            {
                "model": settings.DEEPSEEK_MODEL,
                "temperature": 0.35,
                "response_format": {"type": "json_object"},
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You generate realistic Indian higher-education demo data. "
                            "Return strict JSON only. Keep every item unique and relevant."
                        ),
                    },
                    {"role": "user", "content": json.dumps(prompt, ensure_ascii=True)},
                ],
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            settings.DEEPSEEK_API_URL,
            data=body,
            headers={
                "Authorization": f"Bearer {settings.DEEPSEEK_API_KEY}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                payload = json.loads(response.read().decode("utf-8"))
            content = payload["choices"][0]["message"]["content"]
            return json.loads(clean_json_text(content))
        except (urllib.error.URLError, TimeoutError, KeyError, json.JSONDecodeError, ValueError) as exc:
            raise CommandError(f"DeepSeek generation failed: {exc}") from exc

    def get_vendor(self, reset_demo):
        vendor, _ = VendorInstitute.objects.update_or_create(
            official_email=self.vendor_email,
            defaults={
                "is_email_verified": True,
                "name": self.vendor_name,
                "provider_type": "University",
                "website": "https://demo-eazygrade.edu",
                "city": "Bengaluru",
                "state": "Karnataka",
                "contact_name": "Demo Admissions Team",
                "contact_phone": "+91 90000 00000",
                "description": (
                    "Demo university profile used to test vendor course matching and student outreach."
                ),
                "image_url": "",
            },
        )

        if reset_demo:
            vendor.courses.all().delete()
            User = get_user_model()
            User.objects.filter(email__startswith="demo.candidate.", email__endswith="@eazygrade.test").delete()

        return vendor

    def generate_courses(self):
        prompt = {
            "task": f"Create {self.course_count} diverse vendor courses for an Indian university.",
            "requirements": [
                "Courses must be unique and useful for testing candidate matching.",
                "Include law, business, computer/data, healthcare, design, commerce, humanities, education, and vocational paths.",
                "Subjects and syllabus should contain searchable keywords.",
                "Return exactly the requested count.",
            ],
            "course_schema": {
                "title": "LLB in Legal Studies",
                "level": "Undergraduate|Postgraduate|Diploma|Certificate|Professional",
                "mode": "On campus|Online|Hybrid|Distance learning",
                "duration": "3 years",
                "subjects": "comma-separated subject keywords",
                "seats": "120",
                "fees": "INR 1.5L per year",
                "syllabus": "short syllabus paragraph",
                "idealStudent": "short ideal student profile",
            },
            "response_schema": {"courses": []},
        }
        payload = self.call_deepseek(prompt)
        courses = payload.get("courses", [])

        if len(courses) < self.course_count:
            raise CommandError(f"DeepSeek returned only {len(courses)} courses.")

        return courses[: self.course_count]

    def save_courses(self, vendor, courses_data):
        courses = []

        if not courses_data:
            raise CommandError("No courses were generated.")

        vendor.courses.all().delete()

        for item in courses_data:
            course = VendorCourse.objects.create(
                vendor=vendor,
                title=limit_text(item.get("title"), 255),
                level=limit_text(item.get("level") or "Undergraduate", 100),
                mode=limit_text(item.get("mode") or "Hybrid", 100),
                duration=limit_text(item.get("duration"), 100),
                subjects=limit_text(item.get("subjects"), 4000),
                seats=limit_text(item.get("seats"), 50),
                fees=limit_text(item.get("fees"), 100),
                syllabus=limit_text(item.get("syllabus"), 5000),
                ideal_student=limit_text(item.get("idealStudent"), 3000),
            )
            courses.append(course)

        return courses

    def generate_profiles_from_course_data(self, courses_data):
        course_context = [
            {
                "title": item.get("title", ""),
                "level": item.get("level", ""),
                "mode": item.get("mode", ""),
                "subjects": item.get("subjects", ""),
                "ideal_student": item.get("idealStudent", ""),
            }
            for item in courses_data
        ]
        profiles = []
        remaining = self.profile_count
        batch_number = 1

        while remaining > 0:
            batch_count = min(self.batch_size, remaining)
            prompt = {
                "task": f"Create {batch_count} unique candidate profiles relevant to these vendor courses.",
                "batch_number": batch_number,
                "requirements": [
                    "Make candidates realistic for India.",
                    "Each candidate should strongly match at least one course and weakly match some others.",
                    "Use allowed enum values exactly.",
                    "Do not repeat names, career goals, or subject combinations.",
                    "Return exactly the requested count.",
                ],
                "allowed_values": {
                    "current_activity_type": ACTIVITY_TYPES,
                    "current_education_status": EDUCATION_STATUSES,
                    "current_stream": STREAMS,
                    "study_mode_preference": STUDY_MODES,
                    "relocation_preference": RELOCATION,
                    "academic_level": ACADEMIC_LEVELS,
                    "academic_status": ACADEMIC_STATUSES,
                },
                "courses": course_context,
                "candidate_schema": {
                    "first_name": "Aarav",
                    "last_name": "Sharma",
                    "city": "Jaipur",
                    "state": "Rajasthan",
                    "phone": "9876543210",
                    "current_activity_type": "student",
                    "current_education_status": "class_12_passed",
                    "current_stream": "commerce",
                    "study_mode_preference": "hybrid",
                    "relocation_preference": "anywhere_india",
                    "preferred_states": ["Karnataka", "Maharashtra"],
                    "preferred_cities": ["Bengaluru", "Pune"],
                    "interested_subjects": ["Business Studies", "Economics"],
                    "disliked_subjects": ["Physics"],
                    "skills": ["communication", "excel"],
                    "hobbies": ["debate"],
                    "target_careers": ["Business Analyst"],
                    "career_goal_text": "wants a business analytics career",
                    "comfort": {
                        "maths": 4,
                        "english": 4,
                        "computer": 3,
                        "communication": 5,
                    },
                    "academic_record": {
                        "level": "class_12",
                        "status": "passed",
                        "stream": "commerce",
                        "passing_year": 2025,
                        "percentage": 82.5,
                        "subjects": [
                            {"subject_name": "Business Studies", "marks_obtained": 88, "max_marks": 100},
                            {"subject_name": "Economics", "marks_obtained": 84, "max_marks": 100},
                        ],
                    },
                },
                "response_schema": {"candidates": []},
            }
            payload = self.call_deepseek(prompt)
            batch = payload.get("candidates", [])

            if len(batch) < batch_count:
                raise CommandError(
                    f"DeepSeek returned {len(batch)} candidates for batch {batch_number}; expected {batch_count}."
                )

            profiles.extend(batch[:batch_count])
            remaining -= batch_count
            batch_number += 1
            self.stdout.write(f"Generated {len(profiles)}/{self.profile_count} candidate drafts...")

        return profiles

    def save_profiles(self, profiles_data):
        User = get_user_model()
        created_count = 0

        for index, item in enumerate(profiles_data, start=1):
            email = f"demo.candidate.{index:03d}@eazygrade.test"
            first_name = limit_text(item.get("first_name") or f"Demo{index}", 150)
            last_name = limit_text(item.get("last_name") or "Candidate", 150)

            user, _ = User.objects.update_or_create(
                email=email,
                defaults={
                    "username": email,
                    "first_name": first_name,
                    "last_name": last_name,
                    "is_active": True,
                },
            )
            user.set_unusable_password()
            user.save()

            comfort = item.get("comfort") or {}
            profile, _ = CandidateProfile.objects.update_or_create(
                user=user,
                defaults={
                    "phone": limit_text(item.get("phone") or f"90000{index:05d}", 20),
                    "city": limit_text(item.get("city"), 150),
                    "state": limit_text(item.get("state"), 150),
                    "country": "India",
                    "current_activity_type": choice_value(
                        item.get("current_activity_type"), ACTIVITY_TYPES, "student"
                    ),
                    "current_education_status": choice_value(
                        item.get("current_education_status"), EDUCATION_STATUSES, "class_12_passed"
                    ),
                    "current_stream": choice_value(item.get("current_stream"), STREAMS, "commerce"),
                    "study_mode_preference": choice_value(
                        item.get("study_mode_preference"), STUDY_MODES, "any"
                    ),
                    "relocation_preference": choice_value(
                        item.get("relocation_preference"), RELOCATION, "anywhere_india"
                    ),
                    "preferred_states": list_value(item.get("preferred_states"), ["Karnataka"], 5),
                    "preferred_cities": list_value(item.get("preferred_cities"), ["Bengaluru"], 5),
                    "interested_subjects": list_value(item.get("interested_subjects"), [], 10),
                    "disliked_subjects": list_value(item.get("disliked_subjects"), [], 8),
                    "skills": list_value(item.get("skills"), [], 10),
                    "hobbies": list_value(item.get("hobbies"), [], 8),
                    "target_careers": list_value(item.get("target_careers"), [], 6),
                    "career_goal_text": limit_text(item.get("career_goal_text"), 2000),
                    "max_annual_budget": random.choice([150000, 250000, 350000, 500000]),
                    "weekly_study_hours": int_range(item.get("weekly_study_hours"), 4, 60, 18),
                    "maths_comfort": int_range(comfort.get("maths"), 1, 5, 3),
                    "english_comfort": int_range(comfort.get("english"), 1, 5, 4),
                    "computer_comfort": int_range(comfort.get("computer"), 1, 5, 3),
                    "communication_comfort": int_range(comfort.get("communication"), 1, 5, 4),
                    "needs_scholarship": bool(item.get("needs_scholarship", False)),
                    "open_to_education_loan": bool(item.get("open_to_education_loan", True)),
                    "wants_fast_job": bool(item.get("wants_fast_job", True)),
                    "wants_government_job": bool(item.get("wants_government_job", False)),
                    "wants_abroad_option": bool(item.get("wants_abroad_option", False)),
                    "wants_business_or_startup": bool(item.get("wants_business_or_startup", False)),
                },
            )

            self.save_academic_record(profile, item.get("academic_record") or {})
            profile.save()
            created_count += 1

        return created_count

    def save_academic_record(self, profile, record_data):
        level = choice_value(record_data.get("level"), ACADEMIC_LEVELS, "class_12")
        record, _ = CandidateAcademicRecord.objects.update_or_create(
            candidate=profile,
            is_primary=True,
            defaults={
                "level": level,
                "status": choice_value(record_data.get("status"), ACADEMIC_STATUSES, "passed"),
                "board_or_university": limit_text(
                    record_data.get("board_or_university") or "Demo Board / University",
                    255,
                ),
                "institution_name": limit_text(
                    record_data.get("institution_name") or "Demo Senior Secondary School",
                    255,
                ),
                "stream": choice_value(record_data.get("stream"), STREAMS, profile.current_stream),
                "passing_year": int_range(record_data.get("passing_year"), 2015, 2026, 2025),
                "percentage": decimal_range(record_data.get("percentage"), 35, 99, 78),
                "cgpa": None,
                "max_cgpa": 10,
            },
        )
        record.subject_scores.all().delete()

        subjects = record_data.get("subjects") or []

        if len(subjects) < 5:
            subjects = subjects + [
                {"subject_name": "English", "marks_obtained": 78, "max_marks": 100},
                {"subject_name": "General Studies", "marks_obtained": 76, "max_marks": 100},
                {"subject_name": "Computer Applications", "marks_obtained": 80, "max_marks": 100},
                {"subject_name": "Mathematics", "marks_obtained": 74, "max_marks": 100},
                {"subject_name": "Project Work", "marks_obtained": 82, "max_marks": 100},
            ]

        for subject in subjects[:8]:
            CandidateSubjectScore.objects.create(
                academic_record=record,
                subject_name=limit_text(subject.get("subject_name") or "Subject", 150),
                marks_obtained=decimal_range(subject.get("marks_obtained"), 0, 100, 75),
                max_marks=decimal_range(subject.get("max_marks"), 1, 100, 100),
            )
