import os
import subprocess
import re
import json
from pathlib import Path
from typing import List, Optional
from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv

from reviewer import PRReviewer
import main # Import existing functions from main.py

load_dotenv()

app = FastAPI(title="PR Reviewer API")

# Allow CORS for frontend development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

REVIEWS_DIR = Path("reviews")
REVIEWS_DIR.mkdir(exist_ok=True)
STATIC_DIR = Path("static")
STATIC_DIR.mkdir(exist_ok=True)

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/", response_class=HTMLResponse)
async def read_index():
    index_path = STATIC_DIR / "index.html"
    if not index_path.exists():
        # Create a basic index.html if it doesn't exist yet
        return "<html><body><h1>PR Reviewer</h1><p>Static index.html not found. Please wait...</p></body></html>"
    with open(index_path, "r") as f:
        return f.read()

class ReviewRequest(BaseModel):
    pr_url: str
    provider: str = "openai"
    model: Optional[str] = None
    base: str = "dev"

class ReviewResponse(BaseModel):
    status: str
    message: str
    review_id: Optional[str] = None
    content: Optional[str] = None

@app.get("/api/reviews")
async def list_reviews():
    reviews = []
    for f in REVIEWS_DIR.glob("*.md"):
        reviews.append({
            "id": f.stem,
            "filename": f.name,
            "created_at": f.stat().st_mtime
        })
    # Sort by mtime descending
    reviews.sort(key=lambda x: x["created_at"], reverse=True)
    return reviews

@app.get("/api/reviews/{review_id}")
async def get_review(review_id: str):
    file_path = REVIEWS_DIR / f"{review_id}.md"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Review not found")
    
    with open(file_path, "r") as f:
        content = f.read()
    
    return {"id": review_id, "content": content}

@app.post("/api/review", response_model=ReviewResponse)
async def create_review(req: ReviewRequest):
    try:
        pr_number, repo = main.extract_pr_info(req.pr_url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Determine model name
    provider = req.provider.lower()
    if provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
        model_name = req.model or "gpt-4o"
    elif provider == "gemini":
        api_key = os.getenv("GEMINI_API_KEY")
        model_name = req.model or "gemini-2.5-flash"
    else:
        raise HTTPException(status_code=400, detail="Unsupported provider")

    if not api_key:
        raise HTTPException(status_code=500, detail=f"{provider.upper()}_API_KEY not set")

    # Automate base branch detection
    base = req.base
    pr_details = main.get_pr_details(repo, pr_number)
    if pr_details and "base" in pr_details:
        base = pr_details["base"]["ref"]

    repo_path = main.setup_repo(repo)
    revision = f"pr-{pr_number}-review-temp"

    # Fetch needed data
    try:
        subprocess.run(["git", "fetch", "origin", f"pull/{pr_number}/head:{revision}"], check=True, capture_output=True, cwd=repo_path)
        subprocess.run(["git", "fetch", "origin", f"+refs/heads/{base}:refs/remotes/origin/{base}"], check=False, capture_output=True, cwd=repo_path)
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"Git fetch failed: {e.stderr.decode() if e.stderr else str(e)}")

    all_files = main.get_changed_files(repo_path, revision, base)
    filtered_files = main.filter_files(all_files)
    
    if not filtered_files:
        return ReviewResponse(status="success", message="No relevant changes found after filtering.")

    max_chars = 15000 if provider == "openai" else 100000 
    chunks = main.create_diff_chunks(repo_path, filtered_files, revision, base, max_chars=max_chars)
    
    if not chunks:
         return ReviewResponse(status="error", message="No diff content to analyze.")

    reviewer = PRReviewer(api_key=api_key, model_name=model_name, provider=provider)
    merger = main.ReviewMerger()
    
    for chunk in chunks:
        review_text = reviewer.get_review(chunk)
        merger.add_chunk_review(review_text)

    merged_review = merger.get_merged_review()

    # Save the review
    review_id = f"PR_{pr_number}_review"
    save_path = REVIEWS_DIR / f"{review_id}.md"
    with open(save_path, "w") as f:
        f.write(merged_review)
    
    # Cleanup
    subprocess.run(["git", "branch", "-D", revision], capture_output=True, cwd=repo_path)

    return ReviewResponse(
        status="success", 
        message="Review completed", 
        review_id=review_id,
        content=merged_review
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
