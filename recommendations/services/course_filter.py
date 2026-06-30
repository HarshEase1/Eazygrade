from recommendations.services.eligibility_engine import detect_course_rule, normalize_text


UG_LEVEL_HINTS = [
    "bachelor",
    "b tech",
    "btech",
    "bachelor of technology",
    "bachelor of engineering",
    "bca",
    "bba",
    "bcom",
    "b com",
    "ba",
    "b a",
    "bsc",
    "b sc",
    "under graduate",
    "undergraduate",
]

PG_LEVEL_HINTS = [
    "master",
    "m tech",
    "mtech",
    "mca",
    "mba",
    "mcom",
    "m com",
    "ma",
    "m a",
    "msc",
    "m sc",
    "pg diploma",
    "post graduate",
    "postgraduate",
]

DIPLOMA_HINTS = [
    "diploma",
    "certificate",
    "certification",
]


WORK_ACTIVITY_TYPES = [
    "employed",
    "self_employed",
    "freelancer",
    "business_owner",
    "content_creator",
    "family_business",
]

STUDENT_ACTIVITY_TYPES = [
    "student",
    "college_student",
]


def profile_text(profile):
    values = []

    values.extend(profile.target_careers or [])
    values.extend(profile.interested_subjects or [])
    values.extend(profile.skills or [])
    values.extend(profile.hobbies or [])
    values.append(profile.career_goal_text or "")

    # Add work/business/freelancer/creator context if model exists.
    if hasattr(profile, "work_experiences"):
        for work in profile.work_experiences.all()[:3]:
            values.extend(
                [
                    work.work_type,
                    work.industry,
                    work.role_title,
                    work.company_or_brand_name,
                    work.description,
                ]
            )
            values.extend(work.skills_used or [])
            values.extend(work.tools_used or [])

    return normalize_text(" ".join(str(value) for value in values if value))


def detect_level(programme):
    level = normalize_text(programme.level)
    name = f" {normalize_text(programme.program_name)} "

    if "pg" in level or any(hint in name for hint in PG_LEVEL_HINTS):
        return "pg"

    if "ug" in level or any(hint in name for hint in UG_LEVEL_HINTS):
        return "ug"

    if any(hint in name for hint in DIPLOMA_HINTS):
        # PG Diploma should stay PG.
        if "pg diploma" in name or "post graduate diploma" in name:
            return "pg"
        return "diploma"

    return "general"


def profile_stage(profile):
    activity = normalize_text(getattr(profile, "current_activity_type", ""))
    education_status = normalize_text(profile.current_education_status)

    if activity in STUDENT_ACTIVITY_TYPES:
        return "student"

    if activity in WORK_ACTIVITY_TYPES:
        return "working"

    if education_status in ["class 10", "class 11", "class 12", "class 12 passed", "diploma"]:
        return "school_or_diploma"

    if education_status in ["ug", "undergraduate"]:
        return "college"

    if education_status in ["graduate", "working"]:
        return "graduate_or_working"

    return "unsure"


def matches_mode(profile, programme):
    preferred = normalize_text(profile.study_mode_preference)
    mode = normalize_text(programme.mode)

    if preferred in ["", "any"]:
        return True, "Candidate is open to any study mode."

    if preferred == "online":
        if "online" in mode:
            return True, "Programme mode exactly matches online preference."

        if "odl" in mode or "distance" in mode or "open and distance" in mode:
            return True, "Programme is ODL/distance. It is remote-friendly but not exactly online."

        return False, "Candidate prefers online, but this programme is not online or distance mode."

    if preferred == "distance":
        if "odl" in mode or "distance" in mode or "open and distance" in mode:
            return True, "Programme mode exactly matches distance/ODL preference."

        if "online" in mode:
            return True, "Programme is online. It is remote-friendly but not exactly ODL."

        return False, "Candidate prefers distance/ODL, but this programme is not distance mode."

    if preferred == "regular":
        if "regular" in mode or "campus" in mode or "offline" in mode:
            return True, "Programme mode matches regular/on-campus preference."

        return False, "Candidate prefers regular/on-campus study, but this programme is online or distance mode."

    if preferred == "hybrid":
        if "hybrid" in mode:
            return True, "Programme mode matches hybrid preference."

        if "online" in mode or "odl" in mode or "distance" in mode:
            return True, "Programme is remote-friendly, but not exactly hybrid."

        return False, "Candidate prefers hybrid, but this programme is not hybrid."

    return True, "Study mode preference is flexible."


def matches_location(profile, programme):
    relocation = normalize_text(profile.relocation_preference)
    programme_state = normalize_text(programme.state)
    candidate_state = normalize_text(profile.state)

    preferred_states = [
        normalize_text(value)
        for value in profile.preferred_states or []
        if normalize_text(value)
    ]

    preferred_cities = [
        normalize_text(value)
        for value in profile.preferred_cities or []
        if normalize_text(value)
    ]

    if relocation in ["", "unsure", "anywhere india"]:
        return True, "Candidate is open to programmes across India."

    if relocation == "online only":
        return True, "Online-only preference is handled through mode scoring."

    if preferred_states and programme_state in preferred_states:
        return True, "Programme state matches preferred state."

    if relocation == "same state" and programme_state and programme_state == candidate_state:
        return True, "Programme is in candidate's current state."

    # UGC-DEB programme data usually has state, not city.
    # Do not hard reject because city may not be available.
    if preferred_cities:
        return True, "Preferred city matching is not available for this programme, so state/mode are used instead."

    return False, "Programme location is outside the strongest location preference."


def career_alignment(profile, course_family):
    text = profile_text(profile)

    if not text:
        return False

    groups = {
        "software": ["bca", "mca", "pg_diploma_computer", "bsc", "msc"],
        "developer": ["bca", "mca", "pg_diploma_computer", "bsc", "msc"],
        "programming": ["bca", "mca", "pg_diploma_computer", "bsc", "msc"],
        "coding": ["bca", "mca", "pg_diploma_computer", "bsc", "msc"],
        "computer": ["bca", "mca", "pg_diploma_computer", "bsc", "msc"],
        "data": ["bca", "mca", "pg_diploma_computer", "bsc", "msc"],
        "analytics": ["bca", "mca", "pg_diploma_computer", "bsc", "msc", "bba", "mba"],
        "statistics": ["bsc", "msc"],

        "business": ["bba", "mba", "bcom", "mcom"],
        "management": ["bba", "mba"],
        "entrepreneur": ["bba", "mba", "bcom"],
        "startup": ["bba", "mba", "bcom"],

        "finance": ["bcom", "mcom", "mba"],
        "banking": ["bcom", "mcom", "mba"],
        "account": ["bcom", "mcom"],
        "accounting": ["bcom", "mcom"],

        "government": ["ba", "bcom", "bsc", "ma", "mcom", "general"],
        "civil service": ["ba", "bcom", "bsc", "ma", "mcom", "general"],

        "doctor": ["nursing", "pharmacy", "bsc", "msc"],
        "health": ["nursing", "pharmacy", "bsc", "msc"],
        "medical": ["nursing", "pharmacy", "bsc", "msc"],

        "law": ["llb"],
        "legal": ["llb"],

        "teacher": ["bed", "ba", "bsc", "ma", "msc"],
        "teaching": ["bed", "ba", "bsc", "ma", "msc"],

        "content": ["bba", "mba", "ba", "ma"],
        "youtube": ["bba", "mba", "ba", "ma"],
        "creator": ["bba", "mba", "ba", "ma"],
        "marketing": ["bba", "mba", "ba", "ma"],

        "design": ["ba", "ma", "bba"],
        "media": ["ba", "ma", "bba"],
    }

    for keyword, families in groups.items():
        if keyword in text and course_family in families:
            return True

    return False


def disliked_subject_match(profile, programme):
    disliked_subjects = [
        normalize_text(value)
        for value in profile.disliked_subjects or []
        if normalize_text(value)
    ]

    if not disliked_subjects:
        return False

    programme_text = normalize_text(programme.program_name)

    for disliked in disliked_subjects:
        # Avoid tiny accidental matches.
        if len(disliked) < 3:
            continue

        if disliked in programme_text:
            return True

    return False


def activity_based_reasons(profile, course_family):
    activity = normalize_text(getattr(profile, "current_activity_type", ""))
    reasons = []
    penalties = []

    if activity == "freelancer":
        if course_family in ["bca", "mca", "pg_diploma_computer", "bba", "mba"]:
            reasons.append("Freelancer profile can benefit from practical tech/business programmes.")
        else:
            penalties.append("This course is not directly connected to common freelancing growth paths.")

    elif activity in ["business owner", "business_owner", "family business", "family_business", "self employed", "self_employed"]:
        if course_family in ["bba", "mba", "bcom", "mcom"]:
            reasons.append("Business/self-employed profile aligns with management, commerce, or finance path.")
        else:
            penalties.append("This course is not a direct business-growth path.")

    elif activity in ["content creator", "content_creator"]:
        if course_family in ["bba", "mba", "ba", "ma"]:
            reasons.append("Creator profile can benefit from media, communication, marketing, or business paths.")
        else:
            penalties.append("This course is not directly connected to creator/media/business growth.")

    elif activity == "employed":
        if course_family in ["mba", "mca", "mcom", "msc", "pg_diploma_computer", "bed"]:
            reasons.append("Working professional profile can fit PG, online, distance, or career-upgrade programmes.")

    return reasons, penalties


def filter_programme_for_candidate(profile, programme):
    rule = detect_course_rule(programme.program_name)
    course_family = rule["family"]
    programme_level = detect_level(programme)

    reasons = []
    penalties = []
    status = "likely"

    education_status = profile.current_education_status
    stage = profile_stage(profile)

    # Stage-based filtering
    if stage in ["student", "school_or_diploma"]:
        if programme_level in ["ug", "diploma", "general"]:
            status = "immediate"
            reasons.append("This is an immediate UG/diploma-style option for the candidate stage.")
        elif programme_level == "pg":
            status = "future_path"
            reasons.append("This is a PG option and should be planned after graduation.")
            penalties.append("Future-path option for current education level.")

    elif stage == "college":
        if programme_level == "pg":
            status = "future_path"
            reasons.append("This PG option can be planned after completing graduation.")
            penalties.append("Future-path option until graduation is completed.")
        elif programme_level in ["ug", "diploma", "general"]:
            status = "likely"
            reasons.append("This can be considered, but current college progress should be reviewed.")

    elif stage in ["working", "graduate_or_working"]:
        if programme_level == "pg":
            status = "immediate"
            reasons.append("This PG programme matches a graduate/working candidate stage.")
        elif programme_level in ["diploma", "general"]:
            status = "likely"
            reasons.append("This can be considered as a skill upgrade or alternative pathway.")
        else:
            status = "likely"
            penalties.append("UG options may be less relevant if the candidate is already graduate/working.")

    else:
        reasons.append("Candidate stage is unclear, so this programme is kept for review.")

    # Career alignment
    if career_alignment(profile, course_family):
        reasons.append("Programme family aligns with candidate career goals.")
    else:
        penalties.append("Career-goal alignment is not a strong direct match.")

    # Work/business/creator context
    activity_reasons, activity_penalties = activity_based_reasons(profile, course_family)
    reasons.extend(activity_reasons)
    penalties.extend(activity_penalties)

    # Mode preference
    mode_ok, mode_reason = matches_mode(profile, programme)

    if mode_ok:
        reasons.append(mode_reason)
    else:
        penalties.append(mode_reason)

    # Location preference
    location_ok, location_reason = matches_location(profile, programme)

    if location_ok:
        reasons.append(location_reason)
    else:
        penalties.append(location_reason)

    # Disliked subject
    if disliked_subject_match(profile, programme):
        status = "not_recommended"
        penalties.append("Programme appears related to a disliked subject.")

    # Hard downgrade if not related and already weak
    if (
        status == "likely"
        and not career_alignment(profile, course_family)
        and len(activity_penalties) >= 1
    ):
        penalties.append("This is kept only as a low-priority exploratory option.")

    return {
        "programme": programme,
        "filter_status": status,
        "filter_reasons": reasons,
        "filter_penalties": penalties,
        "detected_level": programme_level,
        "detected_course_family": course_family,
        "detected_course_label": rule.get("label", ""),
    }