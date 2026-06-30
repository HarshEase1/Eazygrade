import json
import re
import urllib.error
import urllib.request
from decimal import Decimal

from django.conf import settings

from accounts.models import CandidateProfile


STOP_WORDS = {
    "and",
    "or",
    "the",
    "a",
    "an",
    "in",
    "of",
    "for",
    "to",
    "with",
    "by",
    "on",
    "course",
    "program",
    "programme",
    "student",
    "students",
}

STREAM_HINTS = {
    "law": ["arts", "commerce"],
    "legal": ["arts", "commerce"],
    "business": ["commerce"],
    "management": ["commerce"],
    "finance": ["commerce"],
    "commerce": ["commerce"],
    "computer": ["pcm", "pcmb", "commerce", "vocational"],
    "data": ["pcm", "pcmb", "commerce"],
    "analytics": ["pcm", "pcmb", "commerce"],
    "engineering": ["pcm", "pcmb"],
    "biology": ["pcb", "pcmb"],
    "medical": ["pcb", "pcmb"],
}


def tokenize(value):
    words = re.findall(r"[a-zA-Z][a-zA-Z0-9+#.]{2,}", str(value or "").lower())
    return {word for word in words if word not in STOP_WORDS}


def list_text(values):
    if isinstance(values, list):
        return " ".join(str(value) for value in values)
    return str(values or "")


def candidate_text(profile):
    latest_record = profile.academic_records.order_by("-is_primary", "-passing_year", "-id").first()
    subject_scores = latest_record.subject_scores.all() if latest_record else []
    subject_names = " ".join(score.subject_name for score in subject_scores)

    return " ".join(
        [
            list_text(profile.interested_subjects),
            list_text(profile.skills),
            list_text(profile.hobbies),
            list_text(profile.target_careers),
            profile.career_goal_text,
            subject_names,
            profile.current_stream,
            profile.current_education_status,
        ]
    )


def course_text(course):
    return " ".join(
        [
            course.title,
            course.level,
            course.mode,
            course.subjects,
            course.syllabus,
            course.ideal_student,
        ]
    )


def overlap_score(course_tokens, profile_tokens):
    if not course_tokens:
        return Decimal("0.00"), []

    matches = sorted(course_tokens.intersection(profile_tokens))
    ratio = len(matches) / max(len(course_tokens), 1)
    score = Decimal(str(min(34, ratio * 42))).quantize(Decimal("0.01"))
    return score, matches[:10]


def score_stream_fit(course_tokens, profile):
    matching_streams = set()

    for token in course_tokens:
        matching_streams.update(STREAM_HINTS.get(token, []))

    if not matching_streams:
        return Decimal("8.00"), ["Course accepts a broad student profile."]

    if profile.current_stream in matching_streams:
        return Decimal("14.00"), ["Candidate stream aligns with the course area."]

    if profile.current_stream == "unsure":
        return Decimal("6.00"), ["Candidate stream is not confirmed yet."]

    return Decimal("3.50"), ["Candidate stream may need manual review for this course."]


def score_mode_fit(course, profile):
    course_mode = str(course.mode or "").lower()
    preferred = str(profile.study_mode_preference or "").lower()

    if preferred in ["", "any"]:
        return Decimal("8.00"), ["Candidate is open to different study modes."]

    if preferred in course_mode:
        return Decimal("12.00"), ["Study mode matches candidate preference."]

    if preferred == "online" and any(term in course_mode for term in ["distance", "odl"]):
        return Decimal("9.00"), ["Remote-friendly mode partially matches online preference."]

    if preferred == "distance" and "online" in course_mode:
        return Decimal("9.00"), ["Online mode partially matches distance preference."]

    return Decimal("4.00"), ["Study mode may not be the candidate's first choice."]


def score_location(profile, vendor):
    if not profile.state and not profile.preferred_states:
        return Decimal("5.00"), []

    vendor_state = str(vendor.state or "").lower()
    preferred_states = [str(value).lower() for value in profile.preferred_states or []]

    if vendor_state and vendor_state in preferred_states:
        return Decimal("8.00"), ["Vendor state matches candidate preference."]

    if vendor_state and vendor_state == str(profile.state or "").lower():
        return Decimal("7.00"), ["Vendor is in the candidate's state."]

    if profile.relocation_preference in ["anywhere_india", "online_only"]:
        return Decimal("6.00"), ["Candidate is flexible about location."]

    return Decimal("2.50"), []


def score_academics(profile):
    record = profile.academic_records.order_by("-is_primary", "-passing_year", "-id").first()

    if not record:
        return Decimal("4.00"), ["Academic details are limited."]

    if record.percentage is not None:
        percentage = float(record.percentage)
        score = min(12, max(4, percentage / 8))
        return Decimal(str(score)).quantize(Decimal("0.01")), [
            f"Latest academic percentage is {record.percentage}%."
        ]

    if record.cgpa is not None and record.max_cgpa:
        percentage = (float(record.cgpa) / float(record.max_cgpa)) * 100
        score = min(12, max(4, percentage / 8))
        return Decimal(str(score)).quantize(Decimal("0.01")), [
            f"Latest CGPA is {record.cgpa}/{record.max_cgpa}."
        ]

    return Decimal("5.00"), ["Academic score is not fully available."]


def recommendation_type(match_percentage):
    if match_percentage >= 82:
        return "top_candidate"
    if match_percentage >= 68:
        return "strong_candidate"
    if match_percentage >= 52:
        return "possible_candidate"
    return "low_priority"


def candidate_payload(profile, percentage, reasons):
    return {
        "id": profile.id,
        "name": profile.user.get_full_name() or profile.user.email,
        "email": profile.user.email,
        "city": profile.city,
        "state": profile.state,
        "current_activity_type": profile.current_activity_type,
        "current_education_status": profile.current_education_status,
        "current_stream": profile.current_stream,
        "interested_subjects": profile.interested_subjects or [],
        "skills": profile.skills or [],
        "target_careers": profile.target_careers or [],
        "match_percentage": percentage,
        "recommendation_type": recommendation_type(percentage),
        "reasons": reasons[:8],
    }


def clean_json_text(value):
    text = str(value or "").strip()

    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text, flags=re.IGNORECASE).strip()
        text = re.sub(r"```$", "", text).strip()

    start = text.find("{")
    end = text.rfind("}")

    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]

    return text


def candidate_analysis_payload(candidate):
    return {
        "name": candidate.get("name"),
        "location": ", ".join(
            value for value in [candidate.get("city"), candidate.get("state")] if value
        ),
        "education_status": candidate.get("current_education_status"),
        "stream": candidate.get("current_stream"),
        "interested_subjects": candidate.get("interested_subjects", [])[:6],
        "skills": candidate.get("skills", [])[:6],
        "target_careers": candidate.get("target_careers", [])[:4],
        "match_percentage": candidate.get("match_percentage"),
        "recommendation_type": candidate.get("recommendation_type"),
        "reasons": candidate.get("reasons", [])[:4],
    }


def deepseek_error_response(message, error=None):
    response = {
        "enabled": True,
        "used": False,
        "message": message,
    }

    if error:
        response["error"] = str(error)[:1200]

    return response


def rank_candidates_for_course(course, limit=25):
    candidates = (
        CandidateProfile.objects.select_related("user")
        .prefetch_related("academic_records__subject_scores", "work_experiences")
        .filter(user__is_active=True)
    )
    course_tokens = tokenize(course_text(course))
    ranked = []

    for profile in candidates:
        profile_tokens = tokenize(candidate_text(profile))
        text_score, matched_terms = overlap_score(course_tokens, profile_tokens)
        stream_score, stream_reasons = score_stream_fit(course_tokens, profile)
        mode_score, mode_reasons = score_mode_fit(course, profile)
        location_score, location_reasons = score_location(profile, course.vendor)
        academic_score, academic_reasons = score_academics(profile)
        completion_score = Decimal(str(min(10, profile.profile_completion_percentage / 10))).quantize(Decimal("0.01"))

        total = text_score + stream_score + mode_score + location_score + academic_score + completion_score
        percentage = int(min(100, round(float(total))))
        reasons = []

        if matched_terms:
            reasons.append(f"Matches course terms: {', '.join(matched_terms[:8])}.")

        reasons.extend(stream_reasons)
        reasons.extend(mode_reasons)
        reasons.extend(location_reasons)
        reasons.extend(academic_reasons)

        if profile.profile_completion_percentage >= 80:
            reasons.append("Candidate profile is detailed enough for outreach.")

        if percentage >= 35:
            ranked.append(candidate_payload(profile, percentage, reasons))

    ranked.sort(key=lambda item: item["match_percentage"], reverse=True)
    return ranked[:limit]


def deepseek_course_analysis(course, matches):
    if not getattr(settings, "DEEPSEEK_API_KEY", ""):
        return {
            "enabled": False,
            "used": False,
            "message": "DeepSeek is not configured; deterministic candidate ranking is shown.",
        }

    prompt = {
        "task": "Summarize the top candidate fit for a vendor course.",
        "course": {
            "title": course.title,
            "level": course.level,
            "mode": course.mode,
            "subjects": course.subjects,
            "syllabus": course.syllabus,
            "ideal_student": course.ideal_student,
        },
        "top_candidates": [candidate_analysis_payload(candidate) for candidate in matches[:10]],
        "response_schema": {
            "summary": "short summary",
            "contact_priority": ["candidate reason"],
            "notes": ["short note"],
        },
    }
    body = json.dumps(
        {
            "model": getattr(settings, "DEEPSEEK_MODEL", "deepseek-chat"),
            "temperature": 0.1,
            "max_tokens": 900,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You explain candidate-course fit for institute admissions teams. "
                        "Return strict JSON only with summary, contact_priority, and notes."
                    ),
                },
                {"role": "user", "content": json.dumps(prompt, ensure_ascii=True)},
            ],
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        getattr(settings, "DEEPSEEK_API_URL", "https://api.deepseek.com/chat/completions"),
        data=body,
        headers={
            "Authorization": f"Bearer {settings.DEEPSEEK_API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            payload = json.loads(response.read().decode("utf-8"))
        content = payload["choices"][0]["message"]["content"]
        parsed = json.loads(clean_json_text(content))
        return {
            "enabled": True,
            "used": True,
            "summary": parsed.get("summary") or "DeepSeek analysis is ready.",
            "contact_priority": parsed.get("contact_priority") or [],
            "notes": parsed.get("notes") or [],
        }
    except urllib.error.HTTPError as exc:
        try:
            detail = exc.read().decode("utf-8", errors="replace")
        except OSError:
            detail = str(exc)

        return deepseek_error_response(
            "DeepSeek analysis failed; deterministic candidate ranking is shown.",
            f"HTTP {exc.code}: {detail}",
        )
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError, KeyError, ValueError) as exc:
        return deepseek_error_response(
            "DeepSeek analysis failed; deterministic candidate ranking is shown.",
            exc,
        )
