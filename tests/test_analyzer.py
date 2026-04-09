"""Basic test coverage for the AI Resume Analyzer."""

from __future__ import annotations

import io
import unittest
import zipfile

from fastapi.testclient import TestClient

from app.core.analyzer import RESUME_SECTION_ALIASES, analyze_resume, detect_sections, estimate_experience_years, extract_skills
from app.main import app


def build_docx_bytes(text: str) -> bytes:
    buffer = io.BytesIO()
    xml = f"""
    <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
      <w:body>
        <w:p>
          <w:r><w:t>{text}</w:t></w:r>
        </w:p>
      </w:body>
    </w:document>
    """.strip()

    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", xml)

    return buffer.getvalue()


def build_pdf_bytes(text: str) -> bytes:
    safe_text = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream = f"BT /F1 12 Tf 72 720 Td ({safe_text}) Tj ET".encode("latin-1")
    return (
        b"%PDF-1.4\n"
        b"1 0 obj << /Type /Catalog >> endobj\n"
        + f"2 0 obj << /Length {len(stream)} >> stream\n".encode("latin-1")
        + stream
        + b"\nendstream endobj\n%%EOF"
    )


class ResumeAnalyzerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def test_skill_extraction_finds_core_technologies(self) -> None:
        text = "Built a resume analyzer with Python, NLP, FastAPI, SQL, and Docker."
        extracted = extract_skills(text)

        self.assertIn("Python", extracted)
        self.assertIn("NLP", extracted)
        self.assertIn("FastAPI", extracted)
        self.assertIn("SQL", extracted)
        self.assertIn("Docker", extracted)

    def test_skill_extraction_handles_modern_aliases(self) -> None:
        text = "Built a Next.js UI with Tailwind CSS, GraphQL APIs, RAG, Hugging Face Transformers, and Terraform."
        extracted = extract_skills(text)

        self.assertIn("Next.js", extracted)
        self.assertIn("Tailwind CSS", extracted)
        self.assertIn("GraphQL", extracted)
        self.assertIn("RAG", extracted)
        self.assertIn("Hugging Face", extracted)
        self.assertIn("Transformers", extracted)
        self.assertIn("Terraform", extracted)

    def test_preferred_skills_are_weighted_below_required_skills(self) -> None:
        resume = "Python FastAPI SQL engineer with production backend API experience."
        required_job = "Requirements\nPython, FastAPI, SQL, Kubernetes."
        preferred_job = "Requirements\nPython, FastAPI, SQL.\nPreferred\nKubernetes."

        required_result = analyze_resume(resume, required_job)
        preferred_result = analyze_resume(resume, preferred_job)

        self.assertLess(required_result["scores"]["skill_match"], preferred_result["scores"]["skill_match"])
        self.assertGreaterEqual(preferred_result["scores"]["skill_match"], 85)

    def test_experience_estimation_merges_role_ranges(self) -> None:
        text = "Engineer | 2020 - 2022\nSenior Engineer | 2022 - 2024"

        self.assertEqual(estimate_experience_years(text), 4.0)

    def test_job_year_range_uses_minimum_required_years(self) -> None:
        resume = "Python FastAPI engineer with 3+ years of API delivery experience."
        job = "Requirements\n3-5 years of Python and FastAPI backend API experience."

        result = analyze_resume(resume, job)

        self.assertEqual(result["profile"]["required_experience_years"], 3.0)

    def test_section_detection_handles_markdown_headings(self) -> None:
        text = "## Technical Skills: Python, FastAPI, SQL\n### Professional Experience\nBuilt APIs."

        sections = detect_sections(text, RESUME_SECTION_ALIASES)

        self.assertIn("Skills", sections)
        self.assertIn("Experience", sections)

    def test_analyze_resume_returns_positive_match(self) -> None:
        resume = "Python NLP developer with FastAPI, SQL, Docker, Git, and REST API experience."
        job = "Looking for a Python engineer with NLP, FastAPI, SQL, Docker, and Git skills."
        result = analyze_resume(resume, job)

        self.assertGreaterEqual(result["scores"]["final_score"], 60)
        self.assertIn("Python", result["skill_gap"]["matched"])
        self.assertIn(result["verdict"], {"Competitive match", "Strong match", "Excellent match"})
        self.assertIn("profile", result)
        self.assertIn("ats_analysis", result)

    def test_sample_analysis_endpoint(self) -> None:
        response = self.client.get("/analyze/sample")
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(payload["scores"]["final_score"], 70)
        self.assertIn("Python", payload["resume_skills"])
        self.assertIn("FastAPI", payload["job_skills"])
        self.assertIn("section_analysis", payload)
        self.assertIn("category_scores", payload)

    def test_root_serves_frontend(self) -> None:
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers["content-type"])
        self.assertIn("AI Resume Analyzer", response.text)

    def test_samples_endpoint_returns_seed_content(self) -> None:
        response = self.client.get("/samples")
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertIn("resume_text", payload)
        self.assertIn("job_description", payload)
        self.assertIn("Python", payload["resume_text"])

    def test_parse_txt_file_endpoint(self) -> None:
        response = self.client.post(
            "/parse-file",
            files={"file": ("resume.txt", b"Python NLP FastAPI SQL Docker", "text/plain")},
        )
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["extension"], ".txt")
        self.assertIn("Python", payload["extracted_text"])

    def test_parse_docx_file_endpoint(self) -> None:
        response = self.client.post(
            "/parse-file",
            files={
                "file": (
                    "resume.docx",
                    build_docx_bytes("Python NLP FastAPI SQL"),
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            },
        )
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["extension"], ".docx")
        self.assertIn("FastAPI", payload["extracted_text"])

    def test_parse_pdf_file_endpoint(self) -> None:
        response = self.client.post(
            "/parse-file",
            files={"file": ("resume.pdf", build_pdf_bytes("Python NLP FastAPI SQL"), "application/pdf")},
        )
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["extension"], ".pdf")
        self.assertIn("NLP", payload["extracted_text"])

    def test_analyze_files_endpoint(self) -> None:
        response = self.client.post(
            "/analyze-files",
            files={
                "resume_file": ("resume.txt", b"Python NLP FastAPI SQL Docker Git", "text/plain"),
                "job_file": (
                    "job.docx",
                    build_docx_bytes("Hiring a Python NLP engineer with FastAPI SQL and Git."),
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                ),
            },
        )
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(payload["scores"]["final_score"], 60)
        self.assertIn("Python", payload["skill_gap"]["matched"])

    def test_extract_skills_file_preserves_contact_lines(self) -> None:
        payload = b"Riya Sharma\nriya@example.com\n9876543210\nPython NLP FastAPI SQL"
        response = self.client.post(
            "/extract-skills/file",
            files={"file": ("resume.txt", payload, "text/plain")},
        )
        data = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(data["contact_info"]["name"], "Riya Sharma")
        self.assertEqual(data["contact_info"]["email"], "riya@example.com")


if __name__ == "__main__":
    unittest.main()
