"""Resume parsing, role inference, and advanced match scoring."""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime
from functools import lru_cache

from app.core.skill_catalog import ROLE_SIGNATURES, SKILL_ALIASES, SKILL_CATEGORY_MAP
from app.core.text_processing import cosine_similarity, extract_contact_info, normalize_text, shared_keywords, top_keywords

RESUME_SECTION_ALIASES = {
    "Summary": {"summary", "profile", "objective", "professional summary", "about"},
    "Skills": {"skills", "technical skills", "core skills", "competencies"},
    "Experience": {"experience", "work experience", "professional experience", "employment history"},
    "Projects": {"projects", "project experience", "key projects"},
    "Education": {"education", "academic background", "qualification", "qualifications"},
    "Certifications": {"certifications", "licenses", "training"},
}

JOB_SECTION_ALIASES = {
    "Overview": {"overview", "about the role", "role overview", "summary", "about us", "job summary"},
    "Responsibilities": {"responsibilities", "what you will do", "key responsibilities", "duties"},
    "Requirements": {"requirements", "qualifications", "must have", "what we are looking for"},
    "Preferred": {"preferred", "nice to have", "preferred qualifications", "bonus points"},
}

RESUME_SECTION_WEIGHTS = {
    "Summary": 0.14,
    "Skills": 0.23,
    "Experience": 0.29,
    "Projects": 0.18,
    "Education": 0.1,
    "Certifications": 0.06,
}

JOB_SECTION_WEIGHTS = {
    "Overview": 0.15,
    "Responsibilities": 0.4,
    "Requirements": 0.35,
    "Preferred": 0.1,
}

SENIORITY_KEYWORDS = [
    ("Intern", {"intern", "internship", "trainee", "fresher"}),
    ("Junior", {"junior", "entry level", "entry-level", "associate"}),
    ("Mid-level", {"mid level", "mid-level", "midlevel", "intermediate"}),
    ("Senior", {"senior", "sr.", "sr ", "experienced"}),
    ("Lead", {"lead", "team lead", "tech lead", "manager"}),
    ("Principal", {"principal", "staff", "architect", "head"}),
]

SENIORITY_RANK = {
    "Intern": 0,
    "Junior": 1,
    "Mid-level": 2,
    "Senior": 3,
    "Lead": 4,
    "Principal": 5,
}

EXPLICIT_YEARS_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)", re.IGNORECASE)
YEAR_REQUIREMENT_RANGE_PATTERN = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:-|to)\s*(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)",
    re.IGNORECASE,
)
YEAR_RANGE_PATTERN = re.compile(
    r"(?<!\d)(19\d{2}|20\d{2})\s*(?:-|\u2013|\u2014|to)\s*(present|current|now|19\d{2}|20\d{2})",
    re.IGNORECASE,
)
MONTH_YEAR_RANGE_PATTERN = re.compile(
    r"\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|"
    r"sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+"
    r"(19\d{2}|20\d{2})\s*(?:-|\u2013|\u2014|to)\s*"
    r"(?:(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|"
    r"sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+)?"
    r"(present|current|now|19\d{2}|20\d{2})\b",
    re.IGNORECASE,
)
METRIC_PATTERN = re.compile(r"\b\d+(?:\.\d+)?\s*(?:%|percent|x|k\+?|m\+?)\b", re.IGNORECASE)
LINE_BULLET_PATTERN = re.compile(r"^\s*(?:[-*]|\u2022|\u25e6|\u2013|\u2014)", re.MULTILINE)
WORD_PATTERN = re.compile(r"\b[a-zA-Z][a-zA-Z0-9+#.\-/]*\b")

JOB_SKILL_SECTION_WEIGHTS = {
    "Requirements": 1.0,
    "Responsibilities": 0.85,
    "Overview": 0.65,
    "Preferred": 0.45,
}

REQUIRED_CUES = {
    "must",
    "required",
    "requirement",
    "minimum",
    "need",
    "needs",
    "looking for",
    "proficiency",
    "strong",
    "hands-on",
}
PREFERRED_CUES = {"preferred", "nice to have", "bonus", "plus", "good to have", "advantage"}
ACTION_VERBS = {
    "achieved",
    "automated",
    "built",
    "created",
    "delivered",
    "designed",
    "developed",
    "engineered",
    "implemented",
    "improved",
    "launched",
    "led",
    "optimized",
    "reduced",
    "scaled",
    "shipped",
}


@lru_cache(maxsize=None)
def _compile_alias_pattern(alias: str) -> re.Pattern[str]:
    return re.compile(rf"(?<!\w){re.escape(_normalize_for_matching(alias))}(?!\w)")


def _normalize_for_matching(text: str) -> str:
    return " ".join(normalize_text(text).lower().split())


def extract_skills(text: str) -> list[str]:
    normalized_text = _normalize_for_matching(text)
    extracted: list[str] = []

    for canonical_skill, aliases in SKILL_ALIASES.items():
        if any(_compile_alias_pattern(alias).search(normalized_text) for alias in aliases):
            extracted.append(canonical_skill)

    return sorted(extracted)


def detect_sections(text: str, aliases_map: dict[str, set[str]]) -> list[str]:
    present_sections: list[str] = []

    for line in normalize_text(text).splitlines():
        section = _match_section_heading(line, aliases_map)
        if section and section not in present_sections:
            present_sections.append(section)

    return present_sections


def _match_section_heading(line: str, aliases_map: dict[str, set[str]]) -> str | None:
    heading = _normalize_section_heading(line)
    if not heading:
        return None

    for section, aliases in aliases_map.items():
        for alias in aliases:
            normalized_alias = _normalize_for_matching(alias)
            if heading == normalized_alias:
                return section
            if re.match(rf"^{re.escape(normalized_alias)}(?:\s|:|-)", heading):
                return section

    return None


def _normalize_section_heading(line: str) -> str:
    heading = _normalize_for_matching(line)
    return heading.strip("#>*- ").rstrip(":")


def _split_sections(text: str, aliases_map: dict[str, set[str]]) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current_section: str | None = None

    for raw_line in normalize_text(text).splitlines():
        matched_section = _match_section_heading(raw_line, aliases_map)
        if matched_section:
            current_section = matched_section
            sections.setdefault(matched_section, [])
            continue

        if current_section and raw_line.strip():
            sections[current_section].append(raw_line.strip())

    return {
        section: "\n".join(lines).strip()
        for section, lines in sections.items()
        if lines
    }


def infer_role(skills: list[str], text: str) -> str:
    text_lower = text.lower()
    skill_set = set(skills)
    best_role = "Software Engineer"
    best_score = -1

    for role, signature in ROLE_SIGNATURES.items():
        skill_score = len(skill_set & signature["skills"]) * 3
        keyword_score = sum(1 for keyword in signature["keywords"] if keyword in text_lower)
        role_score = skill_score + keyword_score
        if role_score > best_score:
            best_role = role
            best_score = role_score

    return best_role if best_score > 0 else "Software Engineer"


def estimate_experience_years(text: str, *, prefer_minimum: bool = False) -> float | None:
    normalized_text = normalize_text(text)
    explicit_years = _extract_explicit_year_values(normalized_text, prefer_minimum=prefer_minimum)
    timeline_years = _estimate_timeline_years(normalized_text)
    candidates = explicit_years + ([timeline_years] if timeline_years else [])
    estimate = max(candidates, default=0.0)
    return round(estimate, 1) if estimate > 0 else None


def _extract_explicit_year_values(text: str, *, prefer_minimum: bool) -> list[float]:
    values: list[float] = []
    range_spans: list[tuple[int, int]] = []

    for match in YEAR_REQUIREMENT_RANGE_PATTERN.finditer(text):
        lower = float(match.group(1))
        upper = float(match.group(2))
        values.append(min(lower, upper) if prefer_minimum else max(lower, upper))
        range_spans.append(match.span())

    for match in EXPLICIT_YEARS_PATTERN.finditer(text):
        if any(start <= match.start() < end for start, end in range_spans):
            continue
        values.append(float(match.group(1)))

    return values


def _estimate_timeline_years(text: str) -> float:
    current_year = datetime.now().year
    intervals: list[tuple[float, float]] = []

    for match in YEAR_RANGE_PATTERN.finditer(text):
        start_year = int(match.group(1))
        end_year = _parse_end_year(match.group(2), current_year)
        _append_year_interval(intervals, start_year, end_year)

    for match in MONTH_YEAR_RANGE_PATTERN.finditer(text):
        start_year = int(match.group(1))
        end_year = _parse_end_year(match.group(2), current_year)
        _append_year_interval(intervals, start_year, end_year)

    if not intervals:
        return 0.0

    intervals.sort()
    merged: list[tuple[float, float]] = []
    for start, end in intervals:
        if not merged or start > merged[-1][1]:
            merged.append((start, end))
            continue
        previous_start, previous_end = merged[-1]
        merged[-1] = (previous_start, max(previous_end, end))

    return round(sum(end - start for start, end in merged), 1)


def _parse_end_year(token: str, current_year: int) -> int:
    normalized = token.lower()
    return current_year if normalized in {"present", "current", "now"} else int(normalized)


def _append_year_interval(intervals: list[tuple[float, float]], start_year: int, end_year: int) -> None:
    current_year = datetime.now().year
    if start_year < 1950 or start_year > current_year + 1 or end_year < start_year:
        return

    interval_end = float(end_year)
    if end_year == start_year:
        interval_end += 0.5
    intervals.append((float(start_year), interval_end))


def infer_seniority(text: str, estimated_years: float | None, *, job_mode: bool = False) -> str:
    text_lower = _normalize_for_matching(text)
    detected_label = None
    detected_rank = -1

    for label, keywords in SENIORITY_KEYWORDS:
        if any(_compile_alias_pattern(keyword).search(text_lower) for keyword in keywords):
            rank = SENIORITY_RANK[label]
            if rank > detected_rank:
                detected_label = label
                detected_rank = rank

    if detected_label:
        return detected_label

    if estimated_years is None:
        return "Not specified" if job_mode else "Emerging"
    if estimated_years >= 9:
        return "Principal"
    if estimated_years >= 7:
        return "Lead"
    if estimated_years >= 4:
        return "Senior"
    if estimated_years >= 2:
        return "Mid-level"
    if estimated_years >= 0.5:
        return "Junior"
    return "Emerging"


def build_verdict(score: float) -> str:
    if score >= 85:
        return "Excellent match"
    if score >= 72:
        return "Strong match"
    if score >= 58:
        return "Competitive match"
    if score >= 42:
        return "Moderate match"
    return "Needs improvement"


def _score_section_presence(
    present_sections: list[str],
    weights: dict[str, float],
) -> float:
    return round(sum(weights[section] for section in present_sections if section in weights) * 100, 2)


def _score_keyword_alignment(resume_text: str, job_description: str) -> float:
    resume_top = set(top_keywords(resume_text, limit=12))
    job_top = set(top_keywords(job_description, limit=12))
    if not job_top:
        return 0.0
    return round(len(resume_top & job_top) / len(job_top) * 100, 2)


def _build_job_skill_weights(job_description: str, job_skills: list[str]) -> dict[str, float]:
    section_blocks = _split_sections(job_description, JOB_SECTION_ALIASES)
    weights: dict[str, float] = {}

    for skill in job_skills:
        section_weight = _section_weight_for_skill(skill, section_blocks)
        context_weight = _context_weight_for_skill(skill, job_description)
        detected_weight = section_weight if section_weight > 0 else context_weight
        weights[skill] = detected_weight if detected_weight > 0 else 0.65

    return weights


def _section_weight_for_skill(skill: str, section_blocks: dict[str, str]) -> float:
    weight = 0.0
    for section, section_text in section_blocks.items():
        if _skill_in_text(skill, section_text):
            weight = max(weight, JOB_SKILL_SECTION_WEIGHTS.get(section, 0.65))
    return weight


def _context_weight_for_skill(skill: str, text: str) -> float:
    normalized_text = _normalize_for_matching(text)
    best_weight = 0.0

    for alias in SKILL_ALIASES.get(skill, [skill]):
        pattern = _compile_alias_pattern(alias)
        for match in pattern.finditer(normalized_text):
            context = normalized_text[max(0, match.start() - 90) : match.end() + 90]
            if any(cue in context for cue in REQUIRED_CUES):
                best_weight = max(best_weight, 1.0)
            elif any(cue in context for cue in PREFERRED_CUES):
                best_weight = max(best_weight, 0.45)
            else:
                best_weight = max(best_weight, 0.65)

    return best_weight


def _skill_in_text(skill: str, text: str) -> bool:
    normalized_text = _normalize_for_matching(text)
    return any(
        _compile_alias_pattern(alias).search(normalized_text)
        for alias in SKILL_ALIASES.get(skill, [skill])
    )


def _score_weighted_skill_match(
    resume_skills: list[str],
    job_skills: list[str],
    skill_weights: dict[str, float],
) -> float:
    if not job_skills:
        return 0.0

    resume_set = set(resume_skills)
    total_weight = sum(skill_weights.get(skill, 0.65) for skill in job_skills)
    if total_weight <= 0:
        return 0.0

    matched_weight = sum(skill_weights.get(skill, 0.65) for skill in job_skills if skill in resume_set)
    return round(matched_weight / total_weight * 100, 2)


def _sort_skills_by_priority(skills: set[str], skill_weights: dict[str, float]) -> list[str]:
    return sorted(skills, key=lambda skill: (-skill_weights.get(skill, 0.65), skill))


def _score_experience_alignment(
    resume_years: float | None,
    required_years: float | None,
    resume_seniority: str,
    job_seniority: str,
) -> tuple[float, str]:
    if required_years is not None and required_years > 0:
        if resume_years is None:
            return 30.0, "Experience evidence is unclear for the target role"
        ratio = min(resume_years / required_years, 1.0)
        if ratio >= 1:
            return 100.0, "Experience depth matches or exceeds the stated requirement"
        if ratio >= 0.75:
            return 78.0, "Experience is close to the stated requirement"
        if ratio >= 0.5:
            return 55.0, "Experience may need stronger positioning"
        return 30.0, "Experience gap may be a hiring risk"

    if job_seniority == "Not specified":
        return 74.0 if resume_years else 58.0, "No explicit seniority requirement detected"

    if resume_seniority not in SENIORITY_RANK or job_seniority not in SENIORITY_RANK:
        return 60.0, "Seniority comparison is directional only"

    difference = SENIORITY_RANK[resume_seniority] - SENIORITY_RANK[job_seniority]
    if difference >= 0:
        return 92.0, "Resume seniority aligns well with the target role"
    if difference == -1:
        return 70.0, "Resume appears one level below the target role"
    if difference == -2:
        return 48.0, "Resume may need stronger seniority evidence"
    return 28.0, "Target role appears significantly more senior"


def _build_category_scores(
    resume_skills: list[str],
    job_skills: list[str],
    skill_weights: dict[str, float] | None = None,
) -> list[dict]:
    resume_set = set(resume_skills)
    grouped_required: dict[str, set[str]] = defaultdict(set)
    skill_weights = skill_weights or {}

    for skill in job_skills:
        grouped_required[SKILL_CATEGORY_MAP.get(skill, "Other")].add(skill)

    if not grouped_required:
        for skill in resume_skills:
            grouped_required[SKILL_CATEGORY_MAP.get(skill, "Other")].add(skill)

    category_scores: list[dict] = []
    for category, required_skills in sorted(grouped_required.items(), key=lambda item: (-len(item[1]), item[0])):
        matched = sorted(required_skills & resume_set)
        missing = sorted(required_skills - resume_set)
        total_weight = sum(skill_weights.get(skill, 0.65) for skill in required_skills)
        matched_weight = sum(skill_weights.get(skill, 0.65) for skill in matched)
        score = round((matched_weight / total_weight * 100) if total_weight else 0.0, 2)
        category_scores.append(
            {
                "category": category,
                "score": score,
                "matched": matched,
                "missing": missing,
                "matched_count": len(matched),
                "required_count": len(required_skills),
            }
        )

    return category_scores


def _has_quantified_impact(text: str) -> bool:
    return bool(METRIC_PATTERN.search(text))


def _has_action_verb(text: str) -> bool:
    normalized = _normalize_for_matching(text)
    return any(_compile_alias_pattern(verb).search(normalized) for verb in ACTION_VERBS)


def _build_ats_analysis(
    resume_text: str,
    contact_info: dict[str, str | None],
    section_score: float,
    keyword_alignment: float,
    skill_match_score: float,
) -> dict:
    contact_score = sum(1 for value in contact_info.values() if value) / 3 * 25
    word_count = len(WORD_PATTERN.findall(resume_text))
    bullet_count = len(LINE_BULLET_PATTERN.findall(normalize_text(resume_text)))
    readability_score = 9 if 180 <= word_count <= 1000 else 6 if 90 <= word_count <= 1200 else 3
    impact_score = 8 if _has_quantified_impact(resume_text) else 3
    bullet_score = 4 if bullet_count >= 3 else 2 if bullet_count else 0
    action_score = 2 if _has_action_verb(resume_text) else 0
    score = round(
        contact_score
        + (section_score * 0.24)
        + (keyword_alignment * 0.14)
        + (skill_match_score * 0.14)
        + readability_score
        + impact_score
        + bullet_score
        + action_score,
        2,
    )
    score = min(score, 100.0)

    strengths: list[str] = []
    issues: list[str] = []

    if contact_info.get("name") and contact_info.get("email"):
        strengths.append("Core contact details are present for ATS parsing.")
    else:
        issues.append("Add clear name and email details near the top of the resume.")

    if section_score >= 70:
        strengths.append("Resume structure includes the major sections recruiters expect.")
    else:
        issues.append("Add clearer sections such as Skills, Experience, Projects, and Education.")

    if keyword_alignment >= 60:
        strengths.append("Job-relevant keywords are represented well across the resume.")
    else:
        issues.append("Mirror more exact phrases from the job description to improve keyword alignment.")

    if _has_quantified_impact(resume_text):
        strengths.append("Quantified metrics strengthen credibility and ATS relevance.")
    else:
        issues.append("Add measurable outcomes like percentages, time saved, or scale handled.")

    if bullet_count >= 3:
        strengths.append("Bullet formatting improves scanability for recruiters and parsers.")
    else:
        issues.append("Use concise bullet points for projects and experience.")

    if not _has_action_verb(resume_text):
        issues.append("Start more bullets with strong action verbs.")

    if word_count < 90:
        issues.append("Resume content is short; add project depth and measurable accomplishments.")
    elif word_count > 1200:
        issues.append("Resume content is long; trim low-impact details for ATS scanability.")

    return {
        "score": score,
        "strengths": strengths[:4],
        "issues": issues[:4],
    }


def _augment_resume_sections(resume_text: str, sections: list[str], resume_skills: list[str]) -> list[str]:
    augmented = list(sections)
    text_lower = _normalize_for_matching(resume_text)
    if "Skills" not in augmented and len(resume_skills) >= 5:
        augmented.append("Skills")
    if "Experience" not in augmented and any(term in text_lower for term in {"developed", "engineered", "built"}):
        augmented.append("Experience")
    if "Projects" not in augmented and "project" in text_lower:
        augmented.append("Projects")
    return [section for section in RESUME_SECTION_ALIASES if section in augmented]


def _build_summary_and_actions(
    verdict: str,
    inferred_role: str,
    matched_skills: list[str],
    missing_skills: list[str],
    top_category: dict | None,
    section_analysis: dict,
    ats_analysis: dict,
    keyword_alignment: float,
    experience_alignment_label: str,
    resume_text: str,
    skill_weights: dict[str, float],
) -> dict:
    summary = (
        f"{verdict} for a {inferred_role} track with {len(matched_skills)} matched skills, "
        f"{ats_analysis['score']}% ATS readiness, and {section_analysis['score']}% structural alignment."
    )

    strengths: list[str] = []
    if matched_skills:
        strengths.append(f"Strong overlap on core skills such as {', '.join(matched_skills[:4])}.")
    if top_category and top_category["score"] >= 75:
        strengths.append(
            f"Best alignment appears in {top_category['category']} ({top_category['matched_count']}/"
            f"{top_category['required_count']} required skills covered)."
        )
    strengths.extend(ats_analysis["strengths"][:2])
    strengths.append(experience_alignment_label)

    critical_missing = [skill for skill in missing_skills if skill_weights.get(skill, 0.65) >= 0.8]
    optional_missing = [skill for skill in missing_skills if skill_weights.get(skill, 0.65) < 0.8]

    recommendations: list[str] = []
    if critical_missing:
        recommendations.append(
            f"Add evidence for required skills: {', '.join(critical_missing[:5])}."
        )
    elif optional_missing:
        recommendations.append(
            f"Optional gaps to target: {', '.join(optional_missing[:5])}."
        )
    if section_analysis["missing_sections"]:
        recommendations.append(
            f"Add missing resume sections: {', '.join(section_analysis['missing_sections'][:4])}."
        )
    if keyword_alignment < 60:
        recommendations.append("Use more exact terminology from the job description in summaries and bullets.")
    if not _has_quantified_impact(resume_text):
        recommendations.append("Rewrite project and experience bullets with measurable impact.")
    if not LINE_BULLET_PATTERN.search(normalize_text(resume_text)):
        recommendations.append("Break dense paragraphs into short bullet points for better scanability.")

    if not recommendations:
        recommendations.append("Tailor the headline and most recent project bullets to the specific role.")

    priority_actions = recommendations[:3]

    risk_flags: list[str] = []
    if len(critical_missing) >= 2:
        risk_flags.append("Multiple required skills are missing from the resume.")
    elif len(missing_skills) >= 4:
        risk_flags.append("Several job-critical skills are currently missing from the resume.")
    if ats_analysis["score"] < 65:
        risk_flags.append("ATS readiness is below the typical threshold for competitive screening.")
    if "Experience" in section_analysis["missing_sections"]:
        risk_flags.append("Work experience is not clearly structured as a dedicated section.")
    if keyword_alignment < 45:
        risk_flags.append("Keyword overlap with the target role is currently weak.")

    return {
        "summary": summary,
        "strengths": strengths[:5],
        "recommendations": recommendations[:5],
        "priority_actions": priority_actions,
        "risk_flags": risk_flags[:4],
    }


def analyze_resume(resume_text: str, job_description: str) -> dict:
    resume_skills = extract_skills(resume_text)
    job_skills = extract_skills(job_description)
    job_skill_weights = _build_job_skill_weights(job_description, job_skills)

    matched_skills = _sort_skills_by_priority(set(resume_skills) & set(job_skills), job_skill_weights)
    missing_skills = _sort_skills_by_priority(set(job_skills) - set(resume_skills), job_skill_weights)
    additional_skills = sorted(set(resume_skills) - set(job_skills))

    contact_info = extract_contact_info(resume_text)
    resume_sections = _augment_resume_sections(
        resume_text,
        detect_sections(resume_text, RESUME_SECTION_ALIASES),
        resume_skills,
    )
    job_sections = detect_sections(job_description, JOB_SECTION_ALIASES)

    section_alignment = round(
        (_score_section_presence(resume_sections, RESUME_SECTION_WEIGHTS) * 0.8)
        + (_score_section_presence(job_sections, JOB_SECTION_WEIGHTS) * 0.2),
        2,
    )
    document_similarity = round(cosine_similarity(resume_text, job_description) * 100, 2)
    keyword_alignment = _score_keyword_alignment(resume_text, job_description)
    skill_match_score = _score_weighted_skill_match(resume_skills, job_skills, job_skill_weights)

    resume_years = estimate_experience_years(resume_text)
    required_years = estimate_experience_years(job_description, prefer_minimum=True)
    resume_seniority = infer_seniority(resume_text, resume_years)
    job_seniority = infer_seniority(job_description, required_years, job_mode=True)
    experience_alignment_score, experience_alignment_label = _score_experience_alignment(
        resume_years,
        required_years,
        resume_seniority,
        job_seniority,
    )

    ats_analysis = _build_ats_analysis(
        resume_text,
        contact_info,
        section_alignment,
        keyword_alignment,
        skill_match_score,
    )

    final_score = round(
        (skill_match_score * 0.4)
        + (document_similarity * 0.18)
        + (keyword_alignment * 0.12)
        + (section_alignment * 0.1)
        + (experience_alignment_score * 0.1)
        + (ats_analysis["score"] * 0.1),
        2,
    )
    verdict = build_verdict(final_score)

    category_scores = _build_category_scores(resume_skills, job_skills, job_skill_weights)
    inferred_role = infer_role(job_skills or resume_skills, f"{resume_text}\n{job_description}")
    section_analysis = {
        "score": section_alignment,
        "present_sections": resume_sections,
        "missing_sections": [section for section in RESUME_SECTION_ALIASES if section not in resume_sections],
        "present_job_sections": job_sections,
        "missing_job_sections": [section for section in JOB_SECTION_ALIASES if section not in job_sections],
    }
    insights = _build_summary_and_actions(
        verdict,
        inferred_role,
        matched_skills,
        missing_skills,
        category_scores[0] if category_scores else None,
        section_analysis,
        ats_analysis,
        keyword_alignment,
        experience_alignment_label,
        resume_text,
        job_skill_weights,
    )

    return {
        "contact_info": contact_info,
        "resume_skills": resume_skills,
        "job_skills": job_skills,
        "skill_gap": {
            "matched": matched_skills,
            "missing": missing_skills,
            "additional": additional_skills,
        },
        "keyword_overlap": shared_keywords(resume_text, job_description, limit=12),
        "resume_keywords": top_keywords(resume_text, limit=12),
        "job_keywords": top_keywords(job_description, limit=12),
        "scores": {
            "skill_match": skill_match_score,
            "document_similarity": document_similarity,
            "keyword_alignment": keyword_alignment,
            "section_alignment": section_alignment,
            "experience_alignment": experience_alignment_score,
            "ats_readiness": ats_analysis["score"],
            "final_score": final_score,
        },
        "verdict": verdict,
        "profile": {
            "inferred_role": inferred_role,
            "resume_seniority": resume_seniority,
            "job_seniority": job_seniority,
            "estimated_experience_years": resume_years,
            "required_experience_years": required_years,
            "experience_alignment_label": experience_alignment_label,
        },
        "section_analysis": section_analysis,
        "ats_analysis": ats_analysis,
        "category_scores": category_scores,
        "insights": insights,
    }
