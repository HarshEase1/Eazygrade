from django.db.models import Q
from django.http import HttpResponse
from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from accounts.authentication import CookieJWTAuthentication
from accounts.models import CandidateProfile
from institutions.models import UGCDEBProgramme
from recommendations.models import DemoProgramme
from recommendations.serializers import RecommendationRunSerializer
from recommendations.services.eligibility_engine import check_programme_eligibility
from recommendations.services.program_search import (
    extract_openai_keywords,
    rank_programmes,
    search_programme_from_demo,
    search_programme_from_ugc,
    search_programme_from_vendor,
)
from recommendations.services.recommendation_engine import run_recommendation_pipeline
from vendors.models import VendorCourse


def get_or_create_candidate_profile(user):
    profile, _ = CandidateProfile.objects.get_or_create(user=user)
    return profile


def normalize_for_matching(value):
    return str(value or "").strip().lower()


def diversify_programme_results(results, per_programme_limit=3):
    seen_counts = {}
    diversified = []

    for result in results:
        key = normalize_for_matching(result.get("program_name"))
        seen_counts[key] = seen_counts.get(key, 0) + 1

        if seen_counts[key] <= per_programme_limit:
            diversified.append(result)

    return diversified


def candidate_default_search_terms(profile):
    raw_values = []
    raw_values.extend(profile.interested_subjects or [])
    raw_values.extend(profile.target_careers or [])
    raw_values.extend(profile.skills or [])

    text = " ".join(normalize_for_matching(value) for value in raw_values)
    terms = []

    if "computer" in text or "software" in text or "programming" in text or "developer" in text:
        terms.extend(
            [
                "computer",
                "computer application",
                "computer science",
                "information technology",
                "data science",
                "software",
            ]
        )

    if "data" in text or "analytics" in text:
        terms.extend(["data", "analytics", "statistics", "computer"])

    if "business" in text or "management" in text or "entrepreneur" in text:
        terms.extend(["business", "management", "mba", "bba"])

    if "commerce" in text or "finance" in text or "account" in text:
        terms.extend(["commerce", "finance", "account"])

    if not terms:
        for value in raw_values:
            normalized_value = normalize_for_matching(value)
            if normalized_value:
                terms.append(normalized_value)

    deduped_terms = []

    for term in terms:
        if term and term not in deduped_terms:
            deduped_terms.append(term)

    return deduped_terms[:8]


def programme_relevance_score(programme, search_terms):
    if not search_terms:
        return 0

    programme_text = normalize_for_matching(
        " ".join(
            [
                programme.program_name,
                programme.hei_name,
                programme.level,
                programme.mode,
                programme.state,
            ]
        )
    )

    score = 0

    for term in search_terms:
        normalized_term = normalize_for_matching(term)

        if not normalized_term:
            continue

        if normalized_term in normalize_for_matching(programme.program_name):
            score += 20
        elif normalized_term in programme_text:
            score += 6

    return score


def serialize_programme(programme):
    return {
        "id": programme.id,
        "program_name": programme.program_name,
        "hei_name": programme.hei_name,
        "hei_type": programme.hei_type,
        "state": programme.state,
        "level": programme.level,
        "mode": programme.mode,
        "year": programme.year,
        "university_id": programme.university_id,
    }


def get_limit(request, default=40, maximum=100):
    raw_limit = request.query_params.get("limit") or request.data.get("limit") or default

    try:
        limit = int(raw_limit)
    except (TypeError, ValueError):
        limit = default

    return min(max(limit, 1), maximum)


def pdf_escape(value):
    return str(value or "").replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def wrap_text(text, max_chars=92):
    words = str(text or "").split()
    lines = []
    current = []

    for word in words:
        candidate = " ".join(current + [word])
        if len(candidate) > max_chars and current:
            lines.append(" ".join(current))
            current = [word]
        else:
            current.append(word)

    if current:
        lines.append(" ".join(current))

    return lines or [""]


def build_simple_pdf(lines):
    width = 612
    height = 792
    margin = 54
    y_start = height - margin
    line_height = 15
    pages = []
    current = []
    y = y_start

    for line in lines:
        if y < margin:
            pages.append(current)
            current = []
            y = y_start
        current.append((line, y))
        y -= line_height

    if current:
        pages.append(current)

    objects = ["<< /Type /Catalog /Pages 2 0 R >>"]
    kids = []
    content_refs = []

    for index, page_lines in enumerate(pages, start=1):
        page_obj_num = 3 + (index - 1) * 2
        content_obj_num = page_obj_num + 1
        kids.append(f"{page_obj_num} 0 R")
        content_refs.append((page_obj_num, content_obj_num, page_lines))

    objects.append(f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(pages)} >>")

    for page_obj_num, content_obj_num, page_lines in content_refs:
        stream_parts = ["BT", "/F1 10 Tf"]
        for line, y in page_lines:
            stream_parts.append(f"1 0 0 1 {margin} {y} Tm ({pdf_escape(line)}) Tj")
        stream_parts.append("ET")
        stream = "\n".join(stream_parts)
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {width} {height}] "
            f"/Resources << /Font << /F1 << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> >> >> "
            f"/Contents {content_obj_num} 0 R >>"
        )
        objects.append(f"<< /Length {len(stream.encode('utf-8'))} >>\nstream\n{stream}\nendstream")

    pdf = "%PDF-1.4\n"
    offsets = [0]
    for number, obj in enumerate(objects, start=1):
        offsets.append(len(pdf.encode("utf-8")))
        pdf += f"{number} 0 obj\n{obj}\nendobj\n"

    xref_offset = len(pdf.encode("utf-8"))
    pdf += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n"
    for offset in offsets[1:]:
        pdf += f"{offset:010d} 00000 n \n"
    pdf += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF"
    )
    return pdf.encode("utf-8")


def build_report_lines(run):
    profile = run.candidate
    recommendations = list(run.recommendations.select_related("programme").order_by("rank")[:12])
    explanation = run.ai_explanation or {}
    lines = [
        "EazyGrad Candidate Recommendation Report",
        "",
        f"Candidate: {profile.user.get_full_name() or profile.user.email}",
        f"Education: {profile.get_current_education_status_display()}",
        f"Stream: {profile.get_current_stream_display()}",
        f"Location: {', '.join([value for value in [profile.city, profile.state] if value]) or 'Not specified'}",
        f"Study mode preference: {profile.get_study_mode_preference_display()}",
        f"Career goals: {', '.join(profile.target_careers or []) or profile.career_goal_text or 'Not specified'}",
        f"Interested subjects: {', '.join(profile.interested_subjects or []) or 'Not specified'}",
        "",
        "Profile Readiness",
        f"Completion: {profile.profile_completion_percentage}%",
        f"Required documents ready: {'Yes' if profile.has_required_documents() else 'No'}",
    ]

    missing_groups = profile.missing_required_document_groups()
    if missing_groups:
        lines.append(f"Missing document groups: {missing_groups}")

    lines.extend(["", "Recommendation Summary"])
    for line in wrap_text(explanation.get("summary", "Recommendation analysis completed.")):
        lines.append(line)

    lines.extend(["", "Top Recommendations"])
    if not recommendations:
        lines.append("No recommendations were generated yet.")
    for recommendation in recommendations:
        programme = recommendation.programme
        lines.extend(
            [
                "",
                f"#{recommendation.rank} - {programme.program_name}",
                f"Institution: {programme.hei_name}, {programme.state}",
                f"Mode/level/year: {' / '.join([programme.mode, programme.level, programme.year])}",
                f"Match: {recommendation.match_percentage}% | Score: {recommendation.final_score} | Type: {recommendation.recommendation_type.replace('_', ' ')}",
                f"Eligibility: {recommendation.eligibility.get('eligibility_status', 'unknown').replace('_', ' ')}",
            ]
        )
        for factor in recommendation.positive_factors[:3]:
            for line in wrap_text(f"+ {factor}", 88):
                lines.append(line)
        for factor in recommendation.negative_factors[:2]:
            for line in wrap_text(f"- {factor}", 88):
                lines.append(line)

    lines.extend(["", "What To Do Next"])
    for step in explanation.get("next_steps", []):
        for line in wrap_text(f"- {step}", 88):
            lines.append(line)

    lines.extend(
        [
            "",
            "Important: This report is a recommendation aid. Always verify official eligibility, fees,",
            "admission dates, recognition, and placement details from the university before applying.",
        ]
    )
    return lines


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def public_program_search(request):
    query = str(request.data.get("query", "")).strip()
    use_profile_context = request.data.get("use_profile_context") is True
    filters = request.data.get("filters") or {}

    if not query:
        return Response(
            {"detail": "Query is required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    profile = None
    profile_message = ""

    if use_profile_context:
        try:
            authenticated = CookieJWTAuthentication().authenticate(request)
        except Exception:
            authenticated = None

        if authenticated:
            user, _ = authenticated
            profile = get_or_create_candidate_profile(user)
        else:
            profile_message = "Profile context unavailable. Continuing with your query only."

    keyword_payload = extract_openai_keywords(query, profile=profile)
    if keyword_payload.get("source") != "openai":
        return Response(
            {
                "detail": "OpenAI is not working.",
                "openai_working": False,
                "keyword_source": keyword_payload.get("source"),
                "error": keyword_payload.get("error") or keyword_payload.get("message"),
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    search_keywords = keyword_payload.get("keywords", [])
    degree_type = normalize_for_matching(filters.get("degree_type"))
    mode = normalize_for_matching(filters.get("mode"))
    provider = normalize_for_matching(filters.get("provider"))

    ugc_queryset = UGCDEBProgramme.objects.filter(is_active=True)
    vendor_queryset = VendorCourse.objects.select_related("vendor").none()
    demo_queryset = DemoProgramme.objects.filter(is_active=True)

    if degree_type:
        ugc_queryset = ugc_queryset.filter(level__icontains=degree_type)
        vendor_queryset = vendor_queryset.filter(level__icontains=degree_type)
        demo_queryset = demo_queryset.filter(degree_type__iexact=degree_type)
    if mode:
        ugc_queryset = ugc_queryset.filter(mode__icontains=mode)
        vendor_queryset = vendor_queryset.filter(mode__icontains=mode)
        demo_queryset = demo_queryset.filter(mode__icontains=mode)
    if provider:
        ugc_queryset = ugc_queryset.filter(hei_name__icontains=provider)
        vendor_queryset = vendor_queryset.filter(vendor__name__icontains=provider)
        demo_queryset = demo_queryset.filter(provider__icontains=provider)

    if search_keywords:
        ugc_keyword_query = Q()
        vendor_keyword_query = Q()
        demo_keyword_query = Q()

        for keyword in search_keywords:
            ugc_keyword_query |= Q(program_name__icontains=keyword)
            ugc_keyword_query |= Q(hei_name__icontains=keyword)
            ugc_keyword_query |= Q(level__icontains=keyword)
            ugc_keyword_query |= Q(mode__icontains=keyword)
            ugc_keyword_query |= Q(state__icontains=keyword)
            ugc_keyword_query |= Q(raw_data__icontains=keyword)
            vendor_keyword_query |= Q(title__icontains=keyword)
            vendor_keyword_query |= Q(vendor__name__icontains=keyword)
            vendor_keyword_query |= Q(vendor__provider_type__icontains=keyword)
            vendor_keyword_query |= Q(vendor__description__icontains=keyword)
            vendor_keyword_query |= Q(vendor__state__icontains=keyword)
            vendor_keyword_query |= Q(vendor__city__icontains=keyword)
            vendor_keyword_query |= Q(level__icontains=keyword)
            vendor_keyword_query |= Q(mode__icontains=keyword)
            vendor_keyword_query |= Q(duration__icontains=keyword)
            vendor_keyword_query |= Q(fees__icontains=keyword)
            vendor_keyword_query |= Q(subjects__icontains=keyword)
            vendor_keyword_query |= Q(syllabus__icontains=keyword)
            vendor_keyword_query |= Q(ideal_student__icontains=keyword)
            demo_keyword_query |= Q(program_name__icontains=keyword)
            demo_keyword_query |= Q(provider__icontains=keyword)
            demo_keyword_query |= Q(degree_type__icontains=keyword)
            demo_keyword_query |= Q(mode__icontains=keyword)
            demo_keyword_query |= Q(career_tags__icontains=keyword)
            demo_keyword_query |= Q(background_tags__icontains=keyword)
            demo_keyword_query |= Q(degree_tags__icontains=keyword)
            demo_keyword_query |= Q(description__icontains=keyword)

        ugc_queryset = ugc_queryset.filter(ugc_keyword_query)
        vendor_queryset = vendor_queryset.filter(vendor_keyword_query)
        demo_queryset = demo_queryset.filter(demo_keyword_query)

    ugc_programmes = list(ugc_queryset.order_by("-year", "program_name", "hei_name")[:100])
    vendor_programmes = list(vendor_queryset.order_by("title", "vendor__name")[:100])
    demo_programmes = list(demo_queryset.order_by("program_name", "provider")[:100])
    programmes = [
        *[search_programme_from_demo(programme) for programme in demo_programmes],
        *[search_programme_from_ugc(programme) for programme in ugc_programmes],
        *[search_programme_from_vendor(course) for course in vendor_programmes],
    ]
    results = rank_programmes(programmes, query, filters=filters, profile=profile)

    strong_results = [result for result in results if result["match_percentage"] >= 50]

    if strong_results:
        results = strong_results

    results = diversify_programme_results(results)[:10]

    return Response(
        {
            "query": query,
            "used_profile_context": bool(profile),
            "profile_message": profile_message,
            "search_keywords": search_keywords,
            "keyword_source": keyword_payload.get("source", "deterministic"),
            "keyword_message": keyword_payload.get("message", ""),
            "hallucination_guard": {
                "enabled": True,
                "rule": "Results are ranked only from seeded demo, UGC-DEB, and vendor records returned by the database.",
                "allowed_sources": ["demo_programme", "ugc_deb", "vendor_course"],
            },
            "matching_method": "OpenAI keyword extraction when configured, deterministic intent scoring, and database-only ranked results.",
            "count": len(results),
            "results": results,
        }
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def check_programme_eligibility_api(request, programme_id):
    profile = get_or_create_candidate_profile(request.user)

    try:
        programme = UGCDEBProgramme.objects.select_related("university").get(
            id=programme_id,
            is_active=True,
        )
    except UGCDEBProgramme.DoesNotExist:
        return Response(
            {"detail": "Programme not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    result = check_programme_eligibility(profile, programme)

    return Response(
        {
            "candidate_profile_id": profile.id,
            "programme": serialize_programme(programme),
            "eligibility": result,
        }
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def candidate_programme_eligibility_list(request):
    profile = get_or_create_candidate_profile(request.user)

    query_text = request.query_params.get("q", "").strip()
    state = request.query_params.get("state", "").strip()
    level = request.query_params.get("level", "").strip()
    mode = request.query_params.get("mode", "").strip()
    year = request.query_params.get("year", "").strip()
    eligibility_status = request.query_params.get("status", "").strip()

    limit = request.query_params.get("limit", "50")

    try:
        limit = int(limit)
    except ValueError:
        limit = 50

    limit = min(max(limit, 1), 200)

    queryset = UGCDEBProgramme.objects.select_related("university").filter(
        is_active=True,
    )

    search_terms = [query_text] if query_text else candidate_default_search_terms(profile)

    if query_text:
        queryset = queryset.filter(
            Q(program_name__icontains=query_text)
            | Q(hei_name__icontains=query_text)
            | Q(state__icontains=query_text)
            | Q(mode__icontains=query_text)
            | Q(level__icontains=query_text)
        )
    elif search_terms:
        profile_query = Q()

        for term in search_terms:
            profile_query |= Q(program_name__icontains=term)

        queryset = queryset.filter(profile_query)

    if state:
        queryset = queryset.filter(state__iexact=state)

    if level:
        queryset = queryset.filter(level__iexact=level)

    if mode:
        queryset = queryset.filter(mode__icontains=mode)

    if year:
        queryset = queryset.filter(year=year)

    queryset = queryset.order_by("-year", "program_name", "hei_name")[: limit * 10]

    results = []

    for programme in queryset:
        eligibility = check_programme_eligibility(profile, programme)

        if eligibility_status and eligibility["eligibility_status"] != eligibility_status:
            continue

        relevance_score = programme_relevance_score(programme, search_terms)

        results.append(
            {
                "programme": serialize_programme(programme),
                "eligibility": eligibility,
                "relevance_score": relevance_score,
            }
        )

        if len(results) >= limit * 3:
            break

    results.sort(
        key=lambda item: (
            item["relevance_score"],
            item["eligibility"]["eligibility_score"],
            item["programme"]["year"] or "",
        ),
        reverse=True,
    )

    results = results[:limit]

    status_counts = {}

    for item in results:
        status_key = item["eligibility"]["eligibility_status"]
        status_counts[status_key] = status_counts.get(status_key, 0) + 1

    return Response(
        {
            "candidate_profile_id": profile.id,
            "query": query_text,
            "applied_profile_terms": [] if query_text else search_terms,
            "count": len(results),
            "status_counts": status_counts,
            "results": results,
        }
    )


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def candidate_recommendation_analysis(request):
    profile = get_or_create_candidate_profile(request.user)
    force = request.query_params.get("force") == "1" or request.data.get("force") is True
    limit = get_limit(request)

    run, executed = run_recommendation_pipeline(
        profile,
        request.user,
        limit=limit,
        force=force,
    )
    serializer = RecommendationRunSerializer(run)
    data = serializer.data
    data["executed"] = executed
    data["cached"] = not executed
    data["download_report_url"] = "/api/recommendations/analysis/report/pdf/"
    return Response(data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def candidate_recommendation_report_pdf(request):
    profile = get_or_create_candidate_profile(request.user)
    run, _ = run_recommendation_pipeline(
        profile,
        request.user,
        limit=get_limit(request),
        force=False,
    )
    lines = build_report_lines(run)
    pdf_bytes = build_simple_pdf(lines)

    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = 'attachment; filename="eazygrad-recommendation-report.pdf"'
    return response
