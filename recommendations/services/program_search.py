import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from django.conf import settings


INTENT_KEYWORDS = {
    "law": ["law", "lawyer", "legal", "judiciary", "court", "llb", "advocate"],
    "government": ["government", "govt", "civil services", "upsc", "public policy", "public administration"],
    "commerce": ["commerce", "account", "finance", "bcom", "mcom", "banking"],
    "business": ["business", "management", "mba", "bba", "startup", "entrepreneur"],
    "technology": ["coding", "software", "computer", "it", "programming", "developer", "bca", "mca"],
    "data": ["data science", "analytics", "data analysis", "analyst", "statistics"],
    "teaching": ["teaching", "teacher", "education", "b.ed", "bed"],
    "media": ["media", "journalism", "content", "creator", "writing"],
    "design": ["design", "designer", "creative", "ux", "ui"],
    "psychology": ["psychology", "counselling", "mental health"],
    "science": ["science", "mathematics", "maths", "b.sc", "bsc"],
}

BACKGROUND_KEYWORDS = {
    "commerce": ["commerce", "accounts", "accountancy", "business studies"],
    "science": ["science", "pcm", "pcb", "maths", "mathematics"],
    "arts": ["arts", "humanities", "political science", "history"],
    "graduate": ["graduate", "graduation", "undergraduate", "degree"],
    "working": ["working professional", "working", "job", "employed"],
    "student": ["student", "school", "class 12", "12th"],
}

MODE_KEYWORDS = {
    "Online": ["online"],
    "Distance": ["distance", "odl", "remote"],
    "Regular": ["regular", "campus", "on-campus", "college"],
}

DEGREE_KEYWORDS = {
    "UG": ["undergraduate", "bachelor", "after 12", "class 12", "12th", "ug"],
    "PG": ["postgraduate", "masters", "master", "after graduation", "pg"],
    "Diploma": ["diploma", "certificate", "short term", "short-term"],
}


@dataclass
class SearchProgramme:
    program_name: str
    provider: str
    degree_type: str
    duration: str
    fee_range: str
    min_fee: int
    max_fee: int
    mode: str
    career_tags: list
    background_tags: list
    degree_tags: list
    duration_years: Decimal
    description: str
    source: str = ""
    source_id: Optional[int] = None


def normalize(value):
    return str(value or "").strip().lower()


def contains_any(text, keywords):
    return any(keyword in text for keyword in keywords)


def unique(values):
    result = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result


def infer_tags(text, keyword_map):
    normalized = normalize(text)
    return [
        key
        for key, keywords in keyword_map.items()
        if key in normalized or contains_any(normalized, keywords)
    ]


def infer_degree_type(value):
    text = normalize(value)
    if "post" in text or text in ["pg", "masters", "master"]:
        return "PG"
    if "diploma" in text or "certificate" in text:
        return "Diploma"
    if "ug" in text or "under" in text or "bachelor" in text:
        return "UG"
    return value or "Not listed"


def infer_duration_years(value):
    text = normalize(value)
    if not text:
        return Decimal("3.0")

    if "semester" in text:
        semester_match = re.search(r"(\d+)", text)
        if semester_match:
            return (Decimal(semester_match.group(1)) / Decimal("2")).quantize(Decimal("0.1"))

    match = re.search(r"(\d+(?:\.\d+)?)", text)
    if match:
        return Decimal(match.group(1))

    return Decimal("3.0")


def parse_fee_values(value):
    numbers = [int(number.replace(",", "")) for number in re.findall(r"\d[\d,]*", str(value or ""))]
    if not numbers:
        return 0, 0
    return min(numbers), max(numbers)


def search_programme_from_ugc(programme):
    text = " ".join(
        [
            programme.program_name,
            programme.hei_name,
            programme.level,
            programme.mode,
            programme.state,
        ]
    )
    career_tags = infer_tags(text, INTENT_KEYWORDS)

    return SearchProgramme(
        program_name=programme.program_name,
        provider=programme.hei_name,
        degree_type=infer_degree_type(programme.level),
        duration="Not listed",
        fee_range="Not listed",
        min_fee=0,
        max_fee=0,
        mode=programme.mode or "Not listed",
        career_tags=career_tags,
        background_tags=infer_tags(text, BACKGROUND_KEYWORDS),
        degree_tags=career_tags,
        duration_years=Decimal("3.0"),
        description=f"UGC-DEB listed programme from {programme.hei_name}",
        source="ugc_deb",
        source_id=programme.id,
    )


def search_programme_from_vendor(course):
    text = " ".join(
        [
            course.title,
            course.level,
            course.mode,
            course.duration,
            course.subjects,
            course.syllabus,
            course.ideal_student,
            course.vendor.name,
            course.vendor.provider_type,
            course.vendor.description,
            course.vendor.state,
            course.vendor.city,
        ]
    )
    min_fee, max_fee = parse_fee_values(course.fees)
    career_tags = infer_tags(text, INTENT_KEYWORDS)

    return SearchProgramme(
        program_name=course.title,
        provider=course.vendor.name,
        degree_type=infer_degree_type(course.level),
        duration=course.duration or "Not listed",
        fee_range=course.fees or "Not listed",
        min_fee=min_fee,
        max_fee=max_fee,
        mode=course.mode or "Not listed",
        career_tags=career_tags,
        background_tags=infer_tags(text, BACKGROUND_KEYWORDS),
        degree_tags=career_tags,
        duration_years=infer_duration_years(course.duration),
        description=course.ideal_student or course.subjects or course.syllabus or course.vendor.description,
        source="vendor_course",
        source_id=course.id,
    )


def search_programme_from_demo(programme):
    return SearchProgramme(
        program_name=programme.program_name,
        provider=programme.provider,
        degree_type=programme.degree_type,
        duration=programme.duration,
        fee_range=programme.fee_range,
        min_fee=programme.min_fee,
        max_fee=programme.max_fee,
        mode=programme.mode,
        career_tags=programme.career_tags or [],
        background_tags=programme.background_tags or [],
        degree_tags=programme.degree_tags or [],
        duration_years=programme.duration_years,
        description=programme.description,
        source="demo_programme",
        source_id=programme.id,
    )


def search_programme_from_university(university):
    text = " ".join(
        [
            university.name,
            university.university_type,
            university.address,
            university.state,
            university.district,
            university.ugc_status,
            university.source,
            university.location,
            str(university.raw_data or ""),
        ]
    )
    career_tags = infer_tags(text, INTENT_KEYWORDS)

    return SearchProgramme(
        program_name=university.name,
        provider=f"{university.get_university_type_display()} / {university.get_source_display()}",
        degree_type="University",
        duration=university.year_of_establishment or "Not listed",
        fee_range=university.ugc_status or "Not listed",
        min_fee=0,
        max_fee=0,
        mode=university.location or "Not listed",
        career_tags=career_tags,
        background_tags=infer_tags(text, BACKGROUND_KEYWORDS),
        degree_tags=career_tags,
        duration_years=Decimal("3.0"),
        description=f"UGC/AISHE university record in {university.state or 'India'}",
        source="university",
        source_id=university.id,
    )


def search_programme_from_nirf(ranking):
    text = " ".join(
        [
            ranking.name,
            ranking.category,
            ranking.city,
            ranking.state,
            ranking.rank,
            ranking.institute_id,
            str(ranking.year),
            str(ranking.raw_data or ""),
        ]
    )
    career_tags = infer_tags(text, INTENT_KEYWORDS)

    return SearchProgramme(
        program_name=ranking.name,
        provider=f"NIRF {ranking.category.title()} ranking",
        degree_type="NIRF",
        duration=str(ranking.year),
        fee_range=f"Rank {ranking.rank}" if ranking.rank else "Rank not listed",
        min_fee=0,
        max_fee=0,
        mode=", ".join([value for value in [ranking.city, ranking.state] if value]) or "Not listed",
        career_tags=career_tags,
        background_tags=infer_tags(text, BACKGROUND_KEYWORDS),
        degree_tags=career_tags,
        duration_years=Decimal("3.0"),
        description=f"NIRF {ranking.category} record with score {ranking.score or 'not listed'}",
        source="nirf_ranking",
        source_id=ranking.id,
    )


def parse_budget(text):
    if any(word in text for word in ["low fee", "low-fee", "affordable", "budget", "cheap"]):
        return 100000

    lakh_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:lakh|lac|lacs)", text)
    if lakh_match:
        return int(float(lakh_match.group(1)) * 100000)

    rupee_match = re.search(r"(?:₹|rs\.?|inr)\s*([\d,]+)", text)
    if rupee_match:
        return int(rupee_match.group(1).replace(",", ""))

    return None


def parse_duration_preference(text):
    if any(word in text for word in ["short", "fast", "quick", "1 year", "one year"]):
        return "short"
    if any(word in text for word in ["5 year", "five year", "integrated"]):
        return "long"
    return ""


def extract_query_context(query, profile=None):
    text = normalize(query)
    profile_text_parts = []

    if profile:
        profile_text_parts.extend(profile.interested_subjects or [])
        profile_text_parts.extend(profile.target_careers or [])
        profile_text_parts.extend(profile.skills or [])
        profile_text_parts.extend(
            [
                profile.current_stream,
                profile.current_education_status,
                profile.current_activity_type,
                profile.study_mode_preference,
                profile.career_goal_text,
            ]
        )
        if profile.max_annual_budget:
            profile_text_parts.append(f"inr {profile.max_annual_budget}")

    combined = " ".join([text] + [normalize(value) for value in profile_text_parts])

    career_intents = [
        key for key, keywords in INTENT_KEYWORDS.items() if contains_any(combined, keywords)
    ]
    backgrounds = [
        key for key, keywords in BACKGROUND_KEYWORDS.items() if contains_any(combined, keywords)
    ]
    mode_preferences = [
        mode for mode, keywords in MODE_KEYWORDS.items() if contains_any(combined, keywords)
    ]
    degree_preferences = [
        degree for degree, keywords in DEGREE_KEYWORDS.items() if contains_any(combined, keywords)
    ]

    return {
        "career_intents": unique(career_intents),
        "backgrounds": unique(backgrounds),
        "mode_preferences": unique(mode_preferences),
        "degree_preferences": unique(degree_preferences),
        "budget": parse_budget(combined),
        "duration_preference": parse_duration_preference(combined),
        "raw_text": combined,
    }


def openai_is_configured():
    return bool(getattr(settings, "OPENAI_API_KEY", ""))


def call_openai_json(system_prompt, prompt, timeout=20):
    body = json.dumps(
        {
            "model": getattr(settings, "OPENAI_MODEL", "gpt-4.1-mini"),
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": json.dumps(prompt, ensure_ascii=True),
                },
            ],
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        getattr(settings, "OPENAI_API_URL", "https://api.openai.com/v1/chat/completions"),
        data=body,
        headers={
            "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))

    content = payload["choices"][0]["message"]["content"].strip()
    if content.startswith("```"):
        content = content.strip("`")
        content = content.replace("json\n", "", 1).strip()
    return json.loads(content)


def keyword_payload_from_context(context):
    keywords = []
    for intent in context["career_intents"]:
        keywords.append(intent)
        keywords.extend(INTENT_KEYWORDS.get(intent, [])[:4])
    keywords.extend(context["backgrounds"])
    keywords.extend(context["mode_preferences"])
    keywords.extend(context["degree_preferences"])

    if context["budget"]:
        keywords.append("affordable")
    if context["duration_preference"]:
        keywords.append(context["duration_preference"])

    return unique([normalize(keyword) for keyword in keywords])[:12]


def extract_openai_keywords(query, profile=None):
    context = extract_query_context(query, profile=profile)
    fallback_keywords = keyword_payload_from_context(context)

    if not openai_is_configured():
        raise ValueError("OPENAI_API_KEY is not configured.")

    prompt = {
        "task": "Extract concise Indian higher-education programme search keywords from a student query.",
        "rules": [
            "Return strict JSON only.",
            "Use short searchable keywords, not sentences.",
            "Include career intent, course families, background, degree level, mode, budget, and duration when present.",
            "Prefer database-friendly terms such as law, llb, government, commerce, mba, data, analytics, bca, teaching, design.",
            "Do not invent personal facts that are not present.",
        ],
        "student_query": query,
        "profile_context": {
            "current_stream": getattr(profile, "current_stream", "") if profile else "",
            "education_status": getattr(profile, "current_education_status", "") if profile else "",
            "study_mode_preference": getattr(profile, "study_mode_preference", "") if profile else "",
            "target_careers": getattr(profile, "target_careers", []) if profile else [],
            "interested_subjects": getattr(profile, "interested_subjects", []) if profile else [],
            "skills": getattr(profile, "skills", []) if profile else [],
            "career_goal_text": getattr(profile, "career_goal_text", "") if profile else "",
        },
        "response_schema": {
            "keywords": ["law", "llb", "government", "commerce", "online"],
            "degree_type": "UG|PG|Diploma|",
            "mode": "Online|Distance|Regular|",
        },
    }
    try:
        parsed = call_openai_json(
            "You extract search keywords for an Indian course recommendation database. Return JSON only.",
            prompt,
        )
    except Exception as exc:
        raise RuntimeError(f"OpenAI keyword extraction failed: {exc}") from exc

    raw_keywords = parsed.get("keywords", [])
    if not isinstance(raw_keywords, list):
        raw_keywords = []

    keywords = unique(
        [
            normalize(keyword)
            for keyword in raw_keywords
            if 2 <= len(normalize(keyword)) <= 40
        ]
        + fallback_keywords
    )[:14]

    return {
        "keywords": keywords,
        "source": "openai" if keywords else "deterministic",
        "context": context,
        "message": "",
    }


def score_tag_overlap(programme_tags, requested_tags, points):
    if not requested_tags:
        return points * Decimal("0.45")

    matches = set(programme_tags or []).intersection(requested_tags)
    if not matches:
        return Decimal("0")

    ratio = Decimal(len(matches)) / Decimal(max(min(len(requested_tags), len(programme_tags or [])), 1))
    return min(Decimal(points), Decimal(points) * (Decimal("0.65") + Decimal("0.35") * ratio))


def score_mode(programme, context):
    preferences = context["mode_preferences"]
    if not preferences:
        return Decimal("8")

    programme_mode = normalize(programme.mode)
    if any(normalize(preference) in programme_mode for preference in preferences):
        return Decimal("15")

    if "Online" in preferences and "distance" in programme_mode:
        return Decimal("11")

    if "Distance" in preferences and "online" in programme_mode:
        return Decimal("11")

    return Decimal("6")


def score_fee(programme, context):
    budget = context["budget"]
    if not budget:
        return Decimal("10")

    if programme.min_fee <= budget:
        return Decimal("10")
    if programme.min_fee <= budget * 1.35:
        return Decimal("6")
    return Decimal("2")


def score_duration(programme, context):
    preference = context["duration_preference"]
    years = Decimal(programme.duration_years or 0)

    if not preference:
        return Decimal("10")
    if preference == "short" and years <= Decimal("2"):
        return Decimal("10")
    if preference == "long" and years >= Decimal("4"):
        return Decimal("10")
    return Decimal("4")


def score_degree(programme, context):
    preferences = context["degree_preferences"]
    degree_match = Decimal("0")

    if preferences:
        degree_match = Decimal("6") if programme.degree_type in preferences else Decimal("1")
    else:
        degree_match = Decimal("6")

    tag_bonus = score_tag_overlap(programme.degree_tags, context["career_intents"], 4)
    return min(Decimal("10"), degree_match + tag_bonus)


def build_reason(programme, context):
    intents = context["career_intents"]
    backgrounds = context["backgrounds"]

    if intents:
        intent_text = ", ".join(intent.replace("_", " ") for intent in intents[:3])
        return (
            f"You mentioned {intent_text}. {programme.program_name} connects well with "
            f"{programme.description or 'that direction'}."
        )

    if backgrounds:
        background_text = ", ".join(backgrounds[:2])
        return (
            f"Your {background_text} background can fit {programme.program_name}, "
            f"especially because it supports {programme.description or 'related career paths'}."
        )

    return (
        f"{programme.program_name} is a broad option from {programme.provider} that can match "
        "students still exploring their next academic path."
    )


def build_watch_out(programme, context):
    preferences = context["mode_preferences"]
    programme_mode = normalize(programme.mode)

    if preferences and not any(normalize(preference) in programme_mode for preference in preferences):
        preferred_text = "/".join(preferences).lower()
        return (
            f"You preferred {preferred_text}, but this programme is listed as {programme.mode}."
        )

    budget = context["budget"]
    if budget and programme.min_fee > budget:
        return "The starting fee may be higher than the budget hint in your query."

    return ""


def apply_filters(queryset, filters):
    degree_type = normalize(filters.get("degree_type"))
    mode = normalize(filters.get("mode"))
    fee_range = normalize(filters.get("fee_range"))
    duration = normalize(filters.get("duration"))
    provider = normalize(filters.get("provider"))

    if degree_type:
        queryset = queryset.filter(degree_type__iexact=degree_type)
    if mode:
        queryset = queryset.filter(mode__icontains=mode)
    if provider:
        queryset = queryset.filter(provider__icontains=provider)
    if fee_range == "under_100000":
        queryset = queryset.filter(min_fee__lte=100000)
    elif fee_range == "100000_250000":
        queryset = queryset.filter(min_fee__lte=250000, max_fee__gte=100000)
    elif fee_range == "above_250000":
        queryset = queryset.filter(max_fee__gte=250000)
    if duration == "short":
        queryset = queryset.filter(duration_years__lte=2)
    elif duration == "medium":
        queryset = queryset.filter(duration_years__gt=2, duration_years__lte=3)
    elif duration == "long":
        queryset = queryset.filter(duration_years__gt=3)

    return queryset


def rank_programmes(programmes, query, filters=None, profile=None):
    context = extract_query_context(query, profile=profile)
    results = []

    for programme in programmes:
        career = score_tag_overlap(programme.career_tags, context["career_intents"], 35)
        background = score_tag_overlap(programme.background_tags, context["backgrounds"], 20)
        mode = score_mode(programme, context)
        fee = score_fee(programme, context)
        duration = score_duration(programme, context)
        degree = score_degree(programme, context)
        total = career + background + mode + fee + duration + degree

        results.append(
            {
                "program_name": programme.program_name,
                "provider": programme.provider,
                "degree_type": programme.degree_type,
                "duration": programme.duration,
                "fee_range": programme.fee_range,
                "mode": programme.mode,
                "source": programme.source,
                "source_id": programme.source_id,
                "match_percentage": int(min(99, max(35, total.quantize(Decimal("1"))))),
                "reason": build_reason(programme, context),
                "watch_out": build_watch_out(programme, context),
                "score_breakdown": {
                    "career_intent": float(career),
                    "education_background": float(background),
                    "mode_preference": float(mode),
                    "fee_budget": float(fee),
                    "duration": float(duration),
                    "provider_degree_relevance": float(degree),
                },
            }
        )

    return sorted(results, key=lambda item: item["match_percentage"], reverse=True)
