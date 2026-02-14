import argparse
import os
import sys
import requests
import subprocess
import re
from dotenv import load_dotenv
from reviewer import PRReviewer

import json
from pathlib import Path

load_dotenv()

REVIEWS_DIR = Path("reviews")
REVIEWS_DIR.mkdir(exist_ok=True)
REPOS_DIR = Path("repos")
REPOS_DIR.mkdir(exist_ok=True)

def extract_pr_info(pr_input: str) -> tuple[int, str]:
    """
    Extracts PR number and repo from a GitHub PR URL.
    Format: https://github.com/owner/repo/pull/123
    """
    url_pattern = r"github\.com/([^/]+/[^/]+)/pull/(\d+)"
    match = re.search(url_pattern, pr_input)
    if match:
        repo = match.group(1)
        pr_number = int(match.group(2))
        return pr_number, repo
    
    raise ValueError(f"Invalid PR input: {pr_input}. Must be a complete GitHub PR URL.")

def get_pr_details(repo: str, pr_number: int) -> dict:
    """Fetches PR details from GitHub API."""
    github_token = os.getenv("GITHUB_TOKEN")
    if not github_token:
        print("Warning: GITHUB_TOKEN not found in .env. Cannot fetch PR details for base branch detection.")
        return {}
        
    url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}"
    headers = {
        "Authorization": f"token {github_token}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Warning: Failed to fetch PR details: {response.status_code} - {response.text}")
            return {}
    except Exception as e:
        print(f"Warning: Error fetching PR details: {e}")
        return {}

def setup_repo(repo: str) -> Path:
    """Ensures a dedicated directory for the repo exists and is cloned."""
    repo_path = REPOS_DIR / repo.replace("/", "_")
    
    # Determine remote URL
    ssh_host = os.getenv("SSH_HOST")
    remote_url = f"git@{ssh_host}:{repo}.git" if ssh_host else f"https://github.com/{repo}.git"

    if not repo_path.exists():
        print(f"Cloning {repo} into {repo_path}...")
        try:
            subprocess.run(["git", "clone", remote_url, str(repo_path)], check=True)
        except subprocess.CalledProcessError as e:
            print(f"Error cloning repository: {e.stderr if e.stderr else e}")
            # Try to init and add remote as fallback if clone fails but dir was created
            if not repo_path.exists():
                repo_path.mkdir(parents=True, exist_ok=True)
            subprocess.run(["git", "init"], cwd=repo_path, check=True)
            subprocess.run(["git", "remote", "add", "origin", remote_url], cwd=repo_path, check=True)
    else:
        # Ensure remote is correct
        subprocess.run(["git", "remote", "set-url", "origin", remote_url], cwd=repo_path, check=False)
        
    return repo_path

def get_git_diff(repo_path: Path, revision: str, base: str = "dev") -> str:
    """Gets the diff for a local revision (branch, commit, etc) against base."""
    try:
        result = subprocess.run(
            ["git", "diff", f"origin/{base}...{revision}"],
            capture_output=True,
            text=True,
            check=True,
            cwd=repo_path
        )
        return result.stdout
    except subprocess.CalledProcessError as e:
        print(f"Error getting git diff: {e.stderr if e.stderr else e}")
        return ""

def get_github_pr_diff(repo_path: Path, pr_number: int, base: str = "dev") -> str:
    """Fetches the PR diff using local git by fetching the PR head."""
    temp_branch = f"pr-{pr_number}-review-temp"
    try:
        # 1. Fetch the PR head and base branch from origin
        print(f"Fetching PR #{pr_number} and {base} from origin...")
        subprocess.run(
            ["git", "fetch", "origin", f"pull/{pr_number}/head:{temp_branch}"],
            check=True,
            capture_output=True,
            text=True,
            cwd=repo_path
        )
        subprocess.run(
            ["git", "fetch", "origin", f"{base}:{base}"],
            check=False, # Don't fail if local branch doesn't exist or is ahead
            capture_output=True,
            text=True,
            cwd=repo_path
        )
        
        # 2. Get the diff against base
        print(f"Generating diff against origin/{base}...")
        result = subprocess.run(
            ["git", "diff", f"origin/{base}...{temp_branch}"],
            check=True,
            capture_output=True,
            text=True,
            cwd=repo_path
        )
        
        # 3. Clean up the temp branch
        subprocess.run(["git", "branch", "-D", temp_branch], capture_output=True, cwd=repo_path)
        
        return result.stdout
    except subprocess.CalledProcessError as e:
        print(f"Error fetching PR diff via git: {e.stderr if e.stderr else e}")
        # Cleanup if fetch failed but branch was somehow created
        subprocess.run(["git", "branch", "-D", temp_branch], capture_output=True, cwd=repo_path)
        return ""
    except Exception as e:
        print(f"Unexpected error: {e}")
        return ""

def get_changed_files(repo_path: Path, revision: str, base: str = "dev") -> list[str]:
    """Gets the list of changed files between base and revision."""
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", f"origin/{base}...{revision}"],
            capture_output=True,
            text=True,
            check=True,
            cwd=repo_path
        )
        files = result.stdout.strip().split("\n")
        return [f for f in files if f]
    except subprocess.CalledProcessError:
        return []

def filter_files(files: list[str]) -> list[str]:
    """Filters out irrelevant files (logs, lock files, etc.)."""
    exclude_patterns = [
        r".*\.log$",
        r".*output\.txt$",
        r".*\.lock$",
        r"\.DS_Store$",
        r".*\.pyc$",
        r"__pycache__/.*"
    ]
    
    filtered = []
    for f in files:
        if any(re.match(pattern, f) for pattern in exclude_patterns):
            continue
        filtered.append(f)
    return filtered

def annotate_diff(diff_text: str) -> str:
    """
    Annotates a unified diff with line numbers for the 'new' version of the file.
    Each line (except deletions and headers) is prefixed with its line number.
    """
    annotated_lines = []
    new_line_no = 0
    
    for line in diff_text.splitlines():
        if line.startswith('+++') or line.startswith('---'):
            annotated_lines.append(line)
        elif line.startswith('@@'):
            # Parse @@ -start,len +start,len @@
            match = re.search(r'\+(\d+)', line)
            if match:
                new_line_no = int(match.group(1))
            annotated_lines.append(line)
        elif line.startswith('+'):
            annotated_lines.append(f"{new_line_no:4d}: {line}")
            new_line_no += 1
        elif line.startswith('-'):
            annotated_lines.append(f"    : {line}") # No line number for deletions in new file
        elif line.startswith(' '):
            annotated_lines.append(f"{new_line_no:4d}: {line}")
            new_line_no += 1
        else:
            annotated_lines.append(line)
            
    return "\n".join(annotated_lines)

def get_file_diff(repo_path: Path, filename: str, revision: str, base: str = "dev") -> str:
    """Gets the diff for a single file."""
    try:
        result = subprocess.run(
            ["git", "diff", f"origin/{base}...{revision}", "--", filename],
            capture_output=True,
            text=True,
            check=True,
            cwd=repo_path
        )
        return annotate_diff(result.stdout)
    except subprocess.CalledProcessError:
        return ""

def create_diff_chunks(repo_path: Path, files: list[str], revision: str, base: str = "dev", max_chars: int = 15000) -> list[str]:
    """Groups file diffs into chunks that fit within character limits."""
    chunks = []
    current_chunk = ""
    
    for f in files:
        file_diff = get_file_diff(repo_path, f, revision, base)
        if not file_diff:
            continue
            
        # If a single file diff is larger than max_chars, we still include it but it'll be its own chunk
        # (or truncated if we wanted to be even safer, but let's try this first)
        if len(current_chunk) + len(file_diff) > max_chars and current_chunk:
            chunks.append(current_chunk)
            current_chunk = file_diff
        else:
            current_chunk += file_diff
            
    if current_chunk:
        chunks.append(current_chunk)
        
    return chunks

def post_github_comment(pr_number: int, comment: str, repo: str) -> bool:
    """Posts a comment to the GitHub PR using the Issues API."""
    github_token = os.getenv("GITHUB_TOKEN")
    if not github_token:
        print("Error: GITHUB_TOKEN not found in .env. Needed for posting comments.")
        return False
        
    url = f"https://api.github.com/repos/{repo}/issues/{pr_number}/comments"
    headers = {
        "Authorization": f"token {github_token}",
        "Accept": "application/vnd.github.v3+json"
    }
    payload = {"body": comment}
    
    try:
        response = requests.post(url, headers=headers, json=payload)
        if response.status_code == 201:
            print(f"Successfully posted comment to PR #{pr_number}")
            return True
        else:
            print(f"Failed to post comment: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"Error posting comment: {e}")
        return False

class ReviewMerger:
    def __init__(self):
        self.summary_rows = []
        self.detailed_findings = []
        self.no_issues_found = False

    def add_chunk_review(self, review_text: str):
        if "No critical issues found" in review_text:
            self.no_issues_found = True
            return

        # Extract table rows
        # Table rows look like: | 🔴 CRITICAL | `path/to/file` | L123 | Brief summary |
        lines = review_text.splitlines()
        in_table = False
        for line in lines:
            if "| Level | File |" in line:
                in_table = True
                continue
            if in_table and line.startswith('|') and ':---' not in line:
                if line.strip() and not line.startswith('| Level |'):
                    self.summary_rows.append(line.strip())
            elif in_table and not line.startswith('|'):
                in_table = False

        # Extract detailed findings
        if "### 🔍 Detailed Findings" in review_text:
            findings_part = review_text.split("### 🔍 Detailed Findings")[-1].split("---")[0].strip()
            if findings_part:
                # Avoid adding "If the diff is clean..." fluff if it leaked in
                findings_part = findings_part.split("If the diff is clean")[0].strip()
                self.detailed_findings.append(findings_part)

    def get_merged_review(self) -> str:
        if not self.summary_rows and self.no_issues_found:
            return "✅ **No critical issues found. Great job!**"
        
        if not self.summary_rows:
            return "✅ **No critical issues found in the analyzed chunks.**"

        report = "# 🛡️ PR Review Report\n\n"
        report += "| Level | File | Lines | Issue Summary |\n"
        report += "| :--- | :--- | :--- | :--- |\n"
        for row in self.summary_rows:
            report += f"{row}\n"
        
        report += "\n---\n\n### 🔍 Detailed Findings\n\n"
        report += "\n\n---\n\n".join(self.detailed_findings)
        
        report += "\n\n---\n\nThese issues are critical and need to be addressed to ensure data integrity."
        
        return report

def main():
    parser = argparse.ArgumentParser(description="Gemini-powered PR Reviewer")
    parser.add_argument("--pr", type=str, help="Complete GitHub PR URL (e.g., https://github.com/owner/repo/pull/123)")
    parser.add_argument("--branch", type=str, help="Local branch name to compare against base")
    parser.add_argument("--base", type=str, default="dev", help="Base branch to compare against (default: dev)")
    parser.add_argument("--repo", type=str, help="GitHub repository (owner/repo). This is automatically detected if --pr URL is provided.")
    parser.add_argument("--provider", type=str, default="openai", choices=["gemini", "openai"], help="AI provider to use (default: openai)")
    parser.add_argument("--model", type=str, default="gpt-4o", help="Model to use (default based on provider: gpt-4o or gemini-2.5-flash)")
    parser.add_argument("--post", action="store_true", help="Post the previously saved review as a comment on the GitHub PR")
    parser.add_argument("--file", type=str, help="Specify a custom file to post as a comment (overrides default naming)")
    
    args = parser.parse_args()
    
    # Extract PR info early to support URLs in both review and post flows
    if args.pr:
        try:
            pr_number, repo = extract_pr_info(args.pr)
            args.pr = pr_number
            args.repo = repo
        except ValueError as e:
            print(f"Error: {e}")
            sys.exit(1)
    elif not args.branch and not args.post:
        print("Error: Either --pr (URL) or --branch must be provided.")
        parser.print_help()
        sys.exit(1)

    # Determine provider and API key
    provider = args.provider.lower()
    if provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            print("Error: OPENAI_API_KEY environment variable not set.")
            sys.exit(1)
        # Default model for OpenAI if not explicitly changed from the Gemini default
        if args.model == "gemini-2.5-flash": # This might happen if user explicitly set gemini-2.5-flash but provider is openai
             model_name = "gpt-4o"
        else:
             model_name = args.model
    else:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            print("Error: GEMINI_API_KEY environment variable not set.")
            sys.exit(1)
        model_name = args.model

    if args.post:
        if not args.pr:
            print("Error: --post requires --pr to identify which review to post.")
            sys.exit(1)
        
        review_file = Path(args.file) if args.file else REVIEWS_DIR / f"PR_{args.pr}_review.md"
        
        if not review_file.exists():
            print(f"Error: Review file {review_file} not found. Generate it first by running without --post.")
            sys.exit(1)
            
        print(f"Reading review from {review_file}...")
        with open(review_file, "r") as f:
            review_content = f.read()
            
        print("\nPosting review as a comment to GitHub PR...")
        post_github_comment(args.pr, review_content, args.repo)
        return

    # Normal Review Flow
    diff = ""
    if args.pr:
        # Automate base branch detection
        print(f"Detecting base branch for PR #{args.pr} in {args.repo}...")
        pr_details = get_pr_details(args.repo, args.pr)
        if pr_details and "base" in pr_details:
            detected_base = pr_details["base"]["ref"]
            if args.base == "dev": # Only override if it's the default or not manually set to something else
                print(f"Detected base branch: {detected_base}")
                args.base = detected_base
            else:
                print(f"PR targets {detected_base}, but using manually specified base: {args.base}")
        else:
            # Fallback to TARGET_BRANCH from environment if detection failed
            env_target_branch = os.getenv("TARGET_BRANCH")
            if env_target_branch and args.base == "dev":
                print(f"Falling back to TARGET_BRANCH: {env_target_branch}")
                args.base = env_target_branch
            
        print(f"Setting up repository context for {args.repo}...")
        repo_path = setup_repo(args.repo)
        revision = f"pr-{args.pr}-review-temp"

        # Fetch everything needed
        print(f"Fetching PR #{args.pr} and {args.base} from origin...")
        subprocess.run(["git", "fetch", "origin", f"pull/{args.pr}/head:{revision}"], check=True, capture_output=True, cwd=repo_path)
        subprocess.run(["git", "fetch", "origin", f"{args.base}:{args.base}"], check=False, capture_output=True, cwd=repo_path)

    elif args.branch:
        print(f"Fetching local diff for branch '{args.branch}' against {args.base}...")
        repo_path = Path(".")
        revision = args.branch
    else:
        print("Error: Either --pr or --branch must be provided (unless using --post).")
        parser.print_help()
        sys.exit(1)

    # Get changed files and filter
    all_files = get_changed_files(repo_path, revision, args.base)
    filtered_files = filter_files(all_files)
    
    if not filtered_files:
         print("No relevant changes found after filtering.")
         sys.exit(0)

    print(f"Identified {len(filtered_files)} relevant files for review.")
    
    # Create chunks based on character limit (proxy for tokens)
    # Tier 1 TPM is 30k. 15k chars is ~4k tokens, safe enough.
    max_chars = 15000 if provider == "openai" else 100000 
    chunks = create_diff_chunks(repo_path, filtered_files, revision, args.base, max_chars=max_chars)
    
    if not chunks:
        print("No diff content to analyze.")
        sys.exit(1)

    print(f"Analyzing PR changes with {provider.capitalize()} model '{model_name}' (in {len(chunks)} chunks)...")
    
    reviewer = PRReviewer(api_key=api_key, model_name=model_name, provider=provider)
    merger = ReviewMerger()
    
    for i, chunk in enumerate(chunks):
        if len(chunks) > 1:
            print(f"  Processing chunk {i+1}/{len(chunks)}...")
        
        review = reviewer.get_review(chunk)
        merger.add_chunk_review(review)

    merged_review = merger.get_merged_review()

    print("\n" + "="*50)
    print("PR REVIEW RESULTS")
    print("="*50)
    print(merged_review)

    # Save the review
    save_path = REVIEWS_DIR / (f"PR_{args.pr}_review.md" if args.pr else f"branch_{args.branch.replace('/', '_')}_review.md")
    print(f"\nSaving review to {save_path}...")
    with open(save_path, "w") as f:
        f.write(merged_review)
    
    # Cleanup temp branch if it was a PR
    if args.pr:
        subprocess.run(["git", "branch", "-D", revision], capture_output=True, cwd=repo_path)

if __name__ == "__main__":
    main()
