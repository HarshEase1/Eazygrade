import hashlib
from decimal import Decimal

from institutions.models import NIRFRanking
from recommendations.services.eligibility_engine import detect_course_rule, normalize_text


CAREER_FAMILY_MAP = {
    "software": ["bca", "mca", "pg_diploma_computer", "bsc", "msc"],
    "developer": ["bca", "mca", "pg_diploma_computer"],
    "data": ["bca", "mca", "bsc", "msc", "pg_diploma_computer"],
    "analytics": ["bba", "mba", "bca", "mca"],
    "business": ["bba", "mba"],
    "management": ["bba", "mba"],
    "entrepreneur": ["bba", "mba"],
    "finance": ["bcom", "mcom", "mba"],
    "banking": ["bcom", "mcom", "mba"],
    "account": ["bcom", "mcom"],
    "government": ["ba", "bcom", "bsc", "ma", "mcom", "general"],
    "doctor": ["nursing", "pharmacy", "bsc"],
    "health": ["nursing", "pharmacy", "bsc", "msc"],
    "law": ["llb"],
    "legal": ["llb"],
    "teacher": ["bed", "ba", "bsc", "ma", "msc"],
}


def clamp(value, minimum=0, maximum=100):
    return max(minimum, min(maximum, value))


def decimal_score(value):
    return Decimal(str(value)).quantize(Decimal("0.01"))


def stable_micro_score(*values, maximum=1.75):
    raw = "|".join(str(value or "") for value in values).encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()
    bucket = int(digest[:8], 16) % 1000
    return Decimal(str((bucket / 999) * maximum)).quantize(Decimal("0.01"))


def profile_goal_text(profile):
    values = []
    values.extend(profile.target_careers or [])
    values.extend(profile.interested_subjects or [])
    values.extend(profile.skills or [])
    values.append(profile.career_goal_text or "")
    return normalize_text(" ".join(str(value) for value in values))

def detect_programme_subfamily(programme):
    name = normalize_text(programme.program_name)

    if any(term in name for term in ["data science", "data analytics", "analytics"]):
        return "data_analytics"

    if any(term in name for term in ["computer science", "computer application", "computer applications", "information technology"]):
        return "computer_it"

    if "statistics" in name:
        return "statistics"

    if "mathematics" in name or "maths" in name:
        return "mathematics"

    if any(term in name for term in ["business administration", "management"]):
        return "business_management"

    if any(term in name for term in ["commerce", "finance", "accounting"]):
        return "commerce_finance"

    if any(term in name for term in ["marketing", "digital marketing"]):
        return "marketing"

    return "general"

def score_career_goal(profile, family, programme=None):
    text = profile_goal_text(profile)
    score = Decimal("6.50")
    positives = []
    negatives = []

    subfamily = detect_programme_subfamily(programme) if programme else "general"

    if any(keyword in text for keyword in ["software", "developer", "programming", "coding"]):
        if family in ["bca", "mca", "pg_diploma_computer"] or subfamily == "computer_it":
            score = Decimal("22.00")
            positives.append("Software/developer goal directly matches computer/application programme.")
        elif family in ["bsc", "msc"] and subfamily in ["computer_it", "statistics"]:
            score = Decimal("18.00")
            positives.append("Software/data goal has a relevant science/computer connection.")
        else:
            negatives.append("Software/developer goal is not a direct match with this programme title.")

    elif any(keyword in text for keyword in ["data", "analytics", "data analyst", "data science"]):
        if subfamily in ["data_analytics", "statistics", "computer_it"]:
            score = Decimal("22.00")
            positives.append("Data/analytics goal directly matches this programme title.")
        elif subfamily == "mathematics":
            score = Decimal("15.50")
            positives.append("Mathematics can support data careers, but this is not a direct data programme.")
            negatives.append("For data career, Data Science, Analytics, Statistics, or Computer Science would be more direct.")
        elif family in ["bca", "mca", "pg_diploma_computer"]:
            score = Decimal("19.00")
            positives.append("Computer applications path can support data career progression.")
        else:
            score = Decimal("8.00")
            negatives.append("Data career goal is not strongly matched by this programme.")

    elif any(keyword in text for keyword in ["business", "management", "entrepreneur", "startup"]):
        if family in ["bba", "mba"] or subfamily == "business_management":
            score = Decimal("21.00")
            positives.append("Business/management goal directly matches this programme.")
        elif profile.wants_business_or_startup and family in ["bcom", "mcom"]:
            score = Decimal("16.50")
            positives.append("Commerce path can support business/startup goals.")
        else:
            negatives.append("Business goal is not a direct match with this programme.")

    elif any(keyword in text for keyword in ["finance", "banking", "account", "accounting"]):
        if family in ["bcom", "mcom", "mba"] or subfamily == "commerce_finance":
            score = Decimal("21.00")
            positives.append("Finance/accounting goal matches commerce or management path.")
        else:
            negatives.append("Finance goal is not directly matched by this programme.")

    elif profile.wants_government_job and family in ["ba", "bcom", "bsc", "ma", "mcom", "general"]:
        score = Decimal("17.50")
        positives.append("Government-job preference matches a broad degree path.")

    elif profile.wants_fast_job and family in ["bca", "pg_diploma_computer", "bcom", "bba"]:
        score = Decimal("16.00")
        positives.append("Fast-job preference fits a practical, skill-oriented path.")

    return min(score, Decimal("22.50")), positives, negatives

def score_academic_fit(profile, eligibility, family):
    score = Decimal("4.50")
    positives = []
    negatives = []
    stream = profile.current_stream

    if eligibility["eligibility_status"] in ["eligible", "likely_eligible"]:
        score += Decimal("3.50")
    elif eligibility["eligibility_status"] == "insufficient_data":
        score += Decimal("1.25")

    if family in ["bca", "mca", "pg_diploma_computer"] and (
        profile.computer_comfort or 0
    ) >= 4:
        score += Decimal("2.40")
        positives.append("Computer comfort supports this path.")

    if family in ["btech_engineering", "bsc", "msc"] and stream in ["pcm", "pcmb"]:
        score += Decimal("3.35")
        positives.append("Science/PCM background supports this path.")

    if family in ["nursing", "pharmacy"] and stream in ["pcb", "pcmb"]:
        score += Decimal("3.35")
        positives.append("Biology stream supports healthcare programmes.")

    if family in ["bcom", "mcom", "bba", "mba"] and stream == "commerce":
        score += Decimal("3.35")
        positives.append("Commerce stream supports business and finance programmes.")

    if family in ["btech_engineering", "nursing", "pharmacy", "bsc"] and stream in ["arts", "commerce"]:
        negatives.append("Stream may not satisfy stricter science-course admission rules.")

    return decimal_score(clamp(float(score), 0, 13.5)), positives, negatives


def score_interest_skill(profile, family):
    text = profile_goal_text(profile)
    score = Decimal("3.00")
    positives = []

    interest_keywords = {
        "computer": ["bca", "mca", "pg_diploma_computer", "bsc"],
        "math": ["btech_engineering", "bca", "bsc", "mca"],
        "commerce": ["bcom", "mcom", "bba", "mba"],
        "business": ["bba", "mba"],
        "biology": ["nursing", "pharmacy", "bsc"],
        "english": ["ba", "ma", "bed", "llb"],
        "statistics": ["bsc", "msc", "bca"],
        "application": ["bca", "mca", "pg_diploma_computer"],
    }

    for keyword, families in interest_keywords.items():
        if keyword in text and family in families:
            score += Decimal("1.45")
            positives.append(f"Interest in {keyword} supports this recommendation.")

    return decimal_score(clamp(float(score), 0, 9)), positives


def mode_match_detail(profile, programme):
    preferred = normalize_text(profile.study_mode_preference)
    mode = normalize_text(programme.mode)

    if preferred in ["", "any"]:
        return "flexible", "Candidate is open to any study mode."

    if preferred == "online":
        if "online" in mode:
            return "exact", "Online mode exactly matches candidate preference."
        if "odl" in mode or "distance" in mode or "open and distance" in mode:
            return "partial", "Programme is ODL/distance, which is remote-friendly but not exactly online."
        return "no_match", "Candidate prefers online, but this programme is not online or distance mode."

    if preferred == "distance":
        if "odl" in mode or "distance" in mode or "open and distance" in mode:
            return "exact", "Distance/ODL mode exactly matches candidate preference."
        if "online" in mode:
            return "partial", "Programme is online, which is remote-friendly but not exactly ODL."
        return "no_match", "Candidate prefers distance/ODL, but this programme is not distance mode."

    if preferred == "regular":
        if "regular" in mode or "campus" in mode or "offline" in mode:
            return "exact", "Regular/on-campus mode exactly matches candidate preference."
        return "no_match", "Candidate prefers regular/on-campus study, but this programme is online or distance mode."

    if preferred == "hybrid":
        if "hybrid" in mode:
            return "exact", "Hybrid mode exactly matches candidate preference."
        if "online" in mode or "odl" in mode or "distance" in mode:
            return "partial", "Programme is remote-friendly, but not exactly hybrid."
        return "no_match", "Candidate prefers hybrid, but this programme is not hybrid."

    return "flexible", "Study mode preference is flexible."


def score_mode_location(profile, programme):
    score = Decimal("3.20")
    positives = []
    negatives = []

    match_level, message = mode_match_detail(profile, programme)

    if match_level == "exact":
        score += Decimal("3.40")
        positives.append(message)
    elif match_level == "partial":
        score += Decimal("2.10")
        positives.append(message)
    elif match_level == "flexible":
        score += Decimal("1.80")
        positives.append(message)
    else:
        score -= Decimal("1.25")
        negatives.append(message)

    programme_state = normalize_text(programme.state)
    preferred_states = [normalize_text(value) for value in profile.preferred_states or []]
    preferred_cities = [normalize_text(value) for value in profile.preferred_cities or []]
    relocation = normalize_text(profile.relocation_preference)

    if preferred_states and programme_state in preferred_states:
        score += Decimal("2.40")
        positives.append("Programme state matches candidate preference.")
    elif programme_state and programme_state == normalize_text(profile.state):
        score += Decimal("1.75")
        positives.append("Programme is in candidate's current state.")
    elif relocation == "anywhere india":
        score += Decimal("1.50")
        positives.append("Candidate is open to studying anywhere in India.")
    elif relocation == "online only":
        score += Decimal("1.00")
        positives.append("Candidate prefers remote study; mode match is more important than location.")
    elif preferred_cities:
        negatives.append("Preferred city matching is not available for this programme yet.")

    return decimal_score(clamp(float(score), 0, 9)), positives, negatives

def score_institution_quality(programme):
    score = Decimal("4.00")
    positives = ["UGC-DEB programme source is treated as trusted source data."]
    negatives = []

    if programme.university and programme.university.is_fake:
        return 0, [], ["Linked university is marked as fake and should be avoided."]

    if programme.university:
        ranking = (
            NIRFRanking.objects.filter(university=programme.university)
            .order_by("-year", "rank")
            .first()
        )
        if ranking:
            score += Decimal("2.25")
            positives.append(f"NIRF ranking data is available for {ranking.year}.")

    if programme.year:
        score += Decimal("1.35")
        positives.append("Programme has year/session metadata.")

    if programme.university and normalize_text(programme.hei_name) == normalize_text(programme.university.name):
        score += Decimal("0.65")
        positives.append("Programme is linked to a matched university record.")

    return decimal_score(clamp(float(score), 0, 9)), positives, negatives


def score_programme_name_specificity(profile, programme, family):
    text = profile_goal_text(profile)
    name = normalize_text(programme.program_name)
    score = Decimal("0.00")
    positives = []
    negatives = []

    direct_goal_terms = {
        "data": [
            "data science",
            "data analytics",
            "analytics",
            "statistics",
            "computer science",
            "computer applications",
            "information technology",
        ],
        "software": [
            "computer science",
            "computer applications",
            "information technology",
            "software",
        ],
        "developer": [
            "computer science",
            "computer applications",
            "information technology",
            "software",
        ],
        "business": [
            "business administration",
            "management",
            "business analytics",
        ],
        "finance": [
            "commerce",
            "finance",
            "accounting",
        ],
        "marketing": [
            "marketing",
            "digital marketing",
            "mass communication",
        ],
    }

    for goal_keyword, programme_terms in direct_goal_terms.items():
        if goal_keyword in text:
            if any(term in name for term in programme_terms):
                score += Decimal("2.25")
                positives.append(f"Programme title directly matches the '{goal_keyword}' goal.")
            elif goal_keyword == "data" and "mathematics" in name:
                score += Decimal("0.45")
                positives.append("Mathematics can support data careers, but it is an indirect match.")
                negatives.append("This is not a direct Data Science/Analytics programme.")
            else:
                score -= Decimal("0.50")
                negatives.append(f"Programme title is not a direct match for '{goal_keyword}' goal.")

    if "combination" in name:
        score -= Decimal("0.35")
        negatives.append("Programme title is broad/combination-based, so fit is less specific.")

    return decimal_score(clamp(float(score), -1.5, 3)), positives, negatives

def score_programme(profile, programme, eligibility, filtered, llm_score=0, llm_reasons=None):
    rule = detect_course_rule(programme.program_name)
    family = eligibility.get("detected_course_family") or rule["family"]
    positives = []
    negatives = []

    eligibility_component = Decimal(str(eligibility.get("eligibility_score", 0))) * Decimal("0.27")
    if eligibility.get("eligibility_status") == "not_eligible":
        eligibility_component = min(eligibility_component, Decimal("7.00"))
    elif eligibility.get("eligibility_status") == "insufficient_data":
        eligibility_component = min(eligibility_component, Decimal("13.50"))

    career_score, career_positives, career_negatives = score_career_goal(
        profile,
        family,
        programme,
    )
    negatives.extend(career_negatives)
    positives.extend(career_positives)
    academic_score, academic_positives, academic_negatives = score_academic_fit(
        profile, eligibility, family
    )
    interest_score, interest_positives = score_interest_skill(profile, family)
    mode_score, mode_positives, mode_negatives = score_mode_location(profile, programme)
    quality_score, quality_positives, quality_negatives = score_institution_quality(programme)
    specificity_score, specificity_positives, specificity_negatives = (
        score_programme_name_specificity(
            profile,
            programme,
            family,
        )
    )
    micro_score = stable_micro_score(
        programme.program_name,
        programme.hei_name,
        programme.state,
        programme.mode,
        maximum=1.25,
    )
    llm_score = Decimal(str(clamp(float(llm_score or 0), 0, 10))).quantize(Decimal("0.01"))

    positives.extend(career_positives + academic_positives + interest_positives)
    positives.extend(mode_positives + quality_positives)
    positives.extend(specificity_positives)
    positives.extend(llm_reasons or [])

    negatives.extend(academic_negatives + mode_negatives + quality_negatives)
    negatives.extend(specificity_negatives)
    negatives.extend(filtered.get("filter_penalties", []))

    deterministic_score = (
        eligibility_component
        + Decimal(str(career_score))
        + Decimal(str(academic_score))
        + Decimal(str(interest_score))
        + Decimal(str(mode_score))
        + Decimal(str(quality_score))
        + specificity_score
        + micro_score
    )

    if filtered.get("filter_status") == "future_path":
        deterministic_score *= Decimal("0.72")
    elif filtered.get("filter_status") == "not_recommended":
        deterministic_score *= Decimal("0.45")

    if eligibility.get("eligibility_status") == "insufficient_data":
        deterministic_score = min(deterministic_score, Decimal("58.50"))

    deterministic_score = decimal_score(clamp(float(deterministic_score), 0, 90))
    final_score = decimal_score(clamp(float(deterministic_score + llm_score), 0, 100))
    match_percentage = final_score

    if filtered.get("filter_status") == "future_path":
        recommendation_type = "future_path"
    elif eligibility.get("eligibility_status") == "not_eligible" or final_score < 35:
        recommendation_type = "not_recommended"
    elif eligibility.get("eligibility_status") == "insufficient_data":
        recommendation_type = "backup_option"
    elif final_score >= Decimal("78"):
        recommendation_type = "strong_recommendation"
    elif final_score >= Decimal("60"):
        recommendation_type = "good_option"
    else:
        recommendation_type = "backup_option"

    return {
        "final_score": final_score,
        "match_percentage": match_percentage,
        "score_breakdown": {
            "eligibility": float(eligibility_component.quantize(Decimal("0.01"))),
            "career_goal": float(career_score),
            "academic_fit": float(academic_score),
            "interest_skill": float(interest_score),
            "mode_location": float(mode_score),
            "institution_quality": float(quality_score),
            "programme_specificity": float(specificity_score),
            "tie_breaker": float(micro_score),
            "llm": float(llm_score),
            "deterministic_total": float(deterministic_score),
        },
        "positive_factors": positives[:8],
        "negative_factors": negatives[:8],
        "recommendation_type": recommendation_type,
    }
