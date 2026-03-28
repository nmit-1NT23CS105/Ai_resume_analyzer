"""FastAPI entrypoint for the AI Resume Analyzer."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.schemas import AnalyzeRequest, FileParseResponse, ResumeAnalysisResponse, SkillExtractionResponse, TextRequest
from app.core.analyzer import (
    RESUME_SECTION_ALIASES,
    analyze_resume,
    detect_sections,
    estimate_experience_years,
    extract_skills,
    infer_role,
)
from app.core.file_parser import FileParsingError, extract_text_from_bytes
from app.core.text_processing import extract_contact_info, top_keywords

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(
    title="AI Resume Analyzer",
    version="1.0.0",
    description="Analyze resumes against job descriptions using Python and lightweight NLP.",
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def root() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/samples")
def samples() -> dict[str, str]:
    return {
        "resume_text": (DATA_DIR / "sample_resume.txt").read_text(encoding="utf-8"),
        "job_description": (DATA_DIR / "sample_job_description.txt").read_text(encoding="utf-8"),
    }


def _parse_uploaded_text(filename: str | None, file_bytes: bytes) -> tuple[str, str]:
    try:
        return extract_text_from_bytes(filename, file_bytes)
    except FileParsingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/parse-file", response_model=FileParseResponse)
async def parse_file(file: UploadFile = File(...)) -> FileParseResponse:
    file_bytes = await file.read()
    extension, extracted_text = _parse_uploaded_text(file.filename, file_bytes)
    return FileParseResponse(
        filename=file.filename or f"upload{extension}",
        extension=extension,
        extracted_text=extracted_text,
        char_count=len(extracted_text),
    )


@app.post("/extract-skills", response_model=SkillExtractionResponse)
def extract_skills_endpoint(request: TextRequest) -> SkillExtractionResponse:
    extracted_skills = extract_skills(request.text)
    return SkillExtractionResponse(
        extracted_skills=extracted_skills,
        keyword_candidates=top_keywords(request.text),
        contact_info=extract_contact_info(request.text),
        sections_detected=detect_sections(request.text, RESUME_SECTION_ALIASES),
        inferred_role=infer_role(extracted_skills, request.text),
        estimated_experience_years=estimate_experience_years(request.text),
    )


@app.post("/analyze", response_model=ResumeAnalysisResponse)
def analyze_endpoint(request: AnalyzeRequest) -> ResumeAnalysisResponse:
    return ResumeAnalysisResponse(**analyze_resume(request.resume_text, request.job_description))


@app.post("/extract-skills/file", response_model=SkillExtractionResponse)
async def extract_skills_file_endpoint(file: UploadFile = File(...)) -> SkillExtractionResponse:
    file_bytes = await file.read()
    _, extracted_text = _parse_uploaded_text(file.filename, file_bytes)
    extracted_skills = extract_skills(extracted_text)
    return SkillExtractionResponse(
        extracted_skills=extracted_skills,
        keyword_candidates=top_keywords(extracted_text),
        contact_info=extract_contact_info(extracted_text),
        sections_detected=detect_sections(extracted_text, RESUME_SECTION_ALIASES),
        inferred_role=infer_role(extracted_skills, extracted_text),
        estimated_experience_years=estimate_experience_years(extracted_text),
    )


@app.post("/analyze-files", response_model=ResumeAnalysisResponse)
async def analyze_files_endpoint(
    resume_file: UploadFile = File(...),
    job_file: UploadFile = File(...),
) -> ResumeAnalysisResponse:
    resume_bytes = await resume_file.read()
    job_bytes = await job_file.read()
    _, resume_text = _parse_uploaded_text(resume_file.filename, resume_bytes)
    _, job_text = _parse_uploaded_text(job_file.filename, job_bytes)
    return ResumeAnalysisResponse(**analyze_resume(resume_text, job_text))


@app.get("/analyze/sample", response_model=ResumeAnalysisResponse)
def analyze_sample() -> ResumeAnalysisResponse:
    resume_text = (DATA_DIR / "sample_resume.txt").read_text(encoding="utf-8")
    job_description = (DATA_DIR / "sample_job_description.txt").read_text(encoding="utf-8")
    return ResumeAnalysisResponse(**analyze_resume(resume_text, job_description))
