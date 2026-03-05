import io
import re
import os
import requests
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import streamlit as st

try:
    import pytesseract
    from PIL import Image, ImageGrab
except Exception:  # optional runtime dependency errors are surfaced in UI
    pytesseract = None
    Image = None
    ImageGrab = None

try:
    from pypdf import PdfReader
except Exception:
    PdfReader = None


FIELD_KEYWORDS: Dict[str, List[str]] = {
    "Software Engineering": ["python", "java", "javascript", "typescript", "c++", "backend", "frontend", "full stack", "software engineer", "developer", "api", "microservices"],
    "Data & AI": ["data scientist", "machine learning", "deep learning", "nlp", "computer vision", "analytics", "sql", "pandas", "tensorflow", "pytorch"],
    "Product & Project Management": ["product manager", "project manager", "scrum", "agile", "roadmap", "stakeholder"],
    "Design": ["ux", "ui", "figma", "adobe", "interaction design", "visual design"],
    "Operations & Support": ["operations", "devops", "sre", "it support", "help desk", "incident", "infrastructure"],
    "Sales & Marketing": ["sales", "marketing", "seo", "content", "growth", "business development"],
    "Finance & Accounting": ["finance", "accounting", "fp&a", "audit", "tax", "bookkeeping"],
}


@dataclass
class ResumeInsights:
    summary: str
    highlights: List[str]
    years_experience: str
    fields: List[str]
    confidence_note: str
    work_history: List["WorkEntry"]
    education_lines: List[str]
    skills: List[str]
    impact_signals: List[str]


@dataclass
class WorkEntry:
    title: str
    company: str
    dates: str
    bullets: List[str]


def extract_skills(text: str, limit: int = 12) -> List[str]:
    lower = text.lower()
    found = []
    seen = set()
    for keywords in FIELD_KEYWORDS.values():
        for keyword in keywords:
            if keyword in lower and keyword not in seen:
                found.append(keyword.title())
                seen.add(keyword)

    common_skills = [
        "aws", "azure", "gcp", "docker", "kubernetes", "react", "node", "django", "flask",
        "excel", "power bi", "tableau", "jira", "git", "linux", "postgres", "mongodb",
    ]
    for skill in common_skills:
        if skill in lower and skill not in seen:
            found.append(skill.title())
            seen.add(skill)

    return found[:limit]


def extract_education(text: str) -> List[str]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    education_terms = [
        "bachelor", "master", "phd", "mba", "b.sc", "m.sc", "education", "university", "college", "certification", "certified"
    ]
    matches = [line for line in lines if any(term in line.lower() for term in education_terms)]
    return matches[:3]


def extract_responsibilities(text: str) -> List[str]:
    responsibility_terms = ["managed", "led", "built", "developed", "designed", "owned", "delivered", "implemented", "created"]
    candidates = sentence_split(text) + [line.strip() for line in text.splitlines() if line.strip()]
    matches = []
    seen = set()
    for line in candidates:
        compact = re.sub(r"\s+", " ", line).strip()
        key = compact.lower()
        if key in seen:
            continue
        if len(compact.split()) < 3 or len(compact) > 220:
            continue
        if any(term in key for term in responsibility_terms):
            seen.add(key)
            matches.append(compact)
    return matches[:4]


def extract_impact(text: str) -> List[str]:
    candidates = sentence_split(text) + [line.strip() for line in text.splitlines() if line.strip()]
    impact_patterns = [r"\d+%", r"\$\d+", r"\d+\s*(k|m|b)", r"increased", r"reduced", r"improved", r"saved"]
    matches = []
    seen = set()
    for line in candidates:
        compact = re.sub(r"\s+", " ", line).strip()
        key = compact.lower()
        if key in seen:
            continue
        if len(compact.split()) < 3 or len(compact) > 220:
            continue
        if any(re.search(pattern, key) for pattern in impact_patterns):
            seen.add(key)
            matches.append(compact)
    return matches[:3]


def build_structured_highlights(text: str) -> List[str]:
    skills = extract_skills(text)
    education = extract_education(text)
    responsibilities = extract_responsibilities(text)
    impact = extract_impact(text)

    highlights = []
    highlights.append(
        "**Skills:** " + (", ".join(skills) if skills else "Not clearly listed in extracted text.")
    )
    highlights.append(
        "**Education/Certifications:** " + (" | ".join(education) if education else "Not clearly listed in extracted text.")
    )
    highlights.append(
        "**Core Responsibilities:** " + (" | ".join(responsibilities) if responsibilities else "Not clearly listed in extracted text.")
    )
    highlights.append(
        "**Impact & Outcomes:** " + (" | ".join(impact) if impact else "No quantified impact statements clearly detected.")
    )
    return highlights





def call_groq(api_key: str, model: str, prompt: str, max_tokens: int = 2048) -> str:
    """Send a prompt to Groq and return the response text."""
    if not api_key.strip():
        raise RuntimeError("Groq API key is required.")
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.3,
    }
    response = requests.post(url, json=body, headers=headers, timeout=(8, 90))
    response.raise_for_status()
    data = response.json()
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("Groq returned no choices.")
    return (choices[0].get("message") or {}).get("content", "").strip()








def build_groq_recruiter_summary(
    text: str,
    api_key: str,
    model: str = "llama-3.3-70b-versatile",
    max_input_chars: int = 12000,
) -> str:
    prompt = (
        "You are a senior technical recruiter writing a detailed candidate brief for a hiring manager. "
        "Read the full resume carefully and return a structured report with these labeled sections:\n"
        "(1) Candidate Overview — 3 to 4 sentences on career level, domain, and trajectory.\n"
        "(2) Recruiter Take — 2 sentences on fit, role suggestions, and any red flags.\n"
        "(3) Work History — for each role list the job title, company, dates, and 2 to 3 specific responsibilities or achievements including technologies and team scope.\n"
        "(4) Skills and Tools — group technical skills, languages, frameworks, and platforms.\n"
        "(5) Education and Certifications — degrees, schools, years, and certs.\n"
        "(6) Key Achievements — 3 to 5 quantified wins with real numbers from the resume.\n"
        "Use actual details from the resume. Do not be vague or generic.\n\n"
        f"Resume:\n{text[:max_input_chars]}"
    )
    return call_groq(api_key, model, prompt, max_tokens=2048)


def build_fallback_highlight_bullets(resume_text: str) -> List[str]:
    skills = ", ".join(extract_skills(resume_text, limit=8))
    education = " | ".join(extract_education(resume_text)[:2])
    responsibilities = " | ".join(extract_responsibilities(resume_text)[:2])
    impact = " | ".join(extract_impact(resume_text)[:2])

    def tidy(value: str) -> str:
        return value.rstrip(" .")

    bullets = []
    if skills:
        bullets.append(f"Top skills include {tidy(skills)}.")
    if education:
        bullets.append(f"Education/certifications noted: {tidy(education)}.")
    if responsibilities:
        bullets.append(f"Core responsibilities include: {tidy(responsibilities)}.")
    if impact:
        bullets.append(f"Impact highlights: {tidy(impact)}.")

    if not bullets:
        bullets.append("Resume contains limited structured details; review extracted text quality and OCR output.")
    return bullets[:5]
def coerce_highlight_sections(answer: str, resume_text: str) -> List[str]:
    lines = [line.strip() for line in answer.splitlines() if line.strip()]

    cleaned = []
    for line in lines:
        item = re.sub(r"^[-*\d\.)\s]+", "", line).strip()
        item = re.sub(r"^\*\*", "", item).strip()
        item = re.sub(r"\*\*$", "", item).strip()
        if item:
            cleaned.append(item)

    if cleaned:
        # prefer concise recruiter-friendly bullets
        return cleaned[:6]

    compact = re.sub(r"\s+", " ", answer.strip())
    if compact:
        return [compact[:240]]

    return build_fallback_highlight_bullets(resume_text)



def extract_text_from_pdf(file_bytes: bytes) -> str:
    if PdfReader is None:
        return ""
    with io.BytesIO(file_bytes) as data:
        reader = PdfReader(data)
        pages = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(pages).strip()


def extract_text_from_image(file_bytes: bytes) -> str:
    if pytesseract is None or Image is None:
        return ""
    image = Image.open(io.BytesIO(file_bytes))
    return pytesseract.image_to_string(image)


def capture_screen_text() -> Tuple[str, str]:
    if ImageGrab is None or pytesseract is None:
        return "", "Screen capture/OCR dependencies are unavailable in this environment."
    try:
        screenshot = ImageGrab.grab()
        text = pytesseract.image_to_string(screenshot)
        return text, ""
    except Exception as exc:
        return "", f"Unable to capture screen: {exc}"


def infer_fields(text: str) -> List[str]:
    lower_text = text.lower()
    detected = []
    for field, keywords in FIELD_KEYWORDS.items():
        if any(keyword in lower_text for keyword in keywords):
            detected.append(field)
    return detected or ["General / Unspecified"]


def estimate_years_experience(text: str) -> str:
    patterns = [
        r"(\d{1,2})\+?\s+years?\s+of\s+experience",
        r"experience\s*[:\-]?\s*(\d{1,2})\+?\s+years?",
        r"(\d{1,2})\+?\s+years?\s+experience",
    ]
    years = []
    for pattern in patterns:
        matches = re.findall(pattern, text, flags=re.IGNORECASE)
        years.extend(int(m) for m in matches)

    if years:
        return f"~{max(years)} years (based on explicit resume statements)"

    year_matches = re.findall(r"\b(19\d{2}|20\d{2})\b", text)
    if len(year_matches) >= 2:
        years_int = sorted({int(y) for y in year_matches})
        span = years_int[-1] - years_int[0]
        if 0 < span < 50:
            return f"~{span} years (estimated from timeline)"

    return "Not clearly stated"


def sentence_split(text: str) -> List[str]:
    normalized = text.replace("\r", "\n")
    pieces = re.split(r"(?<=[.!?])\s+|\n+", normalized)
    return [s.strip() for s in pieces if s.strip()]


def looks_like_resume(text: str) -> bool:
    lower = text.lower()
    resume_markers = [
        "experience",
        "education",
        "skills",
        "work history",
        "employment",
        "certifications",
        "projects",
    ]
    marker_hits = sum(marker in lower for marker in resume_markers)
    year_hits = len(re.findall(r"\b(19\d{2}|20\d{2})\b", text))
    return marker_hits >= 2 or (marker_hits >= 1 and year_hits >= 2)


def extract_certifications(text: str) -> List[str]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    cert_terms = ["certified", "certification", "certificate", "aws ", "azure ", "pmp", "scrum master"]
    return [line for line in lines if any(term in line.lower() for term in cert_terms)][:4]


def extract_locations(text: str) -> List[str]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    pattern = re.compile(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*,\s*[A-Z]{2}\b")
    found: List[str] = []
    for line in lines:
        if any(tag in line.lower() for tag in ["remote", "hybrid", "onsite", "on-site"]):
            found.append(line)
        found.extend(pattern.findall(line))
    deduped = []
    seen = set()
    for item in found:
        key = item.lower()
        if key not in seen:
            seen.add(key)
            deduped.append(item)
    return deduped[:4]


def extract_keyword_signals(text: str) -> List[str]:
    signals = []
    lower = text.lower()
    for field, words in FIELD_KEYWORDS.items():
        if any(word in lower for word in words):
            signals.append(field)
    return signals[:4]


def _line_has_date(line: str) -> Optional[str]:
    date_pattern = re.compile(
        r"((?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{4}|\d{1,2}/\d{4}|\d{4})\s*[-–]\s*(present|current|now|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{4}|\d{1,2}/\d{4}|\d{4})",
        flags=re.IGNORECASE,
    )
    match = date_pattern.search(line)
    return match.group(0) if match else None


def _looks_like_role_anchor(line: str) -> bool:
    lower = line.lower()
    if _line_has_date(line):
        return True
    if any(sep in line for sep in [" | ", " - ", " — ", " at "]):
        return True
    title_terms = ["engineer", "manager", "developer", "analyst", "consultant", "director", "intern", "lead"]
    return any(re.search(rf"\b{re.escape(term)}\b", lower) for term in title_terms) and len(line.split()) >= 2


def _parse_title_company_dates(line: str, next_line: str = "") -> Tuple[str, str, str]:
    dates = _line_has_date(line) or _line_has_date(next_line) or ""
    line_no_dates = line.replace(dates, "").strip(" -|—") if dates else line
    title = line_no_dates.strip()
    company = ""

    if " at " in line_no_dates.lower():
        parts = re.split(r"\bat\b", line_no_dates, flags=re.IGNORECASE, maxsplit=1)
        if len(parts) == 2:
            title, company = parts[0].strip(" -|—"), parts[1].strip(" -|—")
    elif " | " in line_no_dates:
        parts = [p.strip() for p in line_no_dates.split(" | ") if p.strip()]
        if len(parts) >= 2:
            title, company = parts[0], parts[1]
    elif " - " in line_no_dates:
        parts = [p.strip() for p in line_no_dates.split(" - ") if p.strip()]
        if len(parts) >= 2:
            title, company = parts[0], parts[1]

    if not company and next_line and len(next_line.split()) <= 8 and not _line_has_date(next_line):
        company = next_line.strip()

    return title or "Role not clearly stated", company, dates


def extract_work_history(text: str, max_roles: int = 5) -> List[WorkEntry]:
    """Heuristic role parser for experience blocks.

    Sanity check examples:
    - "Senior Engineer - Acme Corp | Jan 2021 - Present" should parse title/company/dates.
    - OCR-ish lines with bullets under a role should produce <=3 short bullets.
    """
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return []

    headers = ["experience", "work experience", "employment", "professional experience"]
    stop_headers = ["education", "skills", "projects", "certifications", "summary"]

    start_idx = 0
    for i, line in enumerate(lines):
        lower = line.lower()
        if any(h == lower or h in lower for h in headers):
            start_idx = i + 1
            break

    end_idx = len(lines)
    for i in range(start_idx, len(lines)):
        lower = lines[i].lower()
        if any(h == lower or h in lower for h in stop_headers):
            end_idx = i
            break

    work_lines = lines[start_idx:end_idx] if start_idx < len(lines) else lines

    anchor_indices = [i for i, line in enumerate(work_lines) if _looks_like_role_anchor(line)]
    entries: List[WorkEntry] = []

    for pos, idx in enumerate(anchor_indices[: max_roles * 2]):
        line = work_lines[idx]
        next_idx = idx + 1
        next_line = work_lines[next_idx] if next_idx < len(work_lines) else ""
        title, company, dates = _parse_title_company_dates(line, next_line)

        block_end = anchor_indices[pos + 1] if pos + 1 < len(anchor_indices) else len(work_lines)
        block_lines = work_lines[idx + 1:block_end]
        action_verbs = ["managed", "led", "built", "developed", "designed", "implemented", "owned", "delivered", "improved", "reduced"]
        bullets: List[str] = []
        for candidate in block_lines:
            compact = re.sub(r"^[-•*\u2022\s]+", "", candidate).strip()
            if not compact:
                continue
            lower = compact.lower()
            if candidate.strip().startswith(("-", "•", "*")) or any(v in lower for v in action_verbs):
                bullets.append(compact[:140])
            if len(bullets) >= 3:
                break

        entries.append(WorkEntry(title=title, company=company, dates=dates, bullets=bullets))
        if len(entries) >= max_roles:
            break

    def sort_key(entry: WorkEntry) -> int:
        years = [int(y) for y in re.findall(r"\b(19\d{2}|20\d{2})\b", entry.dates)]
        if "present" in entry.dates.lower() or "current" in entry.dates.lower():
            return 9999
        return max(years) if years else -1

    dated_entries = [e for e in entries if e.dates]
    undated_entries = [e for e in entries if not e.dates]
    if dated_entries:
        dated_entries.sort(key=sort_key, reverse=True)
        entries = dated_entries + undated_entries

    return entries[:max_roles]


def format_work_history_markdown(entries: List[WorkEntry]) -> List[str]:
    if not entries:
        return ["Work experience not clearly parsed from extracted text."]

    rendered: List[str] = []
    for entry in entries:
        headline = f"**{entry.title}**"
        if entry.company:
            headline += f" — {entry.company}"
        if entry.dates:
            headline += f" ({entry.dates})"
        rendered.append(headline)

        if entry.bullets:
            for bullet in entry.bullets[:3]:
                rendered.append(f"• {bullet[:140]}")
        else:
            rendered.append("• Responsibilities/achievements not clearly parsed from nearby text.")

    return rendered


def summarize_resume(text: str) -> ResumeInsights:
    fields = infer_fields(text)
    years = estimate_years_experience(text)
    structured_points = build_structured_highlights(text)
    work_history = extract_work_history(text)
    education_lines = extract_education(text)
    skills = extract_skills(text)
    impact_signals = extract_impact(text)

    compact_summary = (
        "**Candidate Snapshot**\n"
        f"- **Experience:** {years}\n"
        f"- **Likely field(s):** {', '.join(fields)}\n"
        "- **Overall impression:** A results-oriented profile with practical, role-aligned accomplishments."
    )

    confidence_note = (
        "High confidence this is resume content."
        if looks_like_resume(text)
        else "Lower confidence this is resume content; extracted text may include non-resume material from other open windows."
    )

    return ResumeInsights(
        summary=compact_summary,
        highlights=structured_points,
        years_experience=years,
        fields=fields,
        confidence_note=confidence_note,
        work_history=work_history,
        education_lines=education_lines,
        skills=skills,
        impact_signals=impact_signals,
    )


def answer_question(
    text: str,
    question: str,
    api_key: str = "",
    model: str = "llama-3.3-70b-versatile",
    max_input_chars: int = 12000,
) -> str:
    if not text.strip():
        return "No resume text is available yet. Upload/capture a resume first."

    if not api_key.strip():
        return "A Groq API key is required to answer questions. Add it in the sidebar."

    prompt = (
        "You are a recruiter assistant with access to a candidate's resume. "
        "Answer the recruiter's question thoroughly and specifically using only information found in the resume. "
        "If the resume does not contain enough information to answer the question, say so clearly. "
        "Do not make up or infer details that are not present.\n\n"
        f"Resume:\n{text[:max_input_chars]}\n\n"
        f"Recruiter question: {question}"
    )

    try:
        return call_groq(api_key, model, prompt, max_tokens=1024)
    except Exception as exc:
        return f"Error calling Groq API: {exc}"


def main() -> None:
    st.set_page_config(page_title="Resume Q&A", page_icon="📄", layout="wide")
    st.title("📄 Resume Recruiter Q&A")
    st.write("Upload a resume and ask any question about the candidate. Groq AI will answer using the resume content.")

    with st.sidebar:
        st.header("Settings")
        source = st.radio(
            "Resume source",
            ["Upload file (PDF/Image/TXT)", "Capture current screen (open window scan)"],
        )
        st.divider()
        groq_api_key = st.text_input(
            "Groq API key",
            value=os.getenv("GROQ_API_KEY", ""),
            type="password",
            help="Get a free API key at console.groq.com",
        )
        groq_model = st.selectbox(
            "Groq model",
            options=[
                "llama-3.3-70b-versatile",
                "llama-3.1-8b-instant",
                "mixtral-8x7b-32768",
                "gemma2-9b-it",
            ],
            index=0,
            help="llama-3.3-70b-versatile gives the best results. Use llama-3.1-8b-instant if you hit rate limits.",
        )
        ai_input_chars = st.slider(
            "Resume input size (characters)",
            min_value=2000,
            max_value=20000,
            value=int(os.getenv("GROQ_INPUT_CHARS", "12000")),
            step=500,
            help="Higher values give more complete answers for long resumes.",
        )

    # Session state init
    for key, default in [("resume_text", ""), ("resume_key", ""), ("resume_summary", ""), ("qa_answer", ""), ("qa_question", "")]:
        if key not in st.session_state:
            st.session_state[key] = default

    warning = ""

    if source == "Upload file (PDF/Image/TXT)":
        upload = st.file_uploader("Upload resume", type=["pdf", "png", "jpg", "jpeg", "txt"])
        if upload:
            resume_key = f"{upload.name}_{upload.size}"
            if resume_key != st.session_state.resume_key:
                data = upload.read()
                name = upload.name.lower()
                if name.endswith(".pdf"):
                    extracted = extract_text_from_pdf(data)
                    if not extracted:
                        warning = "Could not parse PDF text. If the PDF is scanned, upload as image or ensure OCR support."
                elif name.endswith((".png", ".jpg", ".jpeg")):
                    extracted = extract_text_from_image(data)
                    if not extracted:
                        warning = "Could not OCR image. Verify pytesseract/tesseract installation."
                else:
                    extracted = data.decode("utf-8", errors="ignore")
                st.session_state.resume_text = extracted
                st.session_state.resume_key = resume_key
                st.session_state.resume_summary = ""
                st.session_state.qa_answer = ""
                st.session_state.qa_question = ""
    else:
        if st.button("Scan current screen"):
            captured, warning = capture_screen_text()
            if captured:
                st.session_state.resume_text = captured
                st.session_state.resume_key = "screen_capture"
                st.session_state.resume_summary = ""
                st.session_state.qa_answer = ""
                st.session_state.qa_question = ""

    if warning:
        st.warning(warning)

    resume_text = st.session_state.resume_text

    if resume_text:
        if source == "Capture current screen (open window scan)" and not looks_like_resume(resume_text):
            st.warning(
                "Screen scan did not strongly detect resume-like content. "
                "Bring the resume window to the front and scan again."
            )

        st.success("Resume loaded successfully.")

        st.divider()
        if not groq_api_key.strip():
            st.warning("Add your Groq API key in the sidebar to generate a summary.")
        else:
            if not st.session_state.resume_summary:
                with st.spinner("Generating summary..."):
                    try:
                        st.session_state.resume_summary = build_groq_recruiter_summary(
                            resume_text,
                            api_key=groq_api_key.strip(),
                            model=groq_model,
                            max_input_chars=ai_input_chars,
                        )
                    except Exception as exc:
                        st.warning(f"Summary generation failed: {exc}")
            if st.session_state.resume_summary:
                with st.expander("Recruiter Summary", expanded=True):
                    st.markdown(st.session_state.resume_summary)

        st.divider()
        st.subheader("Ask a question about this resume")

        with st.form("qa_form", clear_on_submit=False):
            typed_q = st.text_input("Type your question:", value=st.session_state.qa_question)
            submitted = st.form_submit_button("Ask")

        if submitted and typed_q.strip():
            st.session_state.qa_question = typed_q.strip()
            st.session_state.qa_answer = ""
            if not groq_api_key.strip():
                st.warning("Add your Groq API key in the sidebar to get answers.")
            else:
                with st.spinner("Groq is reading the resume..."):
                    st.session_state.qa_answer = answer_question(
                        resume_text,
                        st.session_state.qa_question,
                        api_key=groq_api_key.strip(),
                        model=groq_model,
                        max_input_chars=ai_input_chars,
                    )

        if st.session_state.qa_answer:
            st.markdown("**Answer:**")
            st.write(st.session_state.qa_answer)

        st.divider()
        with st.expander("View extracted resume text", expanded=False):
            st.text(resume_text[:3000] + ("..." if len(resume_text) > 3000 else ""))
    else:
        st.info("Upload a resume to get started.")


if __name__ == "__main__":
    main()