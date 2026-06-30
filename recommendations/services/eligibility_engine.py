import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from accounts.models import CandidateProfile


def normalize_text(value):
    if value is None:
        return ""

    value = str(value).lower()
    value = value.replace("&", " and ")
    value = value.replace(".", "")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


SUBJECT_ALIASES = {
    "mathematics": [
        "mathematics",
        "math",
        "maths",
        "applied mathematics",
        "business mathematics",
    ],
    "physics": [
        "physics",
    ],
    "chemistry": [
        "chemistry",
    ],
    "biology": [
        "biology",
        "bio",
        "botany",
        "zoology",
        "life science",
        "biotechnology",
    ],
    "computer": [
        "computer",
        "computer science",
        "informatics practices",
        "information technology",
        "it",
        "programming",
    ],
    "commerce": [
        "commerce",
        "accountancy",
        "accounts",
        "business studies",
        "economics",
    ],
    "english": [
        "english",
        "english core",
        "english language",
    ],
    "sanskrit": [
        "sanskrit",
        "shastri",
        "vyakarana",
        "sahitya",
        "sahityam",
        "jyotisha",
        "jyotish",
        "ved",
        "veda",
    ],
}


QUALIFICATION_RANKS = {
    "class_10": 10,
    "class_11": 11,
    "class_12": 12,
    "class_12_passed": 12,
    "diploma": 12,
    "ug": 16,
    "graduate": 16,
    "pg": 18,
    "working": 16,
    "unsure": 0,
}


COURSE_RULES = [
    {
        "family": "btech_engineering",
        "label": "B.Tech / Engineering",
        "patterns": [
            "bachelor of technology",
            "b tech",
            "btech",
            "bachelor of engineering",
            "engineering",
        ],
        "required_rank": 12,
        "required_qualification": "Class 12",
        "allowed_streams": ["pcm", "pcmb"],
        "strict_stream": True,
        "required_subject_groups": [["mathematics"], ["physics"]],
        "preferred_subject_groups": [["chemistry"], ["computer"]],
        "min_percentage": 45,
        "future_path": "Class 12 PCM → B.Tech / BE",
    },
    {
        "family": "bca",
        "label": "BCA",
        "patterns": [
            "bachelor of computer applications",
            "bachelor of computer application",
            "bca",
        ],
        "required_rank": 12,
        "required_qualification": "Class 12",
        "allowed_streams": ["pcm", "pcmb", "commerce", "arts", "vocational", "other"],
        "strict_stream": False,
        "required_subject_groups": [],
        "preferred_subject_groups": [["mathematics"], ["computer"]],
        "min_percentage": 45,
        "future_path": "Class 12 → BCA → MCA / Software / Data roles",
    },
    {
        "family": "mca",
        "label": "MCA",
        "patterns": [
            "master of computer applications",
            "master of computer application",
            "mca",
        ],
        "required_rank": 16,
        "required_qualification": "Graduation",
        "allowed_streams": [],
        "strict_stream": False,
        "required_subject_groups": [],
        "preferred_subject_groups": [["mathematics"], ["computer"]],
        "min_percentage": 45,
        "future_path": "Class 12 → BCA / BSc CS / BTech → MCA",
    },
    {
        "family": "pg_diploma_computer",
        "label": "PG Diploma in Computer Applications",
        "patterns": [
            "post graduate diploma in computer application",
            "post graduate diploma in computer applications",
            "pg diploma in computer application",
            "pgdca",
        ],
        "required_rank": 16,
        "required_qualification": "Graduation",
        "allowed_streams": [],
        "strict_stream": False,
        "required_subject_groups": [],
        "preferred_subject_groups": [["computer"], ["mathematics"]],
        "min_percentage": 45,
        "future_path": "Graduation → PG Diploma in Computer Applications",
    },
    {
        "family": "mba",
        "label": "MBA",
        "patterns": [
            "master of business administration",
            "masters of business administration",
            "mba",
        ],
        "required_rank": 16,
        "required_qualification": "Graduation",
        "allowed_streams": [],
        "strict_stream": False,
        "required_subject_groups": [],
        "preferred_subject_groups": [["commerce"], ["english"]],
        "min_percentage": 50,
        "future_path": "Graduation → MBA",
    },
    {
        "family": "sanskrit_acharya",
        "label": "Acharya / Sanskrit Studies",
        "patterns": [
            "acharya",
            "sanskrit",
            "vyakarana",
            "sahityam",
            "sahitya",
            "jyotisha",
            "shastram",
            "shastri",
        ],
        "required_rank": 16,
        "required_qualification": "Relevant graduation in Sanskrit / Shastri",
        "allowed_streams": [],
        "strict_stream": False,
        "required_subject_groups": [["sanskrit"]],
        "preferred_subject_groups": [["sanskrit"]],
        "min_percentage": 45,
        "future_path": "Sanskrit / Shastri background → Acharya",
    },
    {
        "family": "bba",
        "label": "BBA",
        "patterns": [
            "bachelor of business administration",
            "bba",
            "business administration",
        ],
        "required_rank": 12,
        "required_qualification": "Class 12",
        "allowed_streams": ["pcm", "pcmb", "commerce", "arts", "vocational", "other"],
        "strict_stream": False,
        "required_subject_groups": [],
        "preferred_subject_groups": [["commerce"], ["english"]],
        "min_percentage": 45,
        "future_path": "Class 12 → BBA → MBA / Management roles",
    },
    {
        "family": "bcom",
        "label": "B.Com",
        "patterns": [
            "bachelor of commerce",
            "b com",
            "bcom",
        ],
        "required_rank": 12,
        "required_qualification": "Class 12",
        "allowed_streams": ["commerce", "pcm", "pcmb", "arts", "other"],
        "strict_stream": False,
        "required_subject_groups": [],
        "preferred_subject_groups": [["commerce"], ["mathematics"]],
        "min_percentage": 45,
        "future_path": "Class 12 → B.Com → M.Com / MBA / Finance",
    },
    {
        "family": "mcom",
        "label": "M.Com",
        "patterns": [
            "master of commerce",
            "m com",
            "mcom",
        ],
        "required_rank": 16,
        "required_qualification": "Graduation",
        "allowed_streams": [],
        "strict_stream": False,
        "required_subject_groups": [],
        "preferred_subject_groups": [["commerce"]],
        "min_percentage": 45,
        "future_path": "B.Com / Graduation → M.Com",
    },
    {
        "family": "ba",
        "label": "BA",
        "patterns": [
            "bachelor of arts",
            "b a",
            "ba",
        ],
        "required_rank": 12,
        "required_qualification": "Class 12",
        "allowed_streams": ["pcm", "pcmb", "commerce", "arts", "vocational", "other"],
        "strict_stream": False,
        "required_subject_groups": [],
        "preferred_subject_groups": [["english"]],
        "min_percentage": 40,
        "future_path": "Class 12 → BA",
    },
    {
        "family": "ma",
        "label": "MA",
        "patterns": [
            "master of arts",
            "m a",
            "ma",
        ],
        "required_rank": 16,
        "required_qualification": "Graduation",
        "allowed_streams": [],
        "strict_stream": False,
        "required_subject_groups": [],
        "preferred_subject_groups": [["english"]],
        "min_percentage": 45,
        "future_path": "Graduation → MA",
    },
    {
        "family": "bsc",
        "label": "B.Sc",
        "patterns": [
            "bachelor of science",
            "b sc",
            "bsc",
        ],
        "required_rank": 12,
        "required_qualification": "Class 12",
        "allowed_streams": ["pcm", "pcb", "pcmb"],
        "strict_stream": True,
        "required_subject_groups": [],
        "preferred_subject_groups": [["mathematics"], ["biology"], ["physics"], ["chemistry"]],
        "min_percentage": 45,
        "future_path": "Class 12 Science → B.Sc",
    },
    {
        "family": "msc",
        "label": "M.Sc",
        "patterns": [
            "master of science",
            "m sc",
            "msc",
        ],
        "required_rank": 16,
        "required_qualification": "Graduation",
        "allowed_streams": [],
        "strict_stream": False,
        "required_subject_groups": [],
        "preferred_subject_groups": [["mathematics"], ["biology"], ["physics"], ["chemistry"]],
        "min_percentage": 45,
        "future_path": "B.Sc / relevant graduation → M.Sc",
    },
    {
        "family": "bed",
        "label": "B.Ed",
        "patterns": [
            "bachelor of education",
            "b ed",
            "bed",
        ],
        "required_rank": 16,
        "required_qualification": "Graduation",
        "allowed_streams": [],
        "strict_stream": False,
        "required_subject_groups": [],
        "preferred_subject_groups": [["english"]],
        "min_percentage": 50,
        "future_path": "Graduation → B.Ed → Teaching",
    },
    {
        "family": "llb",
        "label": "LLB",
        "patterns": [
            "bachelor of law",
            "bachelor of laws",
            "llb",
            "law",
        ],
        "required_rank": 16,
        "required_qualification": "Graduation for 3-year LLB",
        "allowed_streams": [],
        "strict_stream": False,
        "required_subject_groups": [],
        "preferred_subject_groups": [["english"]],
        "min_percentage": 45,
        "future_path": "Graduation → LLB OR Class 12 → Integrated BA LLB",
    },
    {
        "family": "pharmacy",
        "label": "Pharmacy",
        "patterns": [
            "pharmacy",
            "b pharm",
            "bpharm",
            "pharmaceutical",
        ],
        "required_rank": 12,
        "required_qualification": "Class 12 Science",
        "allowed_streams": ["pcm", "pcb", "pcmb"],
        "strict_stream": True,
        "required_subject_groups": [["physics"], ["chemistry"]],
        "preferred_subject_groups": [["mathematics"], ["biology"]],
        "min_percentage": 45,
        "future_path": "Class 12 PCM/PCB → Pharmacy",
    },
    {
        "family": "nursing",
        "label": "Nursing",
        "patterns": [
            "nursing",
        ],
        "required_rank": 12,
        "required_qualification": "Class 12 PCB",
        "allowed_streams": ["pcb", "pcmb"],
        "strict_stream": True,
        "required_subject_groups": [["biology"], ["chemistry"]],
        "preferred_subject_groups": [["physics"], ["english"]],
        "min_percentage": 45,
        "future_path": "Class 12 PCB → Nursing",
    },
]


DEFAULT_RULE = {
    "family": "general",
    "label": "General Programme",
    "patterns": [],
    "required_rank": 12,
    "required_qualification": "Class 12",
    "allowed_streams": [],
    "strict_stream": False,
    "required_subject_groups": [],
    "preferred_subject_groups": [],
    "min_percentage": None,
    "future_path": "Check official university eligibility before admission.",
}


@dataclass
class CandidateSnapshot:
    profile: CandidateProfile
    highest_rank: float
    highest_label: str
    stream: str
    class_12_percentage: Optional[Decimal]
    ug_percentage: Optional[Decimal]
    subject_names: set
    is_class_12_appearing: bool
    has_required_documents: bool
    missing_required_documents: list


def get_academic_rank(level, status):
    base_rank = QUALIFICATION_RANKS.get(level, 0)

    if status == "passed":
        return float(base_rank)

    if status in ["appearing", "result_awaited"]:
        return float(base_rank) - 0.5

    return 0


def get_subject_names_from_record(record):
    subject_names = set()

    if not record:
        return subject_names

    for subject_score in record.subject_scores.all():
        subject_names.add(normalize_text(subject_score.subject_name))

    return subject_names


def get_profile_interest_subjects(profile):
    subject_names = set()

    for value in list(profile.interested_subjects or []) + list(profile.skills or []):
        normalized_value = normalize_text(value)

        if normalized_value:
            subject_names.add(normalized_value)

    return subject_names


def subject_group_present(subject_names, group):
    for canonical_subject in group:
        aliases = SUBJECT_ALIASES.get(canonical_subject, [canonical_subject])

        for alias in aliases:
            normalized_alias = normalize_text(alias)

            for subject_name in subject_names:
                if normalized_alias == subject_name or normalized_alias in subject_name:
                    return True

    return False


def get_latest_record(records, level):
    matching_records = [record for record in records if record.level == level]

    if not matching_records:
        return None

    matching_records.sort(
        key=lambda record: (
            record.is_primary,
            record.passing_year or 0,
            record.id or 0,
        ),
        reverse=True,
    )

    return matching_records[0]


def build_candidate_snapshot(profile):
    records = list(
        profile.academic_records.prefetch_related("subject_scores").all()
    )

    highest_rank = 0
    highest_label = "Unknown"

    for record in records:
        rank = get_academic_rank(record.level, record.status)

        if rank > highest_rank:
            highest_rank = rank
            highest_label = record.get_level_display()

    fallback_rank = QUALIFICATION_RANKS.get(profile.current_education_status, 0)

    if fallback_rank > highest_rank:
        highest_rank = float(fallback_rank)
        highest_label = profile.get_current_education_status_display()

    class_12_record = get_latest_record(records, "class_12")
    ug_record = get_latest_record(records, "ug")

    stream = profile.current_stream

    if class_12_record and class_12_record.stream != "unsure":
        stream = class_12_record.stream

    subject_names = get_subject_names_from_record(class_12_record)
    subject_names.update(get_profile_interest_subjects(profile))

    is_class_12_appearing = False

    if class_12_record and class_12_record.status in ["appearing", "result_awaited"]:
        is_class_12_appearing = True

    return CandidateSnapshot(
        profile=profile,
        highest_rank=highest_rank,
        highest_label=highest_label,
        stream=stream,
        class_12_percentage=class_12_record.percentage if class_12_record else None,
        ug_percentage=ug_record.percentage if ug_record else None,
        subject_names=subject_names,
        is_class_12_appearing=is_class_12_appearing,
        has_required_documents=profile.has_required_documents(),
        missing_required_documents=profile.missing_required_document_groups(),
    )


def detect_course_rule(programme_name):
    normalized_name = normalize_text(programme_name)

    matched_rule = None
    best_pattern_length = 0

    for rule in COURSE_RULES:
        for pattern in rule["patterns"]:
            normalized_pattern = normalize_text(pattern)

            if normalized_pattern and normalized_pattern in normalized_name:
                if len(normalized_pattern) > best_pattern_length:
                    matched_rule = rule
                    best_pattern_length = len(normalized_pattern)

    return matched_rule or DEFAULT_RULE


def get_percentage_for_rule(snapshot, rule):
    required_rank = rule.get("required_rank", 12)

    if required_rank >= 16:
        return snapshot.ug_percentage

    return snapshot.class_12_percentage


def check_programme_eligibility(candidate_profile, programme):
    snapshot = build_candidate_snapshot(candidate_profile)
    rule = detect_course_rule(programme.program_name)

    score = 0
    passed_rules = []
    failed_rules = []
    warnings = []
    missing_data = []

    required_rank = rule.get("required_rank", 12)
    required_qualification = rule.get("required_qualification", "Class 12")

    # Qualification check
    if snapshot.highest_rank >= required_rank:
        score += 40
        passed_rules.append(
            f"Candidate has required qualification: {snapshot.highest_label}."
        )
    elif required_rank == 12 and snapshot.is_class_12_appearing:
        score += 28
        warnings.append(
            "Candidate is currently appearing/result awaited for Class 12. Eligibility depends on final result."
        )
    else:
        failed_rules.append(
            f"This programme requires {required_qualification}, but candidate currently has {snapshot.highest_label}."
        )

    # Stream check
    allowed_streams = rule.get("allowed_streams", [])
    strict_stream = rule.get("strict_stream", False)

    if allowed_streams:
        if snapshot.stream in allowed_streams:
            score += 20
            passed_rules.append(f"Candidate stream '{snapshot.stream}' matches this programme.")
        elif strict_stream:
            failed_rules.append(
                f"This programme usually requires one of these streams: {', '.join(allowed_streams)}."
            )
        else:
            score += 10
            warnings.append(
                f"Candidate stream '{snapshot.stream}' is not ideal, but this programme may still be possible depending on university rules."
            )
    else:
        score += 20
        passed_rules.append("No strict stream restriction detected.")

    # Required subject check
    required_subject_groups = rule.get("required_subject_groups", [])

    if required_subject_groups:
        if not snapshot.subject_names:
            missing_data.append("Class 12 subject-wise marks are missing.")
        else:
            all_required_subjects_present = True

            for group in required_subject_groups:
                if not subject_group_present(snapshot.subject_names, group):
                    all_required_subjects_present = False
                    failed_rules.append(
                        f"Required subject missing: one of {', '.join(group)}."
                    )

            if all_required_subjects_present:
                score += 20
                passed_rules.append("Required subject condition is satisfied.")
    else:
        score += 15
        passed_rules.append("No strict required subject condition detected.")

    # Preferred subject check
    preferred_subject_groups = rule.get("preferred_subject_groups", [])

    preferred_match_count = 0

    if preferred_subject_groups and snapshot.subject_names:
        for group in preferred_subject_groups:
            if subject_group_present(snapshot.subject_names, group):
                preferred_match_count += 1

        if preferred_match_count:
            score += min(preferred_match_count * 5, 10)
            passed_rules.append("Candidate has preferred subjects for this course.")
        else:
            warnings.append(
                "Candidate does not have preferred subjects, but this may not be a hard rejection."
            )

    # Percentage check
    min_percentage = rule.get("min_percentage")
    candidate_percentage = get_percentage_for_rule(snapshot, rule)

    if min_percentage is not None:
        if candidate_percentage is None:
            missing_data.append("Percentage is missing for eligibility check.")
        elif candidate_percentage >= Decimal(str(min_percentage)):
            score += 10
            passed_rules.append(
                f"Candidate percentage {candidate_percentage}% meets minimum suggested {min_percentage}%."
            )
        else:
            failed_rules.append(
                f"Candidate percentage {candidate_percentage}% is below suggested minimum {min_percentage}%."
            )

    # Document readiness check
    if not snapshot.has_required_documents:
        warnings.append("Some required documents are missing for final admission verification.")

    score = min(score, 100)

    hard_failed = len(failed_rules) > 0

    if missing_data and not hard_failed:
        status = "insufficient_data"
    elif hard_failed:
        status = "not_eligible"
    elif score >= 75:
        status = "eligible"
    else:
        status = "likely_eligible"

    return {
        "programme_id": programme.id,
        "programme_name": programme.program_name,
        "university_name": programme.hei_name,
        "state": programme.state,
        "level": programme.level,
        "mode": programme.mode,
        "year": programme.year,
        "detected_course_family": rule["family"],
        "detected_course_label": rule["label"],
        "eligibility_status": status,
        "eligibility_score": score,
        "required_qualification": required_qualification,
        "candidate_highest_qualification": snapshot.highest_label,
        "future_path": rule.get("future_path", ""),
        "passed_rules": passed_rules,
        "failed_rules": failed_rules,
        "warnings": warnings,
        "missing_data": missing_data,
        "document_status": {
            "has_required_documents": snapshot.has_required_documents,
            "missing_required_document_groups": snapshot.missing_required_documents,
        },
    }
