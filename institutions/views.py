import re

from django.contrib.postgres.search import SearchHeadline, SearchQuery, SearchRank
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from institutions.models import SearchDocument


def normalize_text(value):
    if value is None:
        return ""

    value = str(value).lower()
    value = value.replace("&", " and ")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def year_sort_value(year):
    """
    Converts 2025-26 -> 2025
    Converts 2024-2025 -> 2024
    Empty year -> 0
    """
    if not year:
        return 0

    match = re.search(r"\d{4}", str(year))

    if not match:
        return 0

    return int(match.group())


def get_dedupe_key(document):
    """
    Dedupe only for UGC-DEB programme results.

    Same programme + same HEI + same level + same mode
    should show only latest year in search UI.
    """
    if document.entity_type != "ugc_deb_programme":
        return f"{document.entity_type}:{document.id}"

    metadata = document.metadata or {}

    program_name = metadata.get("program_name") or document.title
    hei_name = metadata.get("hei_name") or document.subtitle
    level = metadata.get("level") or document.level
    mode = metadata.get("mode") or document.mode
    state = document.state

    return "|".join(
        [
            "ugc_deb_programme",
            normalize_text(program_name),
            normalize_text(hei_name),
            normalize_text(level),
            normalize_text(mode),
            normalize_text(state),
        ]
    )


def source_filter_values(source):
    source = source.strip().lower()

    if source in ["ugc", "aishe", "ugc_aishe"]:
        return ["ugc", "aishe", "ugc_aishe"]

    return [source]


def serialize_search_document(document):
    return {
        "id": document.id,
        "entity_type": document.entity_type,
        "source_id": document.source_id,
        "title": document.title,
        "subtitle": document.subtitle,
        "headline": getattr(document, "headline", ""),
        "state": document.state,
        "district": document.district,
        "city": document.city,
        "category": document.category,
        "mode": document.mode,
        "level": document.level,
        "year": document.year,
        "rank": document.rank,
        "score": str(document.score) if document.score is not None else None,
        "source": document.source,
        "source_url": document.source_url,
        "metadata": document.metadata,
        "rank_score": round(float(getattr(document, "search_rank", 0)), 4),
    }


@api_view(["GET"])
@permission_classes([AllowAny])
def search_documents(request):
    query_text = request.query_params.get("q", "").strip()

    if not query_text:
        return Response(
            {
                "query": query_text,
                "count": 0,
                "dedupe": True,
                "pagination": {
                    "limit": 20,
                    "offset": 0,
                    "has_next": False,
                    "has_previous": False,
                    "next_offset": None,
                    "previous_offset": None,
                },
                "results": [],
            }
        )

    entity_type = request.query_params.get("type", "").strip()
    state = request.query_params.get("state", "").strip()
    city = request.query_params.get("city", "").strip()
    category = request.query_params.get("category", "").strip()
    mode = request.query_params.get("mode", "").strip()
    level = request.query_params.get("level", "").strip()
    year = request.query_params.get("year", "").strip()
    source = request.query_params.get("source", "").strip()

    # default dedupe true
    dedupe = request.query_params.get("dedupe", "true").lower() not in [
        "false",
        "0",
        "no",
    ]

    limit = request.query_params.get("limit", "20")
    offset = request.query_params.get("offset", "0")

    try:
        limit = int(limit)
    except ValueError:
        limit = 20

    limit = min(max(limit, 1), 100)

    try:
        offset = int(offset)
    except ValueError:
        offset = 0

    offset = max(offset, 0)

    search_query = SearchQuery(
        query_text,
        search_type="websearch",
        config="english",
    )

    queryset = SearchDocument.objects.filter(
        is_active=True,
        search_vector=search_query,
    )

    if entity_type:
        queryset = queryset.filter(entity_type=entity_type)

    if state:
        queryset = queryset.filter(state__iexact=state)

    if city:
        queryset = queryset.filter(city__iexact=city)

    if category:
        queryset = queryset.filter(category__iexact=category)

    if mode:
        queryset = queryset.filter(mode__icontains=mode)

    if level:
        queryset = queryset.filter(level__iexact=level)

    if year:
        queryset = queryset.filter(year=year)

    if source:
        queryset = queryset.filter(source__in=source_filter_values(source))

    page_end = offset + limit
    fetch_limit = page_end + 1

    if dedupe:
        fetch_limit = min((page_end + 1) * 5, 2000)

    queryset = (
        queryset.annotate(
            search_rank=SearchRank("search_vector", search_query),
            headline=SearchHeadline(
                "body",
                search_query,
                config="english",
                start_sel="<mark>",
                stop_sel="</mark>",
                max_words=35,
                min_words=10,
            ),
        )
        .order_by("-search_rank", "-score", "rank")[:fetch_limit]
    )

    documents = list(queryset)

    if dedupe:
        grouped = {}

        for document in documents:
            key = get_dedupe_key(document)

            existing = grouped.get(key)

            if existing is None:
                grouped[key] = document
                continue

            existing_rank = float(getattr(existing, "search_rank", 0) or 0)
            current_rank = float(getattr(document, "search_rank", 0) or 0)

            existing_year = year_sort_value(existing.year)
            current_year = year_sort_value(document.year)

            # Prefer better search rank.
            # If rank is same, prefer latest academic year.
            if current_rank > existing_rank:
                grouped[key] = document
            elif current_rank == existing_rank and current_year > existing_year:
                grouped[key] = document

        documents = list(grouped.values())

        documents.sort(
            key=lambda doc: (
                float(getattr(doc, "search_rank", 0) or 0),
                float(doc.score or 0),
                year_sort_value(doc.year),
            ),
            reverse=True,
        )

        has_next = len(documents) > page_end
        documents = documents[offset:page_end]
    else:
        has_next = len(documents) > page_end
        documents = documents[offset:page_end]

    results = [serialize_search_document(document) for document in documents]

    return Response(
        {
            "query": query_text,
            "count": len(results),
            "dedupe": dedupe,
            "pagination": {
                "limit": limit,
                "offset": offset,
                "has_next": has_next,
                "has_previous": offset > 0,
                "next_offset": page_end if has_next else None,
                "previous_offset": max(offset - limit, 0) if offset > 0 else None,
            },
            "results": results,
        }
    )
