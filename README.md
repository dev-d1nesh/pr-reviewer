# 🛡️ AI PR Reviewer

A lightweight Pull Request reviewer powered by OpenAI and Google Gemini. It analyzes code changes, identifies critical bugs, flags accidental file commits, and can save or post the resulting review back to GitHub.

## 🚀 Features

- **Multi-Provider Support**: Use either OpenAI (default) or Google Gemini models.
- **Accurate Line Mapping**: Automatically annotates diffs with line numbers for precise feedback.
- **Auto-Detection**: Automatically detects the base branch of a PR using the GitHub API unless you override it.
- **Fallback Logic**: Falls back to `TARGET_BRANCH`, then `main`, when base-branch detection is unavailable.
- **Filtering**: Automatically excludes irrelevant files (logs, locks, binary artifacts) from analysis.
- **Chunking**: Handles large PRs by intelligently chunking diffs to stay within model token limits.
- **API + UI**: Ships with a FastAPI backend that serves the static frontend from the same service.

## 🛠️ Setup

### 1. Prerequisites
- Python 3.10+
- `pip`
- Git

### 2. Installation
Clone the repository and install dependencies:
```bash
git clone <your-repo-url>
cd pr-reviewer
pip install -r requirements.txt
```

On Windows, the equivalent commands are usually:
```powershell
py -m pip install -r requirements.txt
```

### 3. Configuration
Create a `.env` file in the root directory:
```env
# AI API Keys
OPENAI_API_KEY=your_openai_key
GEMINI_API_KEY=your_gemini_key

# GitHub Configuration
GITHUB_TOKEN=your_github_personal_access_token
TARGET_BRANCH=main  # Optional fallback branch if detection fails

# SSH Configuration (optional)
SSH_HOST=git-config-host
```

## 📖 Usage

### Review a GitHub PR
You must pass the complete GitHub PR URL:
```bash
python main.py --pr https://github.com/owner/repo/pull/127
```

### Review a Local Branch
```bash
python main.py --branch feature/my-new-feature --base main
```

### Post a Review to GitHub
Once you've generated and reviewed the report locally, you can post it as a comment using the PR URL:
```bash
python main.py --pr https://github.com/owner/repo/pull/127 --post
```

### Advanced Options
- `--provider`: Choose between `openai` (default) or `gemini`.
- `--model`: Specify a specific model. If omitted, the app uses `gpt-4o` for OpenAI or `gemini-2.5-flash` for Gemini.
- `--base`: Override the detected PR base branch or the `TARGET_BRANCH`/`main` fallback.
- `--repo`: Manually specify the repo if needed, though it's automatically detected from the PR URL.

## 🌐 API and Docker

Run the API locally:
```bash
uvicorn api:app --reload
```

On Windows:
```powershell
py -m uvicorn api:app --reload
```

Then open `http://localhost:8000`.

Run the same service with Docker Compose:
```bash
docker compose up
```

This starts the FastAPI app on port `8000` and serves both the JSON API and the bundled static frontend.

## 🪟 Windows Notes

- The app now stores `reviews/`, `repos/`, and `static/` relative to the project directory instead of the shell's current working directory.
- Review filenames and cloned repo directory names are sanitized to avoid Windows-invalid characters such as `:`, `?`, `*`, and `\`.
- Git still needs to be installed and available on `PATH`.

## 📁 Project Structure

- `main.py`: Entry point, handles CLI arguments, Git operations, and orchestration.
- `api.py`: FastAPI application that exposes review endpoints and serves the frontend.
- `reviewer.py`: Contains the `PRReviewer` class for AI provider integration and prompting logic.
- `reviews/`: Stores generated markdown review reports.
- `repos/`: Temporary directory where repositories are cloned for analysis.
