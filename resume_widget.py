"""
Resume Reviewer Widget
A floating desktop tool for Windows that captures resume text from multiple
sources, sends it to Groq, and displays a structured recruiter summary.

Requirements:
    pip install PyQt6 mss pytesseract groq selenium webdriver-manager psutil pypdf requests Pillow
    + Tesseract OCR installer from https://github.com/UB-Mannheim/tesseract/wiki
"""

import io
import json
import os
import re
import sys
import threading
import traceback
import configparser
from pathlib import Path

import requests

# ── PyQt6 ─────────────────────────────────────────────────────────────────────
from PyQt6.QtCore import (
    Qt, QThread, pyqtSignal, QSize, QTimer, QPoint
)
from PyQt6.QtGui import (
    QIcon, QFont, QColor, QPalette, QAction, QPixmap, QPainter
)
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QTextEdit, QLineEdit, QScrollArea, QFrame,
    QSystemTrayIcon, QMenu, QFileDialog, QSizeGrip, QSplitter,
    QComboBox, QMessageBox, QProgressBar, QTabWidget, QGroupBox,
    QStatusBar
)

# ── Optional deps (graceful fallback) ─────────────────────────────────────────

# Defined at module level so it's always accessible, even if pytesseract import fails
_TESS_CANDIDATES = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    r"C:\Users\Public\Tesseract-OCR\tesseract.exe",
    r"C:\Tesseract-OCR\tesseract.exe",
    r"C:\Tesseract\tesseract.exe",
]

try:
    import mss
    import mss.tools
    MSS_OK = True
except ImportError:
    MSS_OK = False

try:
    import pytesseract
    from PIL import Image

    # Hardcode the known path directly — no detection needed
    TESSERACT_PATH = "C:\\Program Files\\Tesseract-OCR\\tesseract.exe"
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH
    TESS_OK = True

except ImportError:
    TESS_OK = False
    TESSERACT_PATH = ""

try:
    from pypdf import PdfReader
    PYPDF_OK = True
except ImportError:
    PYPDF_OK = False

try:
    import psutil
    PSUTIL_OK = True
except ImportError:
    PSUTIL_OK = False

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from webdriver_manager.chrome import ChromeDriverManager
    SELENIUM_OK = True
except ImportError:
    SELENIUM_OK = False

# ── Config file path ───────────────────────────────────────────────────────────
CONFIG_PATH = Path.home() / ".resume_widget" / "config.ini"


# ═══════════════════════════════════════════════════════════════════════════════
#  CONFIG
# ═══════════════════════════════════════════════════════════════════════════════

def load_config() -> configparser.ConfigParser:
    cfg = configparser.ConfigParser()
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    if CONFIG_PATH.exists():
        cfg.read(CONFIG_PATH)
    if "groq" not in cfg:
        cfg["groq"] = {"api_key": "", "model": "llama-3.3-70b-versatile"}
    if "ocr" not in cfg:
        cfg["ocr"] = {"tesseract_path": ""}
    # Apply saved tesseract path immediately on load
    global TESS_OK, TESSERACT_PATH
    saved_tess = cfg.get("ocr", "tesseract_path", fallback="").strip()
    # Only apply saved path if it's non-empty AND different from the hardcoded default
    if saved_tess and saved_tess != TESSERACT_PATH:
        try:
            import pytesseract as _pt
            _pt.pytesseract.tesseract_cmd = saved_tess
            TESS_OK = True
            TESSERACT_PATH = saved_tess
        except Exception:
            pass
    return cfg


def save_config(cfg: configparser.ConfigParser) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        cfg.write(f)


# ═══════════════════════════════════════════════════════════════════════════════
#  GROQ API
# ═══════════════════════════════════════════════════════════════════════════════

GROQ_MODELS = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "mixtral-8x7b-32768",
    "gemma2-9b-it",
]


def call_groq(api_key: str, model: str, prompt: str, max_tokens: int = 2048) -> str:
    if not api_key.strip():
        raise RuntimeError("Groq API key is required.")
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.3,
    }
    resp = requests.post(url, json=body, headers=headers, timeout=(8, 90))
    resp.raise_for_status()
    data = resp.json()
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("Groq returned no choices.")
    return (choices[0].get("message") or {}).get("content", "").strip()


def build_summary_prompt(text: str, max_chars: int = 14000) -> str:
    return (
        "You are a senior recruiter preparing a hiring-manager brief. "
        "Analyze the resume and return ONLY a valid JSON object with exactly these keys:\n"
        "{\n"
        '  "snapshot": "3-4 sentence overview of seniority, domain, and likely role level",\n'
        '  "assessment": {"strengths": ["..."], "concerns": ["..."], "best_fit_roles": ["..."]},\n'
        '  "career": [{"title": "...", "company": "...", "dates": "...", "highlights": ["...", "..."]}],\n'
        '  "skills": {"languages": ["..."], "frameworks": ["..."], "platforms": ["..."], "tools": ["..."]},\n'
        '  "education": [{"degree": "...", "institution": "...", "year": "..."}],\n'
        '  "certifications": ["..."],\n'
        '  "impact": ["quantified achievement 1", "quantified achievement 2"]\n'
        "}\n\n"
        "Return ONLY the JSON. No markdown, no explanation, no code fences.\n\n"
        f"Resume:\n{text[:max_chars]}"
    )


def build_qa_prompt(resume_text: str, question: str, max_chars: int = 14000) -> str:
    return (
        "You are a recruiter assistant with access to a candidate's resume. "
        "Answer the recruiter's question thoroughly using only information from the resume. "
        "If the resume does not contain enough information, say so clearly.\n\n"
        f"Resume:\n{resume_text[:max_chars]}\n\n"
        f"Question: {question}"
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  TEXT EXTRACTION
# ═══════════════════════════════════════════════════════════════════════════════

def extract_pdf_bytes(data: bytes) -> str:
    """Extract all text from a PDF given its raw bytes."""
    if not PYPDF_OK:
        return ""
    try:
        reader = PdfReader(io.BytesIO(data))
        pages = [p.extract_text() or "" for p in reader.pages]
        return "\n".join(pages).strip()
    except Exception as e:
        return f"[PDF extraction error: {e}]"


def extract_pdf_file(path: str) -> str:
    """Extract all text from a PDF file path."""
    try:
        with open(path, "rb") as f:
            return extract_pdf_bytes(f.read())
    except Exception as e:
        return f"[File read error: {e}]"


def extract_from_clipboard() -> str:
    """Read plain text from the Windows clipboard."""
    clipboard = QApplication.clipboard()
    text = clipboard.text()
    return text.strip()


def get_monitor_list() -> list[dict]:
    """Return info about all connected monitors. Index 0 = combined, 1+ = individual."""
    if not MSS_OK:
        return []
    with mss.mss() as sct:
        # sct.monitors[0] is the combined virtual screen — skip it
        return list(sct.monitors[1:])


def extract_from_screen(monitor_index: int = 1) -> str:
    """
    Take a screenshot of the specified monitor (1-based, matches mss index)
    and OCR it. Defaults to monitor 1 (primary).
    """
    if not MSS_OK:
        return "[ERROR:mss not installed — run: pip install mss]"
    if not TESS_OK:
        return (
            "[ERROR:tesseract_not_found] Tesseract OCR could not be verified on this machine.\n\n"
            "Searched these locations:\n  " + "\n  ".join(_TESS_CANDIDATES) + "\n\n"
            "Your Tesseract is at:\n"
            "  C:\\Program Files\\Tesseract-OCR\\tesseract.exe\n\n"
            "Fix: Go to the Settings tab in the widget and paste that path into the Tesseract Path field, then click Save."
        )
    try:
        with mss.mss() as sct:
            monitor = sct.monitors[monitor_index]
            shot = sct.grab(monitor)
            img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
        return pytesseract.image_to_string(img).strip()
    except Exception as e:
        return f"[Screen capture error: {e}]"


def find_open_pdfs_in_desktop_apps() -> list[str]:
    """
    Inspect running processes and return a list of all PDF file paths
    currently open in any desktop PDF viewer. Deduplicates paths.
    """
    if not PSUTIL_OK:
        return []
    pdf_app_keywords = ["acrobat", "foxit", "sumatrapdf", "pdfxchange", "okular", "evince"]
    found: list[str] = []
    seen: set[str] = set()
    for proc in psutil.process_iter(["name", "open_files"]):
        try:
            proc_name = (proc.info.get("name") or "").lower()
            if not any(kw in proc_name for kw in pdf_app_keywords):
                continue
            open_files = proc.open_files() or []
            for f in open_files:
                if f.path.lower().endswith(".pdf") and f.path not in seen:
                    seen.add(f.path)
                    found.append(f.path)
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            continue
    return found


def find_open_pdf_in_desktop_apps() -> str:
    """Legacy single-result wrapper — returns first found PDF text."""
    paths = find_open_pdfs_in_desktop_apps()
    if not paths:
        return ""
    return extract_pdf_file(paths[0])


def extract_from_browser() -> str:
    """
    Connect to an existing Chrome session (or launch one) and extract
    all visible text from the current tab.
    """
    if not SELENIUM_OK:
        return "[selenium / webdriver-manager not installed]"
    try:
        options = webdriver.ChromeOptions()
        # Try to connect to an already-running Chrome with remote debugging
        # User must launch Chrome with: chrome.exe --remote-debugging-port=9222
        options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        # Extract all text from the page body
        body_text = driver.find_element(By.TAG_NAME, "body").text
        return body_text.strip()
    except Exception as e:
        return f"[Browser read error: {e}\n\nMake sure Chrome is open with remote debugging:\nchrome.exe --remote-debugging-port=9222]"


def looks_like_resume(text: str) -> bool:
    if not text or len(text) < 100:
        return False
    lower = text.lower()
    markers = ["experience", "education", "skills", "work history",
               "employment", "certifications", "projects"]
    hits = sum(m in lower for m in markers)
    year_hits = len(re.findall(r"\b(19\d{2}|20\d{2})\b", text))
    return hits >= 2 or (hits >= 1 and year_hits >= 2)


# ═══════════════════════════════════════════════════════════════════════════════
#  WORKER THREADS
# ═══════════════════════════════════════════════════════════════════════════════

class SummaryWorker(QThread):
    finished = pyqtSignal(str)   # emits JSON string
    error = pyqtSignal(str)

    def __init__(self, resume_text: str, api_key: str, model: str):
        super().__init__()
        self.resume_text = resume_text
        self.api_key = api_key
        self.model = model

    def run(self):
        try:
            prompt = build_summary_prompt(self.resume_text)
            result = call_groq(self.api_key, self.model, prompt, max_tokens=2048)
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class QAWorker(QThread):
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, resume_text: str, question: str, api_key: str, model: str):
        super().__init__()
        self.resume_text = resume_text
        self.question = question
        self.api_key = api_key
        self.model = model

    def run(self):
        try:
            prompt = build_qa_prompt(self.resume_text, self.question)
            result = call_groq(self.api_key, self.model, prompt, max_tokens=1024)
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class ExtractionWorker(QThread):
    finished = pyqtSignal(str)   # emits extracted text
    error = pyqtSignal(str)

    def __init__(self, method: str, file_path: str = "", monitor_index: int = 1):
        super().__init__()
        self.method = method
        self.file_path = file_path
        self.monitor_index = monitor_index

    def run(self):
        try:
            if self.method == "file":
                text = extract_pdf_file(self.file_path)
            elif self.method == "clipboard":
                text = extract_from_clipboard()
            elif self.method == "screen":
                text = extract_from_screen(self.monitor_index)
            elif self.method == "pdf_app":
                text = find_open_pdf_in_desktop_apps()
            elif self.method == "browser":
                text = extract_from_browser()
            else:
                text = ""
            self.finished.emit(text)
        except Exception as e:
            full_tb = traceback.format_exc()
            # Write full traceback to log file next to the script
            try:
                log_path = Path.home() / ".resume_widget" / "error.log"
                log_path.parent.mkdir(parents=True, exist_ok=True)
                with open(log_path, "a", encoding="utf-8") as lf:
                    import datetime
                    lf.write(f"\n{'='*60}\n")
                    lf.write(f"{datetime.datetime.now()}  method={self.method}\n")
                    lf.write(full_tb)
            except Exception:
                pass
            self.error.emit(full_tb)


# ═══════════════════════════════════════════════════════════════════════════════
#  SUMMARY CARD WIDGET
# ═══════════════════════════════════════════════════════════════════════════════

def make_section_label(title: str) -> QLabel:
    lbl = QLabel(title)
    lbl.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
    lbl.setStyleSheet("color: #2c3e50; margin-top: 8px; margin-bottom: 2px;")
    return lbl


def make_tag(text: str, bg: str = "#eef2ff", color: str = "#2c3e50") -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(
        f"background:{bg}; color:{color}; border-radius:10px; "
        f"padding:2px 8px; font-size:11px; margin:2px;"
    )
    lbl.setWordWrap(False)
    return lbl


class SummaryCardWidget(QWidget):
    """Renders the parsed JSON summary as structured cards."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout_ = QVBoxLayout(self)
        self.layout_.setContentsMargins(4, 4, 4, 4)
        self.layout_.setSpacing(4)

    def clear(self):
        while self.layout_.count():
            item = self.layout_.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def render(self, json_str: str):
        self.clear()
        clean = json_str.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        try:
            data = json.loads(clean)
        except Exception:
            lbl = QLabel(json_str)
            lbl.setWordWrap(True)
            self.layout_.addWidget(lbl)
            return

        # ── Snapshot ──────────────────────────────────────────────
        snapshot = (data.get("snapshot") or "").strip()
        if snapshot:
            box = QFrame()
            box.setStyleSheet(
                "background:#f0f4ff; border-left:4px solid #4a6fa5; "
                "border-radius:4px; padding:10px;"
            )
            bl = QVBoxLayout(box)
            bl.setContentsMargins(10, 8, 10, 8)
            lbl = QLabel(snapshot)
            lbl.setWordWrap(True)
            lbl.setFont(QFont("Segoe UI", 10))
            lbl.setStyleSheet("color:#2c3e50;")
            bl.addWidget(lbl)
            self.layout_.addWidget(box)

        # ── Recruiter Assessment ───────────────────────────────────
        assessment = data.get("assessment") or {}
        strengths = [s for s in (assessment.get("strengths") or []) if s and s != "N/A"]
        concerns = [c for c in (assessment.get("concerns") or []) if c and c != "N/A"]
        roles = [r for r in (assessment.get("best_fit_roles") or []) if r and r != "N/A"]

        if strengths or concerns or roles:
            self.layout_.addWidget(make_section_label("🎯  Recruiter Assessment"))
            if strengths:
                for s in strengths:
                    lbl = QLabel(f"✅  {s}")
                    lbl.setWordWrap(True)
                    lbl.setStyleSheet("font-size:11px; color:#2c3e50; padding-left:4px;")
                    self.layout_.addWidget(lbl)
            if concerns:
                clbl = QLabel("Concerns / Gaps")
                clbl.setStyleSheet("font-size:10px; font-weight:600; color:#888; margin-top:4px;")
                self.layout_.addWidget(clbl)
                for c in concerns:
                    lbl = QLabel(f"⚠️  {c}")
                    lbl.setWordWrap(True)
                    lbl.setStyleSheet("font-size:11px; color:#2c3e50; padding-left:4px;")
                    self.layout_.addWidget(lbl)
            if roles:
                rlbl = QLabel("Best-fit Roles")
                rlbl.setStyleSheet("font-size:10px; font-weight:600; color:#888; margin-top:4px;")
                self.layout_.addWidget(rlbl)
                row = QHBoxLayout()
                row.setContentsMargins(0, 0, 0, 0)
                row.setSpacing(4)
                for r in roles:
                    row.addWidget(make_tag(r, "#e8f4e8", "#1b5e20"))
                row.addStretch()
                self.layout_.addLayout(row)

        # ── Divider ───────────────────────────────────────────────
        self._add_divider()

        # ── Career Timeline ────────────────────────────────────────
        career = data.get("career") or []
        if career:
            self.layout_.addWidget(make_section_label("💼  Career Timeline"))
            for role in career:
                title = role.get("title") or ""
                company = role.get("company") or ""
                dates = role.get("dates") or ""
                highlights = role.get("highlights") or []

                header_parts = []
                if title:
                    header_parts.append(f"<b>{title}</b>")
                if company:
                    header_parts.append(company)
                header = " — ".join(header_parts)
                if dates:
                    header += f" <span style='color:#888;font-size:10px'>({dates})</span>"

                hlbl = QLabel(header)
                hlbl.setTextFormat(Qt.TextFormat.RichText)
                hlbl.setWordWrap(True)
                hlbl.setStyleSheet("font-size:11px; color:#2c3e50; margin-top:4px;")
                self.layout_.addWidget(hlbl)

                for h in highlights:
                    if h and h != "N/A":
                        blbl = QLabel(f"    • {h}")
                        blbl.setWordWrap(True)
                        blbl.setStyleSheet("font-size:10px; color:#555; padding-left:8px;")
                        self.layout_.addWidget(blbl)

        # ── Skills ─────────────────────────────────────────────────
        skills = data.get("skills") or {}
        skill_groups = [
            ("languages", "💻  Languages"),
            ("frameworks", "🔧  Frameworks"),
            ("platforms", "☁️  Platforms"),
            ("tools", "🔩  Tools"),
        ]
        has_skills = any(skills.get(k) for k, _ in skill_groups)
        if has_skills:
            self._add_divider()
            self.layout_.addWidget(make_section_label("🛠️  Skills Inventory"))
            for key, label in skill_groups:
                items = [i for i in (skills.get(key) or []) if i and i.strip() and i != "N/A"]
                if items:
                    klbl = QLabel(label)
                    klbl.setStyleSheet("font-size:10px; font-weight:600; color:#555; margin-top:3px;")
                    self.layout_.addWidget(klbl)
                    row = QHBoxLayout()
                    row.setContentsMargins(0, 0, 0, 0)
                    row.setSpacing(4)
                    for item in items:
                        row.addWidget(make_tag(item))
                    row.addStretch()
                    self.layout_.addLayout(row)

        # ── Education & Certifications ─────────────────────────────
        education = data.get("education") or []
        certs = [c for c in (data.get("certifications") or []) if c and c.strip() and c != "N/A"]
        if education or certs:
            self._add_divider()
            self.layout_.addWidget(make_section_label("🎓  Education & Certifications"))
            for edu in education:
                degree = edu.get("degree") or ""
                institution = edu.get("institution") or ""
                year = edu.get("year") or ""
                line = degree
                if institution:
                    line += f", {institution}"
                if year:
                    line += f" ({year})"
                if line.strip():
                    lbl = QLabel(f"📘  {line}")
                    lbl.setWordWrap(True)
                    lbl.setStyleSheet("font-size:11px; color:#2c3e50;")
                    self.layout_.addWidget(lbl)
            for cert in certs:
                lbl = QLabel(f"🏅  {cert}")
                lbl.setWordWrap(True)
                lbl.setStyleSheet("font-size:11px; color:#2c3e50;")
                self.layout_.addWidget(lbl)

        # ── Impact Highlights ──────────────────────────────────────
        impact = [i for i in (data.get("impact") or []) if i and i.strip() and i != "N/A"]
        if impact:
            self._add_divider()
            self.layout_.addWidget(make_section_label("📈  Impact Highlights"))
            for item in impact:
                lbl = QLabel(f"🔹  {item}")
                lbl.setWordWrap(True)
                lbl.setStyleSheet("font-size:11px; color:#2c3e50;")
                self.layout_.addWidget(lbl)

        self.layout_.addStretch()

    def _add_divider(self):
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color: #dde; margin: 4px 0;")
        self.layout_.addWidget(line)


# ═══════════════════════════════════════════════════════════════════════════════
#  SETTINGS PANEL
# ═══════════════════════════════════════════════════════════════════════════════

class SettingsPanel(QWidget):
    settings_saved = pyqtSignal()

    def __init__(self, cfg: configparser.ConfigParser, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        layout.addWidget(QLabel("⚙️  Settings", font=QFont("Segoe UI", 12, QFont.Weight.Bold)))

        # API Key
        layout.addWidget(QLabel("Groq API Key"))
        self.key_input = QLineEdit()
        self.key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_input.setPlaceholderText("gsk_...")
        self.key_input.setText(cfg.get("groq", "api_key", fallback=""))
        self.key_input.setStyleSheet(
            "border:1px solid #ccc; border-radius:4px; padding:6px; font-size:12px;"
        )
        layout.addWidget(self.key_input)

        # Model
        layout.addWidget(QLabel("Model"))
        self.model_combo = QComboBox()
        self.model_combo.addItems(GROQ_MODELS)
        saved_model = cfg.get("groq", "model", fallback="llama-3.3-70b-versatile")
        idx = self.model_combo.findText(saved_model)
        if idx >= 0:
            self.model_combo.setCurrentIndex(idx)
        self.model_combo.setStyleSheet(
            "border:1px solid #ccc; border-radius:4px; padding:4px; font-size:12px;"
        )
        layout.addWidget(self.model_combo)

        # Tesseract path
        tess_header = QHBoxLayout()
        tess_lbl = QLabel("Tesseract Path")
        tess_header.addWidget(tess_lbl)
        # Show green tick or red warning depending on detection status
        tess_status = QLabel("✅ Auto-detected" if TESS_OK else "❌ Not found")
        tess_status.setStyleSheet(
            "font-size:10px; color:#2e7d32;" if TESS_OK
            else "font-size:10px; color:#c62828;"
        )
        tess_header.addStretch()
        tess_header.addWidget(tess_status)
        layout.addLayout(tess_header)

        self.tess_input = QLineEdit()
        self.tess_input.setPlaceholderText(
            r"C:\Program Files\Tesseract-OCR\tesseract.exe"
        )
        saved_tess = cfg.get("ocr", "tesseract_path", fallback=TESSERACT_PATH or "")
        self.tess_input.setText(saved_tess)
        self.tess_input.setStyleSheet(
            "border:1px solid #ccc; border-radius:4px; padding:6px; font-size:11px;"
        )
        layout.addWidget(self.tess_input)

        tess_hint = QLabel(
            "Leave blank to use auto-detection. If screen capture fails, "
            "paste the full path to tesseract.exe here."
        )
        tess_hint.setWordWrap(True)
        tess_hint.setStyleSheet("font-size:10px; color:#888;")
        layout.addWidget(tess_hint)

        # Chrome tip
        tip = QLabel(
            "💡 For browser reading, launch Chrome with:\n"
            "chrome.exe --remote-debugging-port=9222"
        )
        tip.setWordWrap(True)
        tip.setStyleSheet(
            "background:#fffbe6; border:1px solid #ffe58f; border-radius:4px; "
            "padding:8px; font-size:10px; color:#7a6000;"
        )
        layout.addWidget(tip)

        # Save button
        save_btn = QPushButton("💾  Save Settings")
        save_btn.setStyleSheet(
            "background:#4a6fa5; color:white; border-radius:6px; "
            "padding:8px; font-size:12px; font-weight:600;"
        )
        save_btn.clicked.connect(self.save)
        layout.addWidget(save_btn)
        layout.addStretch()

    def save(self):
        self.cfg["groq"]["api_key"] = self.key_input.text().strip()
        self.cfg["groq"]["model"] = self.model_combo.currentText()
        if "ocr" not in self.cfg:
            self.cfg["ocr"] = {}
        tess_path = self.tess_input.text().strip()
        self.cfg["ocr"]["tesseract_path"] = tess_path
        # Apply immediately if a path was given
        if tess_path and TESS_OK is not None:
            try:
                import pytesseract as _pt
                _pt.pytesseract.tesseract_cmd = tess_path
            except Exception:
                pass
        save_config(self.cfg)
        self.settings_saved.emit()


# ═══════════════════════════════════════════════════════════════════════════════
#  PDF PICKER DIALOG
# ═══════════════════════════════════════════════════════════════════════════════

class MonitorPickerDialog(QWidget):
    """
    Dialog shown when multiple monitors are detected.
    User picks which screen to capture.
    """
    selected = pyqtSignal(int)   # emits the mss monitor index (1-based)

    def __init__(self, monitors: list[dict], parent=None):
        super().__init__(parent, Qt.WindowType.Dialog | Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowTitle("Select Screen")
        self.setMinimumWidth(440)
        self.setMinimumHeight(140 + len(monitors) * 80)
        self.setStyleSheet("background:#f7f8fa;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QLabel("Multiple monitors detected")
        title.setStyleSheet("font-size:14px; font-weight:700; color:#2c3e50;")
        layout.addWidget(title)

        subtitle = QLabel("Choose which screen to capture:")
        subtitle.setStyleSheet("font-size:11px; color:#666; margin-bottom:4px;")
        layout.addWidget(subtitle)

        for i, mon in enumerate(monitors):
            mss_index = i + 1   # mss monitors list is 1-based after skipping index 0
            width = mon.get("width", "?")
            height = mon.get("height", "?")
            left = mon.get("left", 0)
            top = mon.get("top", 0)

            # Determine label: primary is always index 1
            label = f"Monitor {mss_index}"
            if mss_index == 1:
                label += "  (Primary)"

            # Position hint so user can identify which physical screen
            if left < 0:
                position = "Left of primary"
            elif left > 0:
                position = "Right of primary"
            elif top < 0:
                position = "Above primary"
            elif top > 0:
                position = "Below primary"
            else:
                position = "Primary display"

            card = QFrame()
            card.setFixedHeight(68)
            card.setCursor(Qt.CursorShape.PointingHandCursor)
            card.setStyleSheet(
                "QFrame { background:white; border:1px solid #ddd; border-radius:8px; }"
                "QFrame:hover { background:#eef2ff; border:1px solid #4a6fa5; }"
            )
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(14, 10, 14, 10)
            card_layout.setSpacing(3)

            name_lbl = QLabel(label)
            name_lbl.setStyleSheet("font-size:12px; font-weight:700; color:#2c3e50;")
            card_layout.addWidget(name_lbl)

            detail_lbl = QLabel(f"{width}×{height}  —  {position}")
            detail_lbl.setStyleSheet("font-size:10px; color:#888;")
            card_layout.addWidget(detail_lbl)

            card.mousePressEvent = lambda event, idx=mss_index: self._choose(idx)
            layout.addWidget(card)

        layout.addSpacing(4)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedHeight(38)
        cancel_btn.setStyleSheet(
            "QPushButton { background:#e8edf3; color:#2c3e50; border-radius:6px; "
            "font-size:12px; font-weight:600; border:none; }"
            "QPushButton:hover { background:#d0d8e8; }"
        )
        cancel_btn.clicked.connect(self.close)
        layout.addWidget(cancel_btn)

    def _choose(self, index: int):
        self.selected.emit(index)
        self.close()


class PdfPickerDialog(QWidget):
    """
    Dialog shown when multiple PDFs are open in desktop viewers.
    Each PDF gets a clearly spaced card with filename and path.
    """
    selected = pyqtSignal(str)

    def __init__(self, paths: list[str], parent=None):
        super().__init__(parent, Qt.WindowType.Dialog | Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowTitle("Select Resume")
        self.setMinimumWidth(480)
        self.setMinimumHeight(160 + len(paths) * 80)
        self.setStyleSheet("background:#f7f8fa;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QLabel("Multiple PDFs detected")
        title.setStyleSheet("font-size:14px; font-weight:700; color:#2c3e50;")
        layout.addWidget(title)

        subtitle = QLabel("Choose which resume to load:")
        subtitle.setStyleSheet("font-size:11px; color:#666; margin-bottom:4px;")
        layout.addWidget(subtitle)

        for path in paths:
            filename = Path(path).name
            directory = str(Path(path).parent)

            # Card frame instead of QPushButton to avoid layout-in-button issues
            card = QFrame()
            card.setFixedHeight(64)
            card.setCursor(Qt.CursorShape.PointingHandCursor)
            card.setStyleSheet(
                "QFrame { background:white; border:1px solid #ddd; border-radius:8px; }"
                "QFrame:hover { background:#eef2ff; border:1px solid #4a6fa5; }"
            )
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(14, 10, 14, 10)
            card_layout.setSpacing(3)

            name_lbl = QLabel(filename)
            name_lbl.setStyleSheet("font-size:12px; font-weight:700; color:#2c3e50;")
            name_lbl.setWordWrap(False)
            card_layout.addWidget(name_lbl)

            dir_lbl = QLabel(directory)
            dir_lbl.setStyleSheet("font-size:10px; color:#888;")
            dir_lbl.setWordWrap(False)
            card_layout.addWidget(dir_lbl)

            # Make the whole card clickable via mousePressEvent
            card.mousePressEvent = lambda event, p=path: self._choose(p)
            layout.addWidget(card)

        layout.addSpacing(4)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedHeight(38)
        cancel_btn.setStyleSheet(
            "QPushButton { background:#e8edf3; color:#2c3e50; border-radius:6px; "
            "font-size:12px; font-weight:600; border:none; }"
            "QPushButton:hover { background:#d0d8e8; }"
        )
        cancel_btn.clicked.connect(self.close)
        layout.addWidget(cancel_btn)

    def _choose(self, path: str):
        self.selected.emit(path)
        self.close()


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN WINDOW
# ═══════════════════════════════════════════════════════════════════════════════

WINDOW_STYLE = """
QMainWindow, QWidget#central {
    background: #f7f8fa;
}
QScrollArea {
    border: none;
    background: transparent;
}
QScrollBar:vertical {
    width: 6px; background: #f0f0f0;
}
QScrollBar::handle:vertical {
    background: #ccc; border-radius: 3px;
}
QPushButton {
    border-radius: 6px;
    padding: 7px 10px;
    font-size: 11px;
    font-weight: 600;
}
QTextEdit, QLineEdit {
    border: 1px solid #ddd;
    border-radius: 4px;
    padding: 6px;
    font-size: 12px;
    background: white;
}
QTextEdit:focus, QLineEdit:focus {
    border: 1px solid #4a6fa5;
    outline: none;
}
"""

BTN_PRIMARY = (
    "background:#4a6fa5; color:white;"
)
BTN_SECONDARY = (
    "background:#e8edf3; color:#2c3e50;"
)
BTN_SUCCESS = (
    "background:#27ae60; color:white;"
)
BTN_DANGER = (
    "background:#e74c3c; color:white;"
)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.cfg = load_config()
        self.resume_text = ""
        self.resume_chunks: list[str] = []   # for multi-page screen capture
        self.summary_worker = None
        self.qa_worker = None
        self.extraction_worker = None

        self._build_ui()
        self._build_tray()
        self._apply_styles()

    # ── UI Build ───────────────────────────────────────────────────

    def _build_ui(self):
        self.setWindowTitle("Resume Reviewer")
        self.setMinimumSize(420, 600)
        self.resize(520, 800)
        self.setWindowFlags(
            Qt.WindowType.Window |
            Qt.WindowType.WindowStaysOnTopHint
        )

        central = QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Title bar
        title_bar = QWidget()
        title_bar.setStyleSheet("background:#2c3e50;")
        title_bar.setFixedHeight(44)
        tb_layout = QHBoxLayout(title_bar)
        tb_layout.setContentsMargins(12, 0, 8, 0)
        title_lbl = QLabel("📄  Resume Reviewer")
        title_lbl.setStyleSheet("color:white; font-size:13px; font-weight:700;")
        tb_layout.addWidget(title_lbl)
        tb_layout.addStretch()
        # Always-on-top toggle
        self.pin_btn = QPushButton("📌 Pinned")
        self.pin_btn.setToolTip("Click to unpin — window will no longer stay on top")
        self.pin_btn.setFixedHeight(26)
        self.pin_btn.setStyleSheet(
            "QPushButton { background:#3a8a5c; color:white; font-size:10px; font-weight:700; "
            "border:none; border-radius:4px; padding:0 8px; }"
            "QPushButton:hover { background:#2e7a4e; }"
        )
        self.pin_btn.setCheckable(True)
        self.pin_btn.setChecked(True)
        self.pin_btn.clicked.connect(self._toggle_pin)
        tb_layout.addWidget(self.pin_btn)
        root.addWidget(title_bar)

        # Tab widget
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(
            "QTabBar::tab { padding:6px 14px; font-size:11px; }"
            "QTabBar::tab:selected { font-weight:700; color:#4a6fa5; }"
        )
        root.addWidget(self.tabs)

        # ── Tab 1: Summarizer ──────────────────────────────────────
        summarizer_tab = QWidget()
        s_layout = QVBoxLayout(summarizer_tab)
        s_layout.setContentsMargins(10, 10, 10, 10)
        s_layout.setSpacing(8)

        # Input buttons
        input_group = QGroupBox("Load Resume")
        input_group.setStyleSheet(
            "QGroupBox { font-size:11px; font-weight:600; color:#555; "
            "border:1px solid #ddd; border-radius:6px; margin-top:6px; padding-top:6px; }"
            "QGroupBox::title { subcontrol-origin:margin; left:8px; }"
        )
        ig_layout = QVBoxLayout(input_group)
        ig_layout.setSpacing(5)

        # Row 1
        row1 = QHBoxLayout()
        self.btn_file = QPushButton("📁  File Picker")
        self.btn_file.setStyleSheet(BTN_SECONDARY)
        self.btn_file.setToolTip("Select a PDF file from disk")
        self.btn_file.clicked.connect(self._load_file)
        row1.addWidget(self.btn_file)

        self.btn_browser = QPushButton("🌐  Read Browser")
        self.btn_browser.setStyleSheet(BTN_SECONDARY)
        self.btn_browser.setToolTip(
            "Extract text from the active Chrome tab\n"
            "(Chrome must be running with --remote-debugging-port=9222)"
        )
        self.btn_browser.clicked.connect(self._load_browser)
        row1.addWidget(self.btn_browser)
        ig_layout.addLayout(row1)

        # Row 2
        row2 = QHBoxLayout()
        self.btn_pdf_app = QPushButton("🖥️  Detect PDF App")
        self.btn_pdf_app.setStyleSheet(BTN_SECONDARY)
        self.btn_pdf_app.setToolTip("Auto-detect a resume open in Acrobat, Foxit, SumatraPDF, etc.")
        self.btn_pdf_app.clicked.connect(self._load_pdf_app)
        row2.addWidget(self.btn_pdf_app)

        self.btn_clipboard = QPushButton("📋  Paste Clipboard")
        self.btn_clipboard.setStyleSheet(BTN_SECONDARY)
        self.btn_clipboard.setToolTip("Use text currently in your clipboard (Ctrl+A, Ctrl+C in your PDF viewer)")
        self.btn_clipboard.clicked.connect(self._load_clipboard)
        row2.addWidget(self.btn_clipboard)
        ig_layout.addLayout(row2)

        # Row 3 — screen capture with Add Page
        row3 = QHBoxLayout()
        self.btn_screen = QPushButton("📷  Capture Screen")
        self.btn_screen.setStyleSheet(BTN_SECONDARY)
        self.btn_screen.setToolTip("Screenshot the current screen and OCR it")
        self.btn_screen.clicked.connect(self._load_screen)
        row3.addWidget(self.btn_screen)

        self.btn_add_page = QPushButton("➕  Add Page")
        self.btn_add_page.setStyleSheet(BTN_SECONDARY)
        self.btn_add_page.setToolTip("Scroll to next page, then click to capture and append")
        self.btn_add_page.setEnabled(False)
        self.btn_add_page.clicked.connect(self._add_screen_page)
        row3.addWidget(self.btn_add_page)
        ig_layout.addLayout(row3)

        s_layout.addWidget(input_group)

        # Status bar (shows what was loaded)
        self.status_lbl = QLabel("No resume loaded.")
        self.status_lbl.setStyleSheet(
            "font-size:10px; color:#666; background:#f0f0f0; "
            "border-radius:4px; padding:4px 8px;"
        )
        self.status_lbl.setWordWrap(True)
        s_layout.addWidget(self.status_lbl)

        # Progress bar
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)  # indeterminate
        self.progress.setFixedHeight(4)
        self.progress.setStyleSheet(
            "QProgressBar { border:none; background:#eee; border-radius:2px; }"
            "QProgressBar::chunk { background:#4a6fa5; border-radius:2px; }"
        )
        self.progress.setVisible(False)
        s_layout.addWidget(self.progress)

        # Summarize button
        self.btn_summarize = QPushButton("✨  Summarize Resume")
        self.btn_summarize.setStyleSheet(
            f"{BTN_PRIMARY} font-size:13px; padding:10px;"
        )
        self.btn_summarize.setEnabled(False)
        self.btn_summarize.clicked.connect(self._run_summary)
        s_layout.addWidget(self.btn_summarize)

        # Clear button
        self.btn_clear = QPushButton("🗑️  Clear")
        self.btn_clear.setStyleSheet(f"{BTN_SECONDARY} font-size:11px;")
        self.btn_clear.clicked.connect(self._clear_all)
        s_layout.addWidget(self.btn_clear)

        # Summary scroll area
        self.summary_scroll = QScrollArea()
        self.summary_scroll.setWidgetResizable(True)
        self.summary_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.summary_cards = SummaryCardWidget()
        self.summary_scroll.setWidget(self.summary_cards)
        s_layout.addWidget(self.summary_scroll, stretch=1)

        self.tabs.addTab(summarizer_tab, "📋  Summary")

        # ── Tab 2: Q&A ─────────────────────────────────────────────
        qa_tab = QWidget()
        qa_layout = QVBoxLayout(qa_tab)
        qa_layout.setContentsMargins(10, 10, 10, 10)
        qa_layout.setSpacing(8)

        qa_layout.addWidget(QLabel(
            "Ask any question about the loaded resume.",
            styleSheet="font-size:11px; color:#666;"
        ))

        self.qa_input = QLineEdit()
        self.qa_input.setPlaceholderText("e.g. How many years of Python experience?")
        self.qa_input.returnPressed.connect(self._run_qa)
        qa_layout.addWidget(self.qa_input)

        self.btn_ask = QPushButton("💬  Ask")
        self.btn_ask.setStyleSheet(f"{BTN_PRIMARY} font-size:12px; padding:9px;")
        self.btn_ask.clicked.connect(self._run_qa)
        qa_layout.addWidget(self.btn_ask)

        self.qa_answer = QTextEdit()
        self.qa_answer.setReadOnly(True)
        self.qa_answer.setPlaceholderText("Answer will appear here...")
        self.qa_answer.setStyleSheet(
            "border:1px solid #ddd; border-radius:6px; "
            "background:#fafafa; font-size:12px; line-height:1.6;"
        )
        qa_layout.addWidget(self.qa_answer, stretch=1)

        self.tabs.addTab(qa_tab, "💬  Q&A")

        # ── Tab 3: Settings ────────────────────────────────────────
        self.settings_panel = SettingsPanel(self.cfg)
        self.settings_panel.settings_saved.connect(self._on_settings_saved)
        self.tabs.addTab(self.settings_panel, "⚙️  Settings")

        # Resize grip
        grip = QSizeGrip(self)
        grip.setFixedSize(16, 16)
        root.addWidget(grip, alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom)

    def _build_tray(self):
        """Build the system tray icon and menu."""
        # Create a simple icon programmatically
        pixmap = QPixmap(32, 32)
        pixmap.fill(QColor("#4a6fa5"))
        painter = QPainter(pixmap)
        painter.setPen(QColor("white"))
        painter.setFont(QFont("Segoe UI", 16))
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "📄")
        painter.end()

        self.tray = QSystemTrayIcon(QIcon(pixmap), self)
        self.tray.setToolTip("Resume Reviewer")

        menu = QMenu()
        show_action = QAction("Show / Hide", self)
        show_action.triggered.connect(self._toggle_visibility)
        menu.addAction(show_action)
        menu.addSeparator()
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(QApplication.quit)
        menu.addAction(quit_action)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    def _apply_styles(self):
        self.setStyleSheet(WINDOW_STYLE)

    # ── Tray / window helpers ──────────────────────────────────────

    def _toggle_visibility(self):
        if self.isVisible():
            self.hide()
        else:
            self.show()
            self.raise_()
            self.activateWindow()

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._toggle_visibility()

    def _toggle_pin(self):
        if self.pin_btn.isChecked():
            self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
            self.pin_btn.setText("📌 Pinned")
            self.pin_btn.setToolTip("Click to unpin — window will no longer stay on top")
            self.pin_btn.setStyleSheet(
                "QPushButton { background:#3a8a5c; color:white; font-size:10px; font-weight:700; "
                "border:none; border-radius:4px; padding:0 8px; }"
                "QPushButton:hover { background:#2e7a4e; }"
            )
        else:
            self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowStaysOnTopHint)
            self.pin_btn.setText("📌 Unpinned")
            self.pin_btn.setToolTip("Click to pin — keep window always on top")
            self.pin_btn.setStyleSheet(
                "QPushButton { background:#666; color:white; font-size:10px; font-weight:700; "
                "border:none; border-radius:4px; padding:0 8px; }"
                "QPushButton:hover { background:#555; }"
            )
        self.show()

    def closeEvent(self, event):
        # Minimise to tray instead of closing
        event.ignore()
        self.hide()
        self.tray.showMessage(
            "Resume Reviewer",
            "Running in system tray. Double-click to reopen.",
            QSystemTrayIcon.MessageIcon.Information,
            2000,
        )

    # ── Loading helpers ────────────────────────────────────────────

    def _set_busy(self, busy: bool, message: str = ""):
        self.progress.setVisible(busy)
        self.btn_summarize.setEnabled(not busy and bool(self.resume_text))
        self.btn_ask.setEnabled(not busy)
        self.btn_file.setEnabled(not busy)
        self.btn_browser.setEnabled(not busy)
        self.btn_pdf_app.setEnabled(not busy)
        self.btn_clipboard.setEnabled(not busy)
        self.btn_screen.setEnabled(not busy)
        if message:
            self.status_lbl.setText(message)

    def _on_text_loaded(self, text: str, source_label: str):
        self._set_busy(False)
        if not text.strip():
            self.status_lbl.setText(f"⚠️  No text extracted from {source_label}.")
            return
        # Catch known error tags so they never reach Groq
        if text.startswith("[ERROR:tesseract_not_found]"):
            # Show the detailed message in the summary area as plain text
            self.summary_cards.clear()
            from PyQt6.QtWidgets import QLabel as _QLabel
            err_lbl = _QLabel(text.replace("[ERROR:tesseract_not_found] ", ""))
            err_lbl.setWordWrap(True)
            err_lbl.setStyleSheet(
                "background:#fff3cd; border:1px solid #ffc107; border-radius:6px; "
                "padding:12px; font-size:11px; color:#856404;"
            )
            self.summary_cards.layout_.addWidget(err_lbl)
            self.status_lbl.setText("❌  Tesseract not found — see summary panel for instructions.")
            return
        if text.startswith("[ERROR:"):
            self.status_lbl.setText(f"❌  {text}")
            return
        if not looks_like_resume(text):
            self.status_lbl.setText(
                f"⚠️  Loaded from {source_label} but content doesn't look like a resume. "
                "You can still summarize."
            )
        else:
            words = len(text.split())
            self.status_lbl.setText(
                f"✅  Loaded from {source_label} — {words:,} words extracted."
            )
        self.resume_text = text
        self.btn_summarize.setEnabled(True)
        self.btn_add_page.setEnabled(False)

    def _on_extraction_error(self, error: str):
        self._set_busy(False)
        log_path = Path.home() / ".resume_widget" / "error.log"
        self.status_lbl.setText(f"❌  Extraction failed — see error details in summary panel.")
        # Show full traceback in the summary area so nothing is cut off
        self.summary_cards.clear()
        from PyQt6.QtWidgets import QLabel as _QLabel
        header = _QLabel("⚠️  An error occurred during extraction")
        header.setStyleSheet(
            "font-size:12px; font-weight:700; color:#721c24;"
        )
        self.summary_cards.layout_.addWidget(header)
        err_box = QTextEdit()
        err_box.setReadOnly(True)
        err_box.setPlainText(error)
        err_box.setStyleSheet(
            "background:#fff3cd; border:1px solid #ffc107; border-radius:6px; "
            "padding:8px; font-family:Consolas,monospace; font-size:10px; color:#856404;"
        )
        err_box.setMinimumHeight(180)
        self.summary_cards.layout_.addWidget(err_box)
        log_lbl = _QLabel(f"Full error also saved to:\n{log_path}")
        log_lbl.setWordWrap(True)
        log_lbl.setStyleSheet("font-size:10px; color:#555; margin-top:4px;")
        self.summary_cards.layout_.addWidget(log_lbl)
        self.summary_cards.layout_.addStretch()

    def _start_extraction(self, method: str, file_path: str = "", source_label: str = ""):
        self._set_busy(True, f"Loading from {source_label}...")
        self.extraction_worker = ExtractionWorker(method, file_path)
        self.extraction_worker.finished.connect(
            lambda text: self._on_text_loaded(text, source_label)
        )
        self.extraction_worker.error.connect(self._on_extraction_error)
        self.extraction_worker.start()

    # ── Input buttons ──────────────────────────────────────────────

    def _load_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Resume", "", "PDF Files (*.pdf);;Text Files (*.txt);;All Files (*)"
        )
        if not path:
            return
        if path.lower().endswith(".txt"):
            try:
                text = Path(path).read_text(encoding="utf-8", errors="ignore")
                self._on_text_loaded(text, f"file: {Path(path).name}")
            except Exception as e:
                self._on_extraction_error(str(e))
        else:
            self._start_extraction("file", file_path=path, source_label=f"file: {Path(path).name}")

    def _load_browser(self):
        self._start_extraction("browser", source_label="browser tab")

    def _load_pdf_app(self):
        """Find all PDFs open in desktop viewers; show picker if more than one."""
        if not PSUTIL_OK:
            self.status_lbl.setText("❌  psutil not installed — pip install psutil")
            return

        self._set_busy(True, "Scanning for open PDF applications...")
        # Run detection in a thread so UI doesn't freeze
        worker = ExtractionWorker("pdf_app")
        # We need the paths list, not extracted text — use psutil directly
        # via a short inline thread
        def _detect():
            paths = find_open_pdfs_in_desktop_apps()
            return paths

        # Use QTimer to keep this on the main thread after a brief check
        self._set_busy(False)
        paths = find_open_pdfs_in_desktop_apps()

        if not paths:
            self.status_lbl.setText(
                "⚠️  No PDF found in a running PDF viewer. "
                "Make sure Acrobat, Foxit, or SumatraPDF has a resume open."
            )
            return

        if len(paths) == 1:
            # Only one PDF open — load it directly
            self._set_busy(True, f"Reading: {Path(paths[0]).name}...")
            self.extraction_worker = ExtractionWorker("file", file_path=paths[0])
            self.extraction_worker.finished.connect(
                lambda text: self._on_text_loaded(text, Path(paths[0]).name)
            )
            self.extraction_worker.error.connect(self._on_extraction_error)
            self.extraction_worker.start()
        else:
            # Multiple PDFs open — show the picker dialog
            self.picker = PdfPickerDialog(paths, parent=self)
            self.picker.selected.connect(self._on_pdf_picked)
            self.picker.show()
            self.picker.raise_()

    def _on_pdf_picked(self, path: str):
        """Called when user selects a PDF from the picker dialog."""
        self._set_busy(True, f"Reading: {Path(path).name}...")
        self.extraction_worker = ExtractionWorker("file", file_path=path)
        self.extraction_worker.finished.connect(
            lambda text: self._on_text_loaded(text, Path(path).name)
        )
        self.extraction_worker.error.connect(self._on_extraction_error)
        self.extraction_worker.start()

    def _load_clipboard(self):
        # Clipboard is fast — do it synchronously
        text = extract_from_clipboard()
        self._on_text_loaded(text, "clipboard")

    def _load_screen(self):
        """Check monitor count — show picker if multiple, else capture immediately."""
        if not MSS_OK:
            self.status_lbl.setText("❌  mss not installed — pip install mss")
            return
        monitors = get_monitor_list()
        if len(monitors) > 1:
            self.monitor_picker = MonitorPickerDialog(monitors, parent=self)
            self.monitor_picker.selected.connect(self._on_monitor_selected_for_capture)
            self.monitor_picker.show()
            self.monitor_picker.raise_()
        else:
            self._capture_monitor(monitor_index=1, is_new=True)

    def _on_monitor_selected_for_capture(self, monitor_index: int):
        self._capture_monitor(monitor_index=monitor_index, is_new=True)

    def _capture_monitor(self, monitor_index: int, is_new: bool):
        if is_new:
            self.resume_chunks = []
            self._active_monitor_index = monitor_index
        self._set_busy(True, f"Capturing Monitor {monitor_index}...")
        self.extraction_worker = ExtractionWorker("screen", monitor_index=monitor_index)
        if is_new:
            self.extraction_worker.finished.connect(self._on_screen_captured)
        else:
            self.extraction_worker.finished.connect(self._on_extra_page_captured)
        self.extraction_worker.error.connect(self._on_extraction_error)
        self.extraction_worker.start()

    def _on_screen_captured(self, text: str):
        self.resume_chunks = [text] if text.strip() else []
        combined = "\n\n".join(self.resume_chunks)
        mon = getattr(self, "_active_monitor_index", 1)
        self._on_text_loaded(combined, f"Monitor {mon} capture (page 1)")
        self.btn_add_page.setEnabled(True)

    def _add_screen_page(self):
        mon = getattr(self, "_active_monitor_index", 1)
        self._capture_monitor(monitor_index=mon, is_new=False)

    def _on_extra_page_captured(self, text: str):
        if text.strip():
            self.resume_chunks.append(text)
        combined = "\n\n".join(self.resume_chunks)
        page_count = len(self.resume_chunks)
        mon = getattr(self, "_active_monitor_index", 1)
        self._on_text_loaded(combined, f"Monitor {mon} capture ({page_count} pages)")
        self.btn_add_page.setEnabled(True)

    # ── Summary ────────────────────────────────────────────────────

    def _run_summary(self):
        api_key = self.cfg.get("groq", "api_key", fallback="").strip()
        if not api_key:
            QMessageBox.warning(self, "API Key Missing",
                                "Please add your Groq API key in the Settings tab.")
            self.tabs.setCurrentIndex(2)
            return
        if not self.resume_text.strip():
            return

        self._set_busy(True, "Generating summary with Groq...")
        self.summary_cards.clear()
        model = self.cfg.get("groq", "model", fallback="llama-3.3-70b-versatile")
        self.summary_worker = SummaryWorker(self.resume_text, api_key, model)
        self.summary_worker.finished.connect(self._on_summary_done)
        self.summary_worker.error.connect(self._on_summary_error)
        self.summary_worker.start()

    def _on_summary_done(self, json_str: str):
        self._set_busy(False, self.status_lbl.text())
        self.summary_cards.render(json_str)
        self.tabs.setCurrentIndex(0)

    def _on_summary_error(self, error: str):
        self._set_busy(False)
        self.status_lbl.setText(f"❌  Summary failed: {error[:200]}")

    # ── Q&A ────────────────────────────────────────────────────────

    def _run_qa(self):
        question = self.qa_input.text().strip()
        if not question:
            return
        api_key = self.cfg.get("groq", "api_key", fallback="").strip()
        if not api_key:
            QMessageBox.warning(self, "API Key Missing",
                                "Please add your Groq API key in the Settings tab.")
            self.tabs.setCurrentIndex(2)
            return
        if not self.resume_text.strip():
            self.qa_answer.setPlainText("No resume loaded. Load a resume first.")
            return

        self._set_busy(True, "Asking Groq...")
        self.qa_answer.setPlainText("Thinking...")
        model = self.cfg.get("groq", "model", fallback="llama-3.3-70b-versatile")
        self.qa_worker = QAWorker(self.resume_text, question, api_key, model)
        self.qa_worker.finished.connect(self._on_qa_done)
        self.qa_worker.error.connect(self._on_qa_error)
        self.qa_worker.start()

    def _on_qa_done(self, answer: str):
        self._set_busy(False, self.status_lbl.text())
        self.qa_answer.setPlainText(answer)

    def _on_qa_error(self, error: str):
        self._set_busy(False)
        self.qa_answer.setPlainText(f"Error: {error}")

    # ── Clear ──────────────────────────────────────────────────────

    def _clear_all(self):
        self.resume_text = ""
        self.resume_chunks = []
        self.summary_cards.clear()
        self.qa_answer.clear()
        self.qa_input.clear()
        self.btn_summarize.setEnabled(False)
        self.btn_add_page.setEnabled(False)
        self.status_lbl.setText("Cleared. Load a new resume to begin.")

    # ── Settings saved ─────────────────────────────────────────────

    def _on_settings_saved(self):
        self.cfg = load_config()
        self.status_lbl.setText("✅  Settings saved.")


# ═══════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    # High-DPI support for Windows
    if hasattr(Qt, "HighDpiScaleFactorRoundingPolicy"):
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )

    app = QApplication(sys.argv)
    app.setApplicationName("Resume Reviewer")
    app.setQuitOnLastWindowClosed(False)   # keep alive in tray

    # Graceful exit if no system tray available
    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(None, "System Tray",
                             "No system tray detected on this system.")
        sys.exit(1)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
