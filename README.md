# 🛡️ AI PR Reviewer

A powerful, automated Pull Request reviewer powered by Google Gemini and OpenAI. This tool analyzes code changes, identifies critical bugs, flags accidental file commits, and provides human-like constructive feedback directly on GitHub.

## 🚀 Features

- **Multi-Provider Support**: Use either Google Gemini (default) or OpenAI models.
- **Accurate Line Mapping**: Automatically annotates diffs with line numbers for precise feedback.
- **Auto-Detection**: Automatically detects the base branch of a PR using the GitHub API.
- **Fallback Logic**: Seamlessly falls back to a target branch from environment variables if GitHub API access is restricted.
- **Filtering**: Automatically excludes irrelevant files (logs, locks, binary artifacts) from analysis.
- **Chunking**: Handles large PRs by intelligently chunking diffs to stay within model token limits.

## 🛠️ Setup

### 1. Prerequisites
- Python 3.10+
- `pip`

### 2. Installation
Clone the repository and install dependencies:
```bash
git clone <your-repo-url>
cd pr-reviewer
pip install -r requirements.txt
```

### 3. Configuration
Create a `.env` file in the root directory:
```env
# AI API Keys
OPENAI_API_KEY=your_openai_key
GEMINI_API_KEY=your_gemini_key

# GitHub Configuration
GITHUB_TOKEN=your_github_personal_access_token
TARGET_BRANCH=develop  # Fallback branch if detection fails

# SSH Configuration (optional)
SSH_HOST=git-tvs
```

## 📖 Usage

### Review a GitHub PR
You must pass the complete GitHub PR URL:
```bash
python main.py --pr https://github.com/owner/repo/pull/127
```

### Review a Local Branch
```bash
python main.py --branch feature/my-new-feature --base develop
```

### Post a Review to GitHub
Once you've generated and reviewed the report locally, you can post it as a comment using the PR URL:
```bash
python main.py --pr https://github.com/owner/repo/pull/127 --post
```

### Advanced Options
- `--provider`: Choose between `openai` (default) or `gemini`.
- `--model`: Specify a specific model (e.g., `gpt-4o`, `gemini-2.0-flash`).
- `--repo`: Manually specify the repo if needed, though it's automatically detected from the PR URL.

## 📁 Project Structure

- `main.py`: Entry point, handles CLI arguments, Git operations, and orchestration.
- `reviewer.py`: Contains the `PRReviewer` class for AI provider integration and prompting logic.
- `reviews/`: Stores generated markdown review reports.
- `repos/`: Temporary directory where repositories are cloned for analysis.
```
