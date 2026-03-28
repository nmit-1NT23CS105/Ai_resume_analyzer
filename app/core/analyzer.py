"""Resume parsing, role inference, and advanced match scoring."""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime
from functools import lru_cache

from app.core.skill_catalog import ROLE_SIGNATURES, SKILL_ALIASES, SKILL_CATEGORY_MAP
from app.core.text_processing import cosine_similarity, extract_contact_info, shared_keywords, top_keywords

RESUME_SECTION_ALIASES = {
    "Summary": {"summary", "profile", "objective", "professional summary", "about"},
    "Skills": {"skills", "technical skills", "core skills", "competencies"},
    "Experience": {"experience", "work experience", "professional experience", "employment history"},
    "Projects": {"projects", "project experience", "key projects"},
    "Education": {"education", "academic background", "qualification", "qualifications"},
    "Certifications": {"certifications", "licenses", "training"},
}

JOB_SECTION_ALIASES = {
    "Overview": {"about the role", "role overview", "summary", "about us", "job summary"},
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
YEAR_RANGE_PATTERN = re.compile(
    r"(?<!\d)(19\d{2}|20\d{2})\s*(?:-|–|—|to)\s*(present|current|now|19\d{2}|20\d{2})",
    re.IGNORECASE,
)
METRIC_PATTERN = re.compile(r"\b\d+(?:\.\d+)?\s*(?:%|percent|x|k\+?|m\+?)\b", re.IGNORECASE)
LINE_BULLET_PATTERN = re.compile(r"^\s*[-*•]", re.MULTILINE)


@lru_cache(maxsize=None)
def _compile_alias_pattern(alias: str) -> re.Pattern[str]:
    return re.compile(rf"(?<!\w){re.escape(alias.lower())}(?!\w)")


def extract_skills(text: str) -> list[str]:
    normalized_text = " ".join(text.lower().split())
    extracted: list[str] = []

    for canonical_skill, aliases in SKILL_ALIASES.items():
        if any(_compile_alias_pattern(alias).search(normalized_text) for alias in aliases):
            extracted.append(canonical_skill)

    return sorted(extracted)


def detect_sections(text: str, aliases_map: dict[str, set[str]]) -> list[str]:
    lines = [line.strip().lower().rstrip(":") for line in text.splitlines() if line.strip()]
    present_sections: list[str] = []

    for section, aliases in aliases_map.items():
        if any(line in aliases or line.startswith(f"{alias} ") for line in lines for alias in aliases):
            present_sections.append(section)

    return present_sections


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


def estimate_experience_years(text: str) -> float | None:
    explicit_years = [float(match.group(1)) for match in EXPLICIT_YEARS_PATTERN.finditer(text)]
    span_years: list[float] = []
    current_year = datetime.now().year

    for match in YEAR_RANGE_PATTERN.finditer(text):
        start_year = int(match.group(1))
        end_token = match.group(2).lower()
        end_year = current_year if end_token in {"present", "current", "now"} else int(end_token)
        if end_year >= start_year:
            span_years.append(float(end_year - start_year))

    estimate = max(explicit_years + span_years, default=0.0)
    return round(estimate, 1) if estimate > 0 else None


def infer_seniority(text: str, estimated_years: float | None, *, job_mode: bool = False) -> str:
    text_lower = text.lower()
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


def _build_category_scores(resume_skills: list[str], job_skills: list[str]) -> list[dict]:
    resume_set = set(resume_skills)
    grouped_required: dict[str, set[str]] = defaultdict(set)

    for skill in job_skills:
        grouped_required[SKILL_CATEGORY_MAP.get(skill, "Other")].add(skill)

    if not grouped_required:
        for skill in resume_skills:
            grouped_required[SKILL_CATEGORY_MAP.get(skill, "Other")].add(skill)

    category_scores: list[dict] = []
    for category, required_skills in sorted(grouped_required.items(), key=lambda item: (-len(item[1]), item[0])):
        matched = sorted(required_skills & resume_set)
        missing = sorted(required_skills - resume_set)
        score = round((len(matched) / len(required_skills) * 100) if required_skills else 0.0, 2)
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


def _build_ats_analysis(
    resume_text: str,
    contact_info: dict[str, str | None],
    section_score: float,
    keyword_alignment: float,
    skill_match_score: float,
) -> dict:
    contact_score = sum(1 for value in contact_info.values() if value) / 3 * 25
    readability_score = 10 if 450 <= len(resume_text) <= 9000 else 6
    impact_score = 12 if _has_quantified_impact(resume_text) else 4
    score = round(
        contact_score
        + (section_score * 0.28)
        + (keyword_alignment * 0.16)
        + (skill_match_score * 0.13)
        + readability_score
        + impact_score,
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

    if len(resume_text) < 350:
        issues.append("Resume content is short; add project depth and measurable accomplishments.")

    return {
        "score": score,
        "strengths": strengths[:4],
        "issues": issues[:4],
    }


def _augment_resume_sections(resume_text: str, sections: list[str], resume_skills: list[str]) -> list[str]:
    augmented = list(sections)
    text_lower = resume_text.lower()
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

    recommendations: list[str] = []
    if missing_skills:
        recommendations.append(
            f"Emphasize or learn the missing priority skills: {', '.join(missing_skills[:5])}."
        )
    if section_analysis["missing_sections"]:
        recommendations.append(
            f"Add missing resume sections: {', '.join(section_analysis['missing_sections'][:4])}."
        )
    if keyword_alignment < 60:
        recommendations.append("Use more exact terminology from the job description in summaries and bullets.")
    if not _has_quantified_impact(resume_text):
        recommendations.append("Rewrite project and experience bullets with measurable impact.")
    if not LINE_BULLET_PATTERN.search(resume_text):
        recommendations.append("Break dense paragraphs into short bullet points for better scanability.")

    if not recommendations:
        recommendations.append("Tailor the headline and most recent project bullets to the specific role.")

    priority_actions = recommendations[:3]

    risk_flags: list[str] = []
    if len(missing_skills) >= 4:
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

    matched_skills = sorted(set(resume_skills) & set(job_skills))
    missing_skills = sorted(set(job_skills) - set(resume_skills))
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
    skill_match_score = round(
        (len(matched_skills) / len(job_skills) * 100) if job_skills else 0.0,
        2,
    )

    resume_years = estimate_experience_years(resume_text)
    required_years = estimate_experience_years(job_description)
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
        (skill_match_score * 0.34)
        + (document_similarity * 0.18)
        + (keyword_alignment * 0.14)
        + (section_alignment * 0.12)
        + (experience_alignment_score * 0.1)
        + (ats_analysis["score"] * 0.12),
        2,
    )
    verdict = build_verdict(final_score)

    category_scores = _build_category_scores(resume_skills, job_skills)
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
