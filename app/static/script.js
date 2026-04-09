const resumeInput = document.getElementById("resume-text");
const jobInput = document.getElementById("job-description");
const resumeFileInput = document.getElementById("resume-file");
const jobFileInput = document.getElementById("job-file");
const resumeFileName = document.getElementById("resume-file-name");
const jobFileName = document.getElementById("job-file-name");
const analyzeButton = document.getElementById("analyze-button");
const extractButton = document.getElementById("extract-button");
const analyzeFilesButton = document.getElementById("analyze-files-button");
const loadSampleButton = document.getElementById("load-sample");
const resetButton = document.getElementById("reset-button");
const copySummaryButton = document.getElementById("copy-summary-button");
const copySummaryInlineButton = document.getElementById("copy-summary-inline");
const statusLine = document.getElementById("status");
const verdictPill = document.getElementById("verdict-pill");

const heroElements = {
  score: document.getElementById("hero-score"),
  role: document.getElementById("hero-role"),
  seniority: document.getElementById("hero-seniority"),
  ats: document.getElementById("hero-ats"),
};

const ringElements = {
  final: { card: document.getElementById("final-ring"), label: document.getElementById("final-score") },
  skill: { card: document.getElementById("skill-ring"), label: document.getElementById("skill-score") },
  ats: { card: document.getElementById("ats-ring"), label: document.getElementById("ats-score") },
  keyword: { card: document.getElementById("keyword-ring"), label: document.getElementById("keyword-score") },
};

const metricElements = {
  similarity: {
    label: document.getElementById("similarity-score"),
    fill: document.getElementById("similarity-fill"),
  },
  section: {
    label: document.getElementById("section-score"),
    fill: document.getElementById("section-fill"),
  },
  experience: {
    label: document.getElementById("experience-score"),
    fill: document.getElementById("experience-fill"),
  },
  ats: {
    label: document.getElementById("ats-mini-score"),
    fill: document.getElementById("ats-fill"),
  },
};

const profileElements = {
  role: document.getElementById("profile-role"),
  resumeSeniority: document.getElementById("profile-resume-seniority"),
  jobSeniority: document.getElementById("profile-job-seniority"),
  experience: document.getElementById("profile-experience"),
  required: document.getElementById("profile-required"),
  label: document.getElementById("profile-experience-label"),
};

const contactElements = {
  name: document.getElementById("contact-name"),
  email: document.getElementById("contact-email"),
  phone: document.getElementById("contact-phone"),
};

const textElements = {
  summary: document.getElementById("summary-text"),
};

const listElements = {
  presentSections: document.getElementById("present-sections-list"),
  missingSections: document.getElementById("missing-sections-list"),
  atsStrengths: document.getElementById("ats-strengths-list"),
  atsIssues: document.getElementById("ats-issues-list"),
  resumeSkills: document.getElementById("resume-skills-list"),
  jobSkills: document.getElementById("job-skills-list"),
  matched: document.getElementById("matched-list"),
  missing: document.getElementById("missing-list"),
  strengths: document.getElementById("strengths-list"),
  recommendations: document.getElementById("recommendations-list"),
  priorities: document.getElementById("priority-list"),
  risks: document.getElementById("risk-list"),
  overlap: document.getElementById("overlap-list"),
  resumeKeywords: document.getElementById("resume-keywords-list"),
  jobKeywords: document.getElementById("job-keywords-list"),
};

const categoryScoreList = document.getElementById("category-score-list");

const extractedFileCache = {
  resume: null,
  job: null,
};

let latestAnalysis = null;

function setStatus(message) {
  statusLine.textContent = message;
}

function clampScore(value) {
  return Math.max(0, Math.min(100, Math.round(value || 0)));
}

function buildFileSignature(file) {
  return `${file.name}:${file.size}:${file.lastModified}`;
}

function formatPercent(value) {
  return `${clampScore(value)}%`;
}

function formatYears(value, fallback = "N/A") {
  if (value === null || value === undefined) {
    return fallback;
  }
  return `${Number(value).toFixed(Number.isInteger(value) ? 0 : 1)} years`;
}

function setLoading(isLoading) {
  analyzeButton.disabled = isLoading;
  extractButton.disabled = isLoading;
  analyzeFilesButton.disabled = isLoading;
  loadSampleButton.disabled = isLoading;
  resetButton.disabled = isLoading;
  copySummaryButton.disabled = isLoading;
  copySummaryInlineButton.disabled = isLoading;
  resumeFileInput.disabled = isLoading;
  jobFileInput.disabled = isLoading;
}

function renderTagList(listNode, items, emptyLabel) {
  listNode.innerHTML = "";
  const values = Array.isArray(items) ? items : [];

  if (!values.length) {
    const item = document.createElement("li");
    item.className = "is-empty";
    item.textContent = emptyLabel;
    listNode.appendChild(item);
    return;
  }

  values.forEach((value) => {
    const item = document.createElement("li");
    item.textContent = value;
    listNode.appendChild(item);
  });
}

function renderDetailList(listNode, items, emptyLabel) {
  listNode.innerHTML = "";
  const values = Array.isArray(items) ? items : [];

  if (!values.length) {
    const item = document.createElement("li");
    item.textContent = emptyLabel;
    listNode.appendChild(item);
    return;
  }

  values.forEach((value) => {
    const item = document.createElement("li");
    item.textContent = value;
    listNode.appendChild(item);
  });
}

function setRingValue(ringElement, value) {
  const score = clampScore(value);
  ringElement.card.style.setProperty("--score", `${score}`);
  ringElement.label.textContent = `${score}%`;
}

function setMetricValue(metricElement, value) {
  const score = clampScore(value);
  metricElement.label.textContent = `${score}%`;
  metricElement.fill.style.width = `${score}%`;
}

function setVerdictTone(score, label) {
  verdictPill.textContent = label;
  verdictPill.classList.remove("score-high", "score-medium", "score-low");

  if (score >= 75) {
    verdictPill.classList.add("score-high");
    return;
  }
  if (score >= 50) {
    verdictPill.classList.add("score-medium");
    return;
  }
  verdictPill.classList.add("score-low");
}

function buildUiSummary(data, finalScore, atsScore) {
  const role = data.profile?.inferred_role || "Role N/A";
  return `${role}. Fit ${formatPercent(finalScore)}. ATS ${formatPercent(atsScore)}.`;
}

function updateHero(role, seniority, overallScore, atsScore) {
  heroElements.score.textContent = formatPercent(overallScore);
  heroElements.role.textContent = role || "Waiting";
  heroElements.seniority.textContent = seniority || "N/A";
  heroElements.ats.textContent = atsScore === null ? "--" : formatPercent(atsScore);
}

function updateContactInfo(contactInfo = {}) {
  contactElements.name.textContent = contactInfo.name || "N/A";
  contactElements.email.textContent = contactInfo.email || "N/A";
  contactElements.phone.textContent = contactInfo.phone || "N/A";
}

function updateProfile(profile = {}) {
  profileElements.role.textContent = profile.inferred_role || "N/A";
  profileElements.resumeSeniority.textContent = profile.resume_seniority || "N/A";
  profileElements.jobSeniority.textContent = profile.job_seniority || "N/A";
  profileElements.experience.textContent = formatYears(profile.estimated_experience_years, "N/A");
  profileElements.required.textContent = formatYears(profile.required_experience_years, "N/A");
  profileElements.label.textContent = profile.experience_alignment_label || "N/A";
}

function renderCategoryScores(scores) {
  categoryScoreList.innerHTML = "";
  const values = Array.isArray(scores) ? scores : [];

  if (!values.length) {
    const empty = document.createElement("div");
    empty.className = "category-row";
    empty.textContent = "Run analysis.";
    categoryScoreList.appendChild(empty);
    return;
  }

  values.forEach((score) => {
    const row = document.createElement("article");
    row.className = "category-row";

    const head = document.createElement("div");
    head.className = "category-row-head";

    const name = document.createElement("strong");
    name.textContent = score.category;

    const value = document.createElement("span");
    value.textContent = `${clampScore(score.score)}%`;

    head.appendChild(name);
    head.appendChild(value);

    const track = document.createElement("div");
    track.className = "category-track";

    const fill = document.createElement("span");
    fill.className = "category-fill";
    fill.style.width = `${clampScore(score.score)}%`;
    track.appendChild(fill);

    const meta = document.createElement("div");
    meta.className = "category-meta";

    const matched = document.createElement("span");
    matched.textContent = `Matched: ${score.matched_count}/${score.required_count}`;

    const missing = document.createElement("span");
    missing.textContent = score.missing.length
      ? `Missing: ${score.missing.slice(0, 3).join(", ")}`
      : "Missing: None";

    meta.appendChild(matched);
    meta.appendChild(missing);

    row.appendChild(head);
    row.appendChild(track);
    row.appendChild(meta);
    categoryScoreList.appendChild(row);
  });
}

function clearListsForExtraction() {
  renderTagList(listElements.jobSkills, [], "Run analysis");
  renderTagList(listElements.matched, [], "Run analysis");
  renderTagList(listElements.missing, [], "Run analysis");
  renderDetailList(listElements.atsStrengths, [], "Run analysis");
  renderDetailList(listElements.atsIssues, [], "Run analysis");
  renderDetailList(listElements.strengths, [], "Run analysis");
  renderDetailList(listElements.recommendations, [], "Run analysis");
  renderDetailList(listElements.priorities, [], "Run analysis");
  renderDetailList(listElements.risks, [], "Run analysis");
  renderTagList(listElements.overlap, [], "Run analysis");
  renderTagList(listElements.jobKeywords, [], "Run analysis");
  renderCategoryScores([]);
}

function resetResultView() {
  latestAnalysis = null;
  textElements.summary.textContent = "Run analysis.";
  updateHero("Waiting", "N/A", 0, null);
  updateProfile({});
  updateContactInfo({});
  setVerdictTone(0, "Waiting");

  setRingValue(ringElements.final, 0);
  setRingValue(ringElements.skill, 0);
  setRingValue(ringElements.ats, 0);
  setRingValue(ringElements.keyword, 0);
  setMetricValue(metricElements.similarity, 0);
  setMetricValue(metricElements.section, 0);
  setMetricValue(metricElements.experience, 0);
  setMetricValue(metricElements.ats, 0);

  renderTagList(listElements.presentSections, [], "None");
  renderTagList(listElements.missingSections, [], "None");
  renderTagList(listElements.resumeSkills, [], "None");
  renderTagList(listElements.jobSkills, [], "None");
  renderTagList(listElements.matched, [], "None");
  renderTagList(listElements.missing, [], "None");
  renderTagList(listElements.overlap, [], "None");
  renderTagList(listElements.resumeKeywords, [], "None");
  renderTagList(listElements.jobKeywords, [], "None");
  renderDetailList(listElements.atsStrengths, [], "None");
  renderDetailList(listElements.atsIssues, [], "None");
  renderDetailList(listElements.strengths, [], "None");
  renderDetailList(listElements.recommendations, [], "None");
  renderDetailList(listElements.priorities, [], "None");
  renderDetailList(listElements.risks, [], "None");
  renderCategoryScores([]);
}

function renderAnalysis(data) {
  latestAnalysis = data;
  const finalScore = data.scores?.final_score || 0;
  const atsScore = data.ats_analysis?.score || data.scores?.ats_readiness || 0;

  textElements.summary.textContent = buildUiSummary(data, finalScore, atsScore);
  updateHero(
    data.profile?.inferred_role,
    data.profile?.resume_seniority,
    finalScore,
    atsScore,
  );
  updateProfile(data.profile);
  updateContactInfo(data.contact_info);

  setVerdictTone(finalScore, data.verdict || "Done");
  setRingValue(ringElements.final, finalScore);
  setRingValue(ringElements.skill, data.scores?.skill_match || 0);
  setRingValue(ringElements.ats, atsScore);
  setRingValue(ringElements.keyword, data.scores?.keyword_alignment || 0);

  setMetricValue(metricElements.similarity, data.scores?.document_similarity || 0);
  setMetricValue(metricElements.section, data.scores?.section_alignment || 0);
  setMetricValue(metricElements.experience, data.scores?.experience_alignment || 0);
  setMetricValue(metricElements.ats, atsScore);

  renderTagList(
    listElements.presentSections,
    data.section_analysis?.present_sections,
    "None",
  );
  renderTagList(
    listElements.missingSections,
    data.section_analysis?.missing_sections,
    "None",
  );
  renderDetailList(
    listElements.atsStrengths,
    data.ats_analysis?.strengths,
    "None",
  );
  renderDetailList(
    listElements.atsIssues,
    data.ats_analysis?.issues,
    "None",
  );
  renderCategoryScores(data.category_scores);
  renderTagList(listElements.resumeSkills, data.resume_skills, "None");
  renderTagList(listElements.jobSkills, data.job_skills, "None");
  renderTagList(listElements.matched, data.skill_gap?.matched, "None");
  renderTagList(listElements.missing, data.skill_gap?.missing, "None");
  renderDetailList(listElements.strengths, data.insights?.strengths, "None");
  renderDetailList(
    listElements.recommendations,
    data.insights?.recommendations,
    "None",
  );
  renderDetailList(
    listElements.priorities,
    data.insights?.priority_actions,
    "None",
  );
  renderDetailList(listElements.risks, data.insights?.risk_flags, "None");
  renderTagList(listElements.overlap, data.keyword_overlap, "None");
  renderTagList(listElements.resumeKeywords, data.resume_keywords, "None");
  renderTagList(listElements.jobKeywords, data.job_keywords, "None");
}

function renderExtraction(data) {
  latestAnalysis = null;
  const sectionScore = Math.min((data.sections_detected?.length || 0) * 17, 100);
  const skillDensityScore = Math.min((data.extracted_skills?.length || 0) * 8, 100);

  textElements.summary.textContent = `Extracted ${data.extracted_skills.length} skills, ${
    data.sections_detected.length
  } sections.`;

  updateHero(
    data.inferred_role,
    data.estimated_experience_years ? formatYears(data.estimated_experience_years, "Emerging") : "Emerging",
    0,
    null,
  );
  updateProfile({
    inferred_role: data.inferred_role,
    resume_seniority: data.estimated_experience_years ? "Estimated" : "Emerging",
    job_seniority: "N/A",
    estimated_experience_years: data.estimated_experience_years,
    required_experience_years: null,
    experience_alignment_label: "Run match",
  });
  updateContactInfo(data.contact_info);

  setVerdictTone(52, "Profile extracted");
  setRingValue(ringElements.final, 0);
  setRingValue(ringElements.skill, skillDensityScore);
  setRingValue(ringElements.ats, 0);
  setRingValue(ringElements.keyword, 0);
  setMetricValue(metricElements.similarity, 0);
  setMetricValue(metricElements.section, sectionScore);
  setMetricValue(metricElements.experience, data.estimated_experience_years ? 60 : 30);
  setMetricValue(metricElements.ats, 0);

  renderTagList(listElements.presentSections, data.sections_detected, "None");
  renderTagList(listElements.missingSections, [], "Run analysis");
  renderTagList(listElements.resumeSkills, data.extracted_skills, "None");
  renderTagList(listElements.resumeKeywords, data.keyword_candidates, "None");
  clearListsForExtraction();
}

function buildRecruiterSummary(data) {
  if (!data) {
    return "";
  }

  const lines = [
    data.insights?.summary || data.verdict || "Resume analysis summary",
    `Role: ${data.profile?.inferred_role || "N/A"}`,
    `Level: ${data.profile?.resume_seniority || "N/A"} vs ${data.profile?.job_seniority || "N/A"}`,
    `Fit: ${formatPercent(data.scores?.final_score || 0)}`,
    `ATS: ${formatPercent(data.ats_analysis?.score || data.scores?.ats_readiness || 0)}`,
  ];

  if (Array.isArray(data.insights?.strengths) && data.insights.strengths.length) {
    lines.push(`Strengths: ${data.insights.strengths.slice(0, 3).join(" | ")}`);
  }

  if (Array.isArray(data.insights?.priority_actions) && data.insights.priority_actions.length) {
    lines.push(`Priority: ${data.insights.priority_actions.slice(0, 3).join(" | ")}`);
  }

  return lines.join("\n");
}

async function copyRecruiterSummary() {
  if (!latestAnalysis) {
    setStatus("Run analysis first.");
    return;
  }

  const summary = buildRecruiterSummary(latestAnalysis);
  try {
    await navigator.clipboard.writeText(summary);
    setStatus("Copied.");
  } catch (error) {
    setStatus("Copy failed.");
  }
}

async function postJson(url, payload) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const errorPayload = await response.json().catch(() => ({}));
    const detail = errorPayload.detail || "Request failed.";
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }

  return response.json();
}

async function uploadForText(file) {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch("/parse-file", {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    const errorPayload = await response.json().catch(() => ({}));
    const detail = errorPayload.detail || "File upload failed.";
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }

  return response.json();
}

async function handleAnalyze() {
  if (!resumeInput.value.trim() || !jobInput.value.trim()) {
    setStatus("Add resume + job.");
    return;
  }

  try {
    setLoading(true);
    setStatus("Analyzing...");
    const data = await postJson("/analyze", {
      resume_text: resumeInput.value,
      job_description: jobInput.value,
    });
    renderAnalysis(data);
    setStatus("Done.");
  } catch (error) {
    setStatus(error.message);
  } finally {
    setLoading(false);
  }
}

async function handleExtract() {
  if (!resumeInput.value.trim()) {
    setStatus("Add resume.");
    return;
  }

  try {
    setLoading(true);
    setStatus("Extracting...");
    const data = await postJson("/extract-skills", {
      text: resumeInput.value,
    });
    renderExtraction(data);
    setStatus("Extracted.");
  } catch (error) {
    setStatus(error.message);
  } finally {
    setLoading(false);
  }
}

async function handleAnalyzeFiles() {
  const resumeFile = resumeFileInput.files?.[0];
  const jobFile = jobFileInput.files?.[0];

  if (!resumeFile || !jobFile) {
    setStatus("Choose both files.");
    return;
  }

  try {
    setLoading(true);
    const resumeSignature = buildFileSignature(resumeFile);
    const jobSignature = buildFileSignature(jobFile);

    let data;
    if (
      extractedFileCache.resume?.signature === resumeSignature &&
      extractedFileCache.job?.signature === jobSignature
    ) {
      setStatus("Analyzing...");
      data = await postJson("/analyze", {
        resume_text: extractedFileCache.resume.text,
        job_description: extractedFileCache.job.text,
      });
    } else {
      setStatus("Analyzing files...");
      const formData = new FormData();
      formData.append("resume_file", resumeFile);
      formData.append("job_file", jobFile);

      const response = await fetch("/analyze-files", {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        const errorPayload = await response.json().catch(() => ({}));
        const detail = errorPayload.detail || "File analysis failed.";
        throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
      }

      data = await response.json();
    }

    renderAnalysis(data);
    setStatus("Done.");
  } catch (error) {
    setStatus(error.message);
  } finally {
    setLoading(false);
  }
}

async function loadSample() {
  try {
    setLoading(true);
    setStatus("Loading sample...");
    const response = await fetch("/samples");
    if (!response.ok) {
      throw new Error("Unable to load sample content.");
    }

    const data = await response.json();
    resumeInput.value = data.resume_text || "";
    jobInput.value = data.job_description || "";
    extractedFileCache.resume = null;
    extractedFileCache.job = null;
    setStatus("Loaded. Analyzing...");
    await handleAnalyze();
  } catch (error) {
    setStatus(error.message);
  } finally {
    setLoading(false);
  }
}

async function handleFileSelection(input, targetTextArea, nameNode, label) {
  const selectedFile = input.files?.[0];
  if (!selectedFile) {
    return;
  }

  const cacheKey = label === "Resume" ? "resume" : "job";

  try {
    setLoading(true);
    nameNode.textContent = selectedFile.name;
    setStatus(`Extracting ${label.toLowerCase()}...`);
    const data = await uploadForText(selectedFile);
    targetTextArea.value = data.extracted_text;
    extractedFileCache[cacheKey] = {
      signature: buildFileSignature(selectedFile),
      text: data.extracted_text,
    };
    nameNode.textContent = `${selectedFile.name} - ${data.char_count} chars`;
    setStatus("Loaded.");
  } catch (error) {
    extractedFileCache[cacheKey] = null;
    nameNode.textContent = cacheKey === "resume" ? "TXT/DOCX/PDF" : "Upload JD";
    setStatus(error.message);
  } finally {
    setLoading(false);
  }
}

function resetWorkspace() {
  resumeInput.value = "";
  jobInput.value = "";
  resumeFileInput.value = "";
  jobFileInput.value = "";
  resumeFileName.textContent = "TXT/DOCX/PDF";
  jobFileName.textContent = "Upload JD";
  extractedFileCache.resume = null;
  extractedFileCache.job = null;
  resetResultView();
  setStatus("Reset.");
}

function attachTiltEffects() {
  const cards = document.querySelectorAll("[data-tilt]");
  cards.forEach((card) => {
    card.addEventListener("pointermove", (event) => {
      if (window.innerWidth < 900) {
        return;
      }

      const bounds = card.getBoundingClientRect();
      const x = (event.clientX - bounds.left) / bounds.width;
      const y = (event.clientY - bounds.top) / bounds.height;
      const rotateY = (x - 0.5) * 10;
      const rotateX = (0.5 - y) * 8;
      card.style.transform = `perspective(1200px) rotateX(${rotateX}deg) rotateY(${rotateY}deg) translateY(-2px)`;
      card.style.boxShadow = "0 34px 80px rgba(16, 35, 63, 0.18)";
    });

    card.addEventListener("pointerleave", () => {
      card.style.transform = "";
      card.style.boxShadow = "";
    });
  });
}

analyzeButton.addEventListener("click", handleAnalyze);
extractButton.addEventListener("click", handleExtract);
analyzeFilesButton.addEventListener("click", handleAnalyzeFiles);
loadSampleButton.addEventListener("click", loadSample);
resetButton.addEventListener("click", resetWorkspace);
copySummaryButton.addEventListener("click", copyRecruiterSummary);
copySummaryInlineButton.addEventListener("click", copyRecruiterSummary);
resumeFileInput.addEventListener("change", () =>
  handleFileSelection(resumeFileInput, resumeInput, resumeFileName, "Resume"),
);
jobFileInput.addEventListener("change", () =>
  handleFileSelection(jobFileInput, jobInput, jobFileName, "Job"),
);

resetResultView();
attachTiltEffects();
