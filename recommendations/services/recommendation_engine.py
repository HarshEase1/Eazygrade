import hashlib
import json

from django.db import transaction
from django.utils import timezone

from accounts.models import CandidateProfile
from institutions.models import UGCDEBProgramme
from recommendations.models import RankedCourseRecommendation, RecommendationRun
from recommendations.services.ai_explainer import (
    build_ai_style_explanation,
    call_deepseek_for_scores,
)
from recommendations.services.course_filter import filter_programme_for_candidate
from recommendations.services.eligibility_engine import check_programme_eligibility
from recommendations.services.scoring_engine import score_programme


SECTION_NAMES = [
    "profile",
    "eligibility",
    "course_filter",
    "scoring",
    "ranking",
    "ai_analysis",
]

RECOMMENDATION_ALGORITHM_VERSION = "2026-06-30-scoring-v3-profile-work-mode"


def serialize_profile_for_signature(profile):
    records = []
    for record in profile.academic_records.prefetch_related("subject_scores").all():
        records.append(
            {
                "level": record.level,
                "status": record.status,
                "stream": record.stream,
                "percentage": str(record.percentage or ""),
                "passing_year": record.passing_year,
                "subjects": [
                    {
                        "name": subject.subject_name,
                        "percentage": str(subject.percentage or ""),
                    }
                    for subject in record.subject_scores.all()
                ],
            }
        )

    documents = list(
        profile.documents.exclude(file="")
        .order_by("document_type", "id")
        .values_list("document_type", flat=True)
    )

    work_experiences = []

    for work in profile.work_experiences.all():
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
                "proof_url": work.proof_url,
            }
        )

    return {
        "algorithm_version": RECOMMENDATION_ALGORITHM_VERSION,
        "profile_id": profile.id,
        "education_status": profile.current_education_status,
        "stream": profile.current_stream,
        "study_mode": profile.study_mode_preference,
        "relocation": profile.relocation_preference,
        "city": profile.city,
        "state": profile.state,
        "preferred_states": profile.preferred_states or [],
        "preferred_cities": profile.preferred_cities or [],
        "interested_subjects": profile.interested_subjects or [],
        "disliked_subjects": profile.disliked_subjects or [],
        "skills": profile.skills or [],
        "target_careers": profile.target_careers or [],
        "career_goal_text": profile.career_goal_text,
        "wants_fast_job": profile.wants_fast_job,
        "wants_government_job": profile.wants_government_job,
        "wants_abroad_option": profile.wants_abroad_option,
        "wants_business_or_startup": profile.wants_business_or_startup,
        "comfort": {
            "maths": profile.maths_comfort,
            "english": profile.english_comfort,
            "computer": profile.computer_comfort,
            "communication": profile.communication_comfort,
        },
        "academic_records": records,
        "documents": documents,
        "current_activity_type": profile.current_activity_type,
        "preferred_cities": profile.preferred_cities or [],
        "hobbies": profile.hobbies or [],
        "work_experiences": work_experiences,
    }


def build_profile_signature(profile):
    payload = serialize_profile_for_signature(profile)
    encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def initial_sections():
    return {
        name: {"status": "pending", "ran_once": False}
        for name in SECTION_NAMES
    }


def mark_section(run, section_name, status="completed", extra=None):
    sections = run.sections or initial_sections()
    section = sections.get(section_name, {})
    section.update(
        {
            "status": status,
            "ran_once": True,
            "updated_at": timezone.now().isoformat(),
        }
    )
    if extra:
        section.update(extra)
    sections[section_name] = section
    run.sections = sections
    run.save(update_fields=["sections", "updated_at"])


def candidate_profile_ready(profile):
    return profile.profile_completion_percentage >= 100 and profile.has_required_documents()


def programme_queryset_for_profile(profile, limit):
    base_queryset = (
        UGCDEBProgramme.objects.select_related("university")
        .filter(is_active=True)
        .order_by("-year", "program_name", "hei_name")
    )

    terms = []
    terms.extend(profile.interested_subjects or [])
    terms.extend(profile.target_careers or [])

    if terms:
        from django.db.models import Q

        query = Q()
        for term in terms[:8]:
            query |= Q(program_name__icontains=term) | Q(hei_name__icontains=term)
        queryset = base_queryset.filter(query)

        if queryset.exists():
            return queryset[: max(limit * 8, 80)]

    return base_queryset[: max(limit * 8, 80)]


def get_or_create_current_run(profile, user, force=False):
    signature = build_profile_signature(profile)

    if not force:
        run = (
            RecommendationRun.objects.filter(
                candidate=profile,
                requested_by=user,
                profile_signature=signature,
                status=RecommendationRun.Status.COMPLETED,
            )
            .order_by("-completed_at", "-id")
            .first()
        )
        if run:
            return run, False

    run = RecommendationRun.objects.create(
        candidate=profile,
        requested_by=user,
        profile_signature=signature,
        status=RecommendationRun.Status.PENDING,
        sections=initial_sections(),
    )
    return run, True


@transaction.atomic
def run_recommendation_pipeline(profile, user, limit=40, force=False):
    profile.refresh_from_db()
    run, created = get_or_create_current_run(profile, user, force=force)

    if not created and run.status == RecommendationRun.Status.COMPLETED:
        return run, False

    run.status = RecommendationRun.Status.RUNNING
    run.started_at = timezone.now()
    run.error_message = ""
    run.save(update_fields=["status", "started_at", "error_message", "updated_at"])

    try:
        profile_snapshot = serialize_profile_for_signature(profile)
        run.profile_snapshot = profile_snapshot
        run.save(update_fields=["profile_snapshot", "updated_at"])
        mark_section(run, "profile", extra={"is_ready": candidate_profile_ready(profile)})

        candidates = list(programme_queryset_for_profile(profile, limit))

        analysed = []
        for programme in candidates:
            eligibility = check_programme_eligibility(profile, programme)
            analysed.append((programme, eligibility))
        mark_section(run, "eligibility", extra={"programme_count": len(analysed)})

        filtered = []
        for programme, eligibility in analysed:
            filtered_item = filter_programme_for_candidate(profile, programme)
            if filtered_item["filter_status"] != "not_recommended":
                filtered.append((programme, eligibility, filtered_item))
        mark_section(run, "course_filter", extra={"candidate_count": len(filtered)})

        scored = []
        for programme, eligibility, filtered_item in filtered:
            score = score_programme(profile, programme, eligibility, filtered_item)
            scored.append((programme, eligibility, filtered_item, score))

        llm_score_map, llm_metadata = call_deepseek_for_scores(profile, scored)
        if llm_score_map:
            rescored = []
            for programme, eligibility, filtered_item, _score in scored:
                llm_item = llm_score_map.get(programme.id, {})
                score = score_programme(
                    profile,
                    programme,
                    eligibility,
                    filtered_item,
                    llm_score=llm_item.get("score", 0),
                    llm_reasons=llm_item.get("reasons", []),
                )
                rescored.append((programme, eligibility, filtered_item, score))
            scored = rescored

        mark_section(
            run,
            "scoring",
            extra={
                "scored_count": len(scored),
                "llm": llm_metadata,
            },
        )

        scored.sort(key=lambda item: (item[3]["final_score"], item[0].year or ""), reverse=True)
        RankedCourseRecommendation.objects.filter(run=run).delete()

        recommendations = []
        for rank, (programme, eligibility, filtered_item, score) in enumerate(scored[:limit], start=1):
            recommendations.append(
                RankedCourseRecommendation(
                    run=run,
                    candidate=profile,
                    programme=programme,
                    rank=rank,
                    final_score=score["final_score"],
                    match_percentage=score["match_percentage"],
                    recommendation_type=score["recommendation_type"],
                    filter_status=filtered_item["filter_status"],
                    filter_reasons=filtered_item["filter_reasons"],
                    filter_penalties=filtered_item["filter_penalties"],
                    eligibility=eligibility,
                    score_breakdown=score["score_breakdown"],
                    positive_factors=score["positive_factors"],
                    negative_factors=score["negative_factors"],
                )
            )

        RankedCourseRecommendation.objects.bulk_create(recommendations)
        mark_section(run, "ranking", extra={"recommendation_count": len(recommendations)})

        saved_recommendations = list(run.recommendations.select_related("programme")[:limit])
        run.ai_explanation = build_ai_style_explanation(
            profile,
            saved_recommendations,
            llm_metadata=llm_metadata,
        )
        run.save(update_fields=["ai_explanation", "updated_at"])
        mark_section(run, "ai_analysis")

        run.status = RecommendationRun.Status.COMPLETED
        run.completed_at = timezone.now()
        run.save(update_fields=["status", "completed_at", "updated_at"])
        return run, True
    except Exception as exc:
        run.status = RecommendationRun.Status.FAILED
        run.error_message = str(exc)
        run.save(update_fields=["status", "error_message", "updated_at"])
        raise
