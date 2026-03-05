# Resume Summarizer App (Beginner Friendly Guide)

Hi! 👋

## ⚡ Quick Start (5 minutes)

If you just want to run the app fast, do this:

### Windows PowerShell
```powershell
cd "C:\Users\ValdonLaud\Resume-Summarizer-Project"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
streamlit run app.py
```

### macOS/Linux
```bash
cd /path/to/Resume-Summarizer-Project
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
streamlit run app.py
```


Optional (for AI-written recruiter summary with Gemini API):

1. Create a free API key in Google AI Studio: https://aistudio.google.com/app/apikey
2. In the app sidebar, paste your **Gemini API key**.
3. Use model `gemini-1.5-flash-latest` (default) for fast/low-cost responses.

Then open your browser to:

- `http://localhost:8501`

If that does not load, try:

- `http://127.0.0.1:8501`

---

This project is a simple web app that helps recruiters read resumes faster.

It can:

- Read resume text from an uploaded file.
- Try to read text from a screenshot/image using OCR.
- Create a short summary.
- Return a recruiter-style AI summary that is easy to scan quickly.
- Estimate years of experience.
- Guess the main work field (like Software, Data, Marketing, etc.).
- Answer follow-up questions about the resume.

---

## 1) What this app does (in plain words)

Imagine a recruiter has many resumes to review.
This app helps by doing the first quick read.

You upload a resume file (PDF, image, or TXT), and the app will:

1. Extract text from the file.

(Upload file is the default source in the app so recruiters can move quickly.)
2. Summarize the person’s background.
3. Return an easy-to-read recruiter-style summary.
4. Estimate years of experience.
5. Let you ask questions like:
   - “How many years of experience do they have?”
   - “What field is this candidate in?”
   - “Did they mention Python?”

---

## 2) Before you start

You need these installed on your computer:

- **Python 3.10+**
- **pip**
- Optional but recommended for image text reading:
  - **Tesseract OCR**

If you are brand new, install Python first:

- Go to: https://www.python.org/downloads/
- Download and install Python.
- During install, check **“Add Python to PATH”**.

---

## 3) Project files (what each file is for)

- `app.py` → Main app code.
- `requirements.txt` → List of Python libraries the app needs.
- `README.md` → This guide.

---

## 4) Step-by-step setup (copy/paste friendly)

### First: open terminal in the project folder

This error means you are in the wrong folder:

`could not open requirements file: [Errno 2] No such file or directory: 'requirements.txt'`

Run this first to move into the project folder.

**PowerShell**
```powershell
cd "C:\path\to\Resume-Summarizer-Project"
```

**macOS/Linux**
```bash
cd /path/to/Resume-Summarizer-Project
```

Now confirm the file exists:

**PowerShell**
```powershell
dir requirements.txt
```

**macOS/Linux**
```bash
ls requirements.txt
```

If you get "cannot find path ... requirements.txt", your project folder is incomplete (or you are in the wrong location).
Do this:

### If folder exists but file is missing

In PowerShell, list all files in the folder:

```powershell
dir
```

If you do not see `app.py`, `README.md`, and `requirements.txt`, you likely opened the wrong folder.

### Safest fix: clone the repo again into a fresh folder

```powershell
cd $HOME
git clone <your-github-repo-url> Resume-Summarizer-Project
cd .\Resume-Summarizer-Project
dir
```

You should now see:

- `app.py`
- `README.md`
- `requirements.txt`

Then continue:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
streamlit run app.py
```

### Then run setup commands

```bash
python -m venv .venv
# macOS/Linux
source .venv/bin/activate
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app.py
```

### What these commands mean

- `python -m venv .venv`
  - Creates a virtual environment.
- `source .venv/bin/activate` (macOS/Linux)
  - Activates that environment.
- `.\.venv\Scripts\Activate.ps1` (Windows PowerShell)
  - Activates the same environment in PowerShell.
- `pip install -r requirements.txt`
  - Installs project libraries.
- `streamlit run app.py`
  - Starts the web app.

When it starts, open the URL shown in terminal (usually `http://localhost:8501`).

---

### Windows PowerShell note

If you see this error:

`source: The term source is not recognized ...`

That is expected on Windows PowerShell. Use:

```powershell
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks script execution, run once:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Then activate again:

```powershell
.\.venv\Scripts\Activate.ps1
```

---



### If your folder path is correct but still empty

Sometimes people create a local folder manually with the right name, but it is not connected to GitHub code.
Check this:

```powershell
git remote -v
git status
```

- If `git remote -v` shows nothing, this is not a cloned repo.
- Clone from GitHub using the steps above.

## 5) If `pip install -r requirements.txt` still fails

Run this exact checklist in order.

1. Check where you are:

```powershell
pwd
```

2. List files in current folder:

```powershell
dir
```

3. If you do **not** see `requirements.txt`, move to the correct folder:

```powershell
cd "C:\path\to\Resume-Summarizer-Project"
```

4. Try install again:

```powershell
pip install -r requirements.txt
```

5. If pip itself is not found, use Python directly:

```powershell
python -m pip install -r requirements.txt
```

---

## 6) How to use the app

1. Open the app in your browser.
2. Choose resume source.
3. Upload resume.
4. Review summary, years, fields, and highlights.
5. Ask follow-up questions in Q&A.

---

## 7) Supported resume file types

- `.pdf`
- `.png`
- `.jpg` / `.jpeg`
- `.txt`

---

## 8) Important beginner notes

- Text PDFs work best.
- Scanned PDFs/images need OCR.
- OCR needs Tesseract installed locally.
- Screen capture can fail in headless/cloud environments.

---

## 9) Quick test

Create `sample_resume.txt`:

```txt
Jane Doe
Software Engineer
8 years of experience in backend development with Python and Java.
Led migration to microservices and improved latency by 30%.
```

Upload it and verify summary appears.

---

## 10) You’re done ✅

If app runs and one test upload works, you are set.

---

## 11) How to check if your files are on GitHub

If you do not see files on GitHub, it usually means changes are only local and were not pushed yet.

### A) Check local Git status

In your project folder run:

```bash
git status
git log --oneline -n 5
```

- `git status` shows if files are tracked/committed.
- `git log` shows your recent commits.

### B) Check which remote repo you are connected to

```bash
git remote -v
```

This shows the GitHub repository URL your local project is linked to.

### C) Push your branch to GitHub

```bash
git push -u origin <your-branch-name>
```

If you are on main (or another branch), you can check it with:

```bash
git branch --show-current
```

Then push that branch name.

### D) Verify on GitHub website

1. Open the repo URL from `git remote -v`.
2. Make sure you are viewing the **same branch** you pushed.
3. Refresh the page.
4. You should see `README.md`, `app.py`, and `requirements.txt` in the file list.

### E) If push says authentication failed

- Make sure you are logged in to GitHub in your terminal tooling.
- Use a Personal Access Token (PAT) if your setup requires it.
- Or use GitHub Desktop and push from there.

### F) Quick command set (copy/paste)

```bash
cd /path/to/Resume-Summarizer-Project
git status
git branch --show-current
git remote -v
git push -u origin $(git branch --show-current)
```

If the push succeeds, your files are on GitHub for that branch.

---

## 12) Why GitHub may show only one file (and how to fix it)

If GitHub shows only one file, the most common reason is:

- You are viewing a different branch (for example `main`) than the one where your new files were committed.
- Or your local commits were never pushed.

### Step 1: Check local commits and branch

```bash
git status
git branch --show-current
git log --oneline -n 5
```

### Step 2: Push the branch that contains your files

```bash
git push -u origin $(git branch --show-current)
```

### Step 3: Verify on GitHub

1. Open your repository in GitHub.
2. Click the branch dropdown (usually says `main`).
3. Select the branch from `git branch --show-current`.
4. You should now see `README.md`, `app.py`, and `requirements.txt`.

### Step 4: Get files into `main`

If files appear on your branch but not `main`, create and merge a Pull Request:

1. Click **Compare & pull request** on GitHub.
2. Create PR from your branch → `main`.
3. Merge the PR.
4. Refresh `main` and confirm all files are present.

### If push is rejected

Run:

```bash
git pull --rebase origin $(git branch --show-current)
git push -u origin $(git branch --show-current)
```

Then retry PR merge.


---

## 13) Super simple explanation: where your files are going

If you are brand new, think of it like this:

- Your computer folder = **Local copy**
- GitHub website = **Cloud copy**

When we create files, they are first in your **local copy**.
They do **NOT** appear on GitHub until you **push** them.

### 3-step beginner flow

1. Save files locally (already done when files exist in your folder).
2. Commit locally (a local save point).
3. Push to GitHub (upload to website).

### Exact commands (PowerShell or terminal)

Run these inside your project folder:

```bash
git status
git add .
git commit -m "Add resume summarizer files"
git push -u origin $(git branch --show-current)
```

After push succeeds:

1. Open your GitHub repo in browser.
2. Switch to the same branch you just pushed.
3. You should see `app.py`, `README.md`, and `requirements.txt`.

### If this still feels confusing, use GitHub Desktop (easiest)

1. Install **GitHub Desktop**.
2. Open your repository folder in GitHub Desktop.
3. You will see changed files listed.
4. Enter a commit message.
5. Click **Commit to <branch>**.
6. Click **Push origin**.
7. Refresh GitHub website.

### Quick check: did push work?

Run:

```bash
git log --oneline -n 3
git remote -v
git branch --show-current
```

If these commands show your new commit and a valid GitHub remote URL, your files are on that branch.

---

## 14) Fix for Pillow build error on Python 3.14

If you see:

- `Pillow 10.4.0 does not support Python 3.14`
- `Failed building wheel for pillow`

That is a Python-version compatibility issue.

### What we changed

This repo now uses:

- `pillow>=11.0.0`

so newer Python versions can install prebuilt wheels more reliably.

### What you should run now (PowerShell)

```powershell
cd "C:\Users\ValdonLaud\Resume-Summarizer-Project"
python --version
Remove-Item -Recurse -Force .venv
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If install still fails, easiest path is to use Python 3.12 or 3.13 for this project.

---

## 15) AI mode with Gemini API (cloud model, no local Ollama needed)

If your computer is struggling with local models, use Gemini API mode in this app.

### Quick setup

1. Create API key: https://aistudio.google.com/app/apikey
2. Run app:

```bash
streamlit run app.py
```

3. In sidebar:
- Turn on **Use Gemini API for recruiter summary**
- Paste **Gemini API key**
- Keep model as `gemini-1.5-flash-latest` (recommended)
- Optional: reduce **AI input size (characters)** for faster responses

### Common Gemini errors (plain English)

- **Missing API key**: add key in sidebar or set `GEMINI_API_KEY` env var.
- **401/403**: key is invalid or project permissions are not enabled.
- **404 (model not found)**: chosen model name is unavailable for your key/project. Try `gemini-1.5-flash-latest`.
- **429**: quota/rate limit reached; retry later or check Google AI Studio limits.
- **Timeout/network error**: temporary internet issue; retry.

### Optional: set environment variable instead of typing key each run

Windows PowerShell:

```powershell
$env:GEMINI_API_KEY="your_api_key_here"
streamlit run app.py
```

macOS/Linux:

```bash
export GEMINI_API_KEY="your_api_key_here"
streamlit run app.py
```
