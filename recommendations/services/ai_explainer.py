import json
import urllib.error
import urllib.request
from decimal import Decimal

from django.conf import settings


def recommendation_payload(item):
    programme, eligibility, filtered_item, score = item
    return {
        "programme_id": programme.id,
        "program_name": programme.program_name,
        "institution": programme.hei_name,
        "state": programme.state,
        "level": programme.level,
        "mode": programme.mode,
        "eligibility_status": eligibility.get("eligibility_status"),
        "eligibility_score": eligibility.get("eligibility_score"),
        "course_family": eligibility.get("detected_course_label"),
        "filter_status": filtered_item.get("filter_status"),
        "filter_reasons": filtered_item.get("filter_reasons", [])[:4],
        "filter_penalties": filtered_item.get("filter_penalties", [])[:4],
        "deterministic_score": str(score.get("score_breakdown", {}).get("deterministic_total", "")),
        "positive_factors": score.get("positive_factors", [])[:4],
        "negative_factors": score.get("negative_factors", [])[:4],
    }


def candidate_payload(profile):
    work_experiences = []

    for work in profile.work_experiences.all()[:3]:
        work_experiences.append(
            {
                "work_type": work.work_type,
                "industry": work.industry,
                "role_title": work.role_title,
                "company_or_brand_name": work.company_or_brand_name,
                "experience_years": str(work.experience_years or ""),
                "monthly_income_range": work.monthly_income_range,
                "skills_used": work.skills_used or [],
                "tools_used": work.tools_used or [],
                "description": work.description,
            }
        )

    return {
        "current_activity_type": profile.current_activity_type,
        "education_status": profile.current_education_status,
        "stream": profile.current_stream,
        "city": profile.city,
        "state": profile.state,
        "study_mode_preference": profile.study_mode_preference,
        "relocation_preference": profile.relocation_preference,
        "preferred_states": profile.preferred_states or [],
        "preferred_cities": profile.preferred_cities or [],
        "interested_subjects": profile.interested_subjects or [],
        "disliked_subjects": profile.disliked_subjects or [],
        "skills": profile.skills or [],
        "hobbies": profile.hobbies or [],
        "target_careers": profile.target_careers or [],
        "career_goal_text": profile.career_goal_text,
        "wants_fast_job": profile.wants_fast_job,
        "wants_government_job": profile.wants_government_job,
        "wants_abroad_option": profile.wants_abroad_option,
        "wants_business_or_startup": profile.wants_business_or_startup,
        "work_experiences": work_experiences,
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


def call_openai_for_scores(profile, scored_items):
    if not openai_is_configured():
        raise ValueError("OPENAI_API_KEY is not configured.")

    model = getattr(settings, "OPENAI_MODEL", "gpt-4.1-mini")
    limited_items = list(scored_items[: min(len(scored_items), 25)])

    prompt = {
        "task": "Score each programme from 0 to 10 as an LLM judgment layer for candidate-programme fit.",
        "rules": [
            "Use only the provided candidate and programme data.",
            "Do not invent programme names, fees, eligibility, placements, rankings, or recognition.",
            "0 means poor fit; 10 means excellent fit.",
            "Reward direct title/career/subject fit, realistic eligibility, mode/location fit, and clarity of path.",
            "Penalize insufficient data, vague/general programmes, weak mode/location fit, and risky eligibility.",
            "Return strict JSON only with key scores.",
        ],
        "candidate": candidate_payload(profile),
        "programmes": [recommendation_payload(item) for item in limited_items],
        "response_schema": {
            "scores": [
                {
                    "programme_id": 123,
                    "llm_score": 7.25,
                    "reasons": ["short reason 1", "short reason 2"],
                }
            ]
        },
    }

    try:
        parsed = call_openai_json(
            "You are a careful Indian higher-education recommendation evaluator. Return JSON only.",
            prompt,
        )
    except Exception as exc:
        raise RuntimeError(f"OpenAI scoring failed: {exc}") from exc
    score_map = {}

    for item in parsed.get("scores", []):
        programme_id = item.get("programme_id")
        if not programme_id:
            continue

        score = Decimal(str(item.get("llm_score", 0)))
        score = max(Decimal("0.00"), min(Decimal("10.00"), score)).quantize(Decimal("0.01"))
        reasons = [str(reason) for reason in item.get("reasons", [])[:3]]
        score_map[int(programme_id)] = {
            "score": score,
            "reasons": [f"LLM: {reason}" for reason in reasons],
        }

    return score_map, {
        "provider": "openai",
        "enabled": True,
        "used_for_scoring": bool(score_map),
        "max_weight": 10,
        "model": model,
        "scored_programme_count": len(score_map),
    }


def build_ai_style_explanation(profile, recommendations, llm_metadata=None):
    top_items = list(recommendations[:5])
    goals = ", ".join(profile.target_careers or []) or profile.career_goal_text or "not specified"
    subjects = ", ".join(profile.interested_subjects or []) or "not specified"
    llm_metadata = llm_metadata or {}

    summary = (
        "The recommendation engine compared your current education, stream, subjects, "
        "career goals, study-mode preference, location preference, and document readiness "
        "against trusted UGC-DEB programme data."
    )

    if llm_metadata.get("used_for_scoring"):
        summary += " OpenAI added up to 10 extra fit points across the shortlisted programmes."
    else:
        summary += " OpenAI scoring was not used for this run."

    if top_items:
        first = top_items[0]
        summary += (
            f" Your strongest current match is {first.programme.program_name} from "
            f"{first.programme.hei_name}, with a {first.match_percentage}% match."
        )

    next_steps = [
        "Verify the programme eligibility page on the university website before applying.",
        "Keep required marksheets and ID proof ready for admission verification.",
        "Shortlist 3-5 strong or good options, then compare fees, exam requirements, and deadlines.",
    ]

    if profile.missing_required_document_groups():
        next_steps.insert(0, "Upload missing required documents so final admission readiness is clearer.")

    if profile.wants_fast_job:
        next_steps.append("Add job-ready skills, internships, or certifications alongside the degree.")

    return {
        "summary": summary,
        "candidate_focus": {
            "career_goals": goals,
            "interested_subjects": subjects,
            "education_status": profile.get_current_education_status_display(),
            "stream": profile.get_current_stream_display(),
        },
        "next_steps": next_steps,
        "llm": llm_metadata,
    }
