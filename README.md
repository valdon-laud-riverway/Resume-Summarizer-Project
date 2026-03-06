# Resume Reviewer Widget

A floating Windows desktop tool for recruiters that captures resume text from multiple sources and generates a structured AI-powered summary using the Groq API. Designed to sit alongside your workflow — open a resume anywhere, click a button, get a recruiter brief instantly.

---

## Features

- **Structured AI Summary** — Candidate snapshot, recruiter assessment, career timeline, skills inventory, education, and impact highlights
- **Q&A** — Ask any follow-up question about the resume and get an answer grounded in the document
- **Multiple input methods** — works with PDFs on disk, browser tabs, desktop PDF viewers, clipboard, and screen capture
- **Always-on-top floating panel** — stays visible while you browse Indeed, LinkedIn, or any ATS
- **System tray** — minimizes to tray, never clutters your taskbar
- **Resizable window** — adjust to fit your screen layout

---

## Input Methods

| Button | Best For |
|---|---|
| 📁 File Picker | PDF or TXT file saved to disk |
| 🌐 Read Browser | Resume open in Chrome (Indeed, LinkedIn, Greenhouse, etc.) |
| 🖥️ Detect PDF App | Resume open in Acrobat, Foxit, SumatraPDF, or similar |
| 📋 Paste Clipboard | Text copied from any application (Ctrl+A, Ctrl+C) |
| 📷 Capture Screen | Resume visible on screen — use **➕ Add Page** for multi-page resumes |

---

## Requirements

### Python packages

```
pip install -r requirements.txt
```

### Tesseract OCR (required for screen capture only)

Download and run the Windows installer from:
https://github.com/UB-Mannheim/tesseract/wiki

Install to the default location:
```
C:\Program Files\Tesseract-OCR\
```

### Chrome remote debugging (required for browser reading only)

To use the **Read Browser** button, Chrome must be launched with remote debugging enabled. Create a shortcut with this target:

```
"C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222
```

Use this shortcut when you want the widget to read from your browser tab.

---

## Setup

1. Clone the repository
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Install Tesseract OCR (see above)
4. Run the widget:
   ```
   python resume_widget.py
   ```
5. On first launch, go to the **⚙️ Settings** tab and enter your Groq API key

### Running without a terminal window

Create a file called `Resume Reviewer.bat` in the same folder as `resume_widget.py`:

```bat
@echo off
pythonw resume_widget.py
```

Double-clicking this file launches the widget with no terminal window.

---

## Getting a Groq API Key

1. Go to https://console.groq.com
2. Sign up for a free account
3. Create an API key
4. Paste it into the **⚙️ Settings** tab in the widget

The free tier is generous for recruiter usage. If you hit rate limits, switch to `llama-3.1-8b-instant` in the model dropdown for faster responses.

---

## Configuration

Settings are saved to:
```
C:\Users\<YourName>\.resume_widget\config.ini
```

This includes your Groq API key, selected model, and Tesseract path. You only need to configure these once.

---

## Supported PDF Viewers (Auto-detect)

- Adobe Acrobat
- Foxit Reader
- SumatraPDF
- PDF-XChange

---

## Notes

- The widget minimizes to the system tray when you close it — double-click the tray icon to reopen, or right-click and select **Quit** to close completely
- The 📌 pin button in the title bar toggles always-on-top behavior
- Screen capture quality depends on screen resolution and whether the resume is a text-based or scanned PDF — the File Picker and Browser Read methods always give better results
- Multi-monitor setups are supported — you will be prompted to choose which screen to capture
- If multiple PDFs are open in a desktop viewer, you will be prompted to choose which one to load
