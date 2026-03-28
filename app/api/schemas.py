"""Pydantic request and response models."""

from __future__ import annotations

from pydantic import BaseModel, Field


class TextRequest(BaseModel):
    text: str = Field(..., min_length=20, description="Resume or job description text.")


class AnalyzeRequest(BaseModel):
    resume_text: str = Field(..., min_length=20, description="Raw resume text.")
    job_description: str = Field(..., min_length=20, description="Raw job description text.")


class ContactInfo(BaseModel):
    name: str | None = None
    email: str | None = None
    phone: str | None = None


class SkillGap(BaseModel):
    matched: list[str]
    missing: list[str]
    additional: list[str]


class ScoreBreakdown(BaseModel):
    skill_match: float
    document_similarity: float
    keyword_alignment: float
    section_alignment: float
    experience_alignment: float
    ats_readiness: float
    final_score: float


class ProfileInsights(BaseModel):
    inferred_role: str
    resume_seniority: str
    job_seniority: str
    estimated_experience_years: float | None = None
    required_experience_years: float | None = None
    experience_alignment_label: str


class SectionAnalysis(BaseModel):
    score: float
    present_sections: list[str]
    missing_sections: list[str]
    present_job_sections: list[str]
    missing_job_sections: list[str]


class ATSAnalysis(BaseModel):
    score: float
    strengths: list[str]
    issues: list[str]


class CategoryScore(BaseModel):
    category: str
    score: float
    matched: list[str]
    missing: list[str]
    matched_count: int
    required_count: int


class InsightSummary(BaseModel):
    summary: str
    strengths: list[str]
    recommendations: list[str]
    priority_actions: list[str]
    risk_flags: list[str]


class SkillExtractionResponse(BaseModel):
    extracted_skills: list[str]
    keyword_candidates: list[str]
    contact_info: ContactInfo
    sections_detected: list[str]
    inferred_role: str
    estimated_experience_years: float | None = None


class FileParseResponse(BaseModel):
    filename: str
    extension: str
    extracted_text: str
    char_count: int


class ResumeAnalysisResponse(BaseModel):
    contact_info: ContactInfo
    resume_skills: list[str]
    job_skills: list[str]
    skill_gap: SkillGap
    keyword_overlap: list[str]
    resume_keywords: list[str]
    job_keywords: list[str]
    scores: ScoreBreakdown
    verdict: str
    profile: ProfileInsights
    section_analysis: SectionAnalysis
    ats_analysis: ATSAnalysis
    category_scores: list[CategoryScore]
    insights: InsightSummary
