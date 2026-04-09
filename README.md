# AI Resume Analyzer

Python + NLP project that analyzes resumes, extracts skills, and compares them against job descriptions through a FastAPI backend.

## Features

- Advanced resume skill extraction using a curated NLP-style skill catalog
- Job description matching with matched, missing, and additional skills
- Weighted matching that prioritizes required skills above preferred skills
- Multi-factor scoring across skill fit, semantic similarity, keyword alignment, section coverage, experience fit, and ATS readiness
- Role inference, seniority estimation, category-based skill coverage, and recruiter-style recommendations
- FastAPI endpoints for skill extraction, file parsing, and advanced resume analysis
- File upload support for `TXT`, `DOCX`, and text-based `PDF` documents
- Immersive browser UI with 3D-style visuals, animated score rings, category heatmaps, and recruiter summary copy actions
- Sample resume and job description for quick demos

## Project Structure

```text
resume_project/
|-- app/
|   |-- api/
|   |   `-- schemas.py
|   |-- core/
|   |   |-- analyzer.py
|   |   |-- file_parser.py
|   |   |-- skill_catalog.py
|   |   `-- text_processing.py
|   |-- data/
|   |   |-- sample_job_description.txt
|   |   `-- sample_resume.txt
|   `-- main.py
|-- tests/
|   `-- test_analyzer.py
|-- requirements.txt
`-- README.md
```

## Setup

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Run The App

```powershell
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/` for the browser UI.

Open `http://127.0.0.1:8000/docs` for Swagger UI.

The UI now supports direct file uploads for resumes and job descriptions.

## Example Endpoints

### Health Check

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

### Extract Skills

```powershell
Invoke-RestMethod `
  -Uri http://127.0.0.1:8000/extract-skills `
  -Method Post `
  -ContentType "application/json" `
  -Body '{"text":"Built an NLP resume parser with Python, FastAPI, SQL, and Docker."}'
```

### Analyze Resume Against A Job Description

```powershell
Invoke-RestMethod `
  -Uri http://127.0.0.1:8000/analyze `
  -Method Post `
  -ContentType "application/json" `
  -Body '{"resume_text":"Python NLP developer with FastAPI and SQL.","job_description":"Hiring a Python NLP engineer with FastAPI, SQL, and Docker."}'
```

### Sample Demo

```powershell
Invoke-RestMethod http://127.0.0.1:8000/analyze/sample
```

### Load Sample Content For The UI

```powershell
Invoke-RestMethod http://127.0.0.1:8000/samples
```

### Parse An Uploaded File

```powershell
curl.exe -X POST -F "file=@resume.docx" http://127.0.0.1:8000/parse-file
```

### Analyze Two Uploaded Files

```powershell
curl.exe -X POST ^
  -F "resume_file=@resume.pdf" ^
  -F "job_file=@job_description.docx" ^
  http://127.0.0.1:8000/analyze-files
```

## Deploy On Render

This repository is now prepared for Render deployment with [render.yaml](/c:/project_resum/resume_project/render.yaml) and [.python-version](/c:/project_resum/resume_project/.python-version).

### Option 1: Deploy From `render.yaml`

1. Push the project to GitHub.
2. In Render, select `New +` and then `Blueprint`.
3. Connect the GitHub repository.
4. Render will detect `render.yaml` and provision the web service automatically.
5. Open the generated `onrender.com` URL after the first successful deploy.

### Option 2: Create A Web Service Manually

Use these Render settings:

- Runtime: `Python`
- Build Command: `pip install -r requirements.txt`
- Start Command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Health Check Path: `/health`

### Render Notes

- The root route `/` serves the full frontend UI.
- The API docs remain available at `/docs`.
- File upload parsing works in the same deployed service.
- `render.yaml` is set to the `free` plan by default. You can switch to a paid plan in Render later if you want higher uptime or less cold-start behavior.

## How Scoring Works

- `skill_match`: weighted job-skill coverage, with Requirements weighted higher than Preferred skills
- `document_similarity`: TF-IDF-style cosine similarity between resume and job text
- `keyword_alignment`: overlap across normalized keywords and high-value technical phrases
- `experience_alignment`: compares resume years/seniority against required years and role level
- `ats_readiness`: checks contact info, sections, keyword fit, measurable impact, bullets, and action verbs
- `final_score`: weighted blend led by skill match, then similarity, keywords, sections, experience, and ATS quality

## Notes

- This implementation stays dependency-light and does not require downloading external NLP models.
- You can extend `app/core/skill_catalog.py` with more domain-specific skills whenever needed.
- The root route now serves a built-in frontend, while the JSON endpoints remain available for API use.
- PDF extraction is best-effort for text-based PDFs. Scanned or image-only PDFs need OCR support, which is not included yet.
- `pypdf` is used to improve PDF extraction accuracy, with the lightweight parser retained as a fallback.
