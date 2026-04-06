from google import genai
from openai import OpenAI


AI_REQUEST_TIMEOUT_SECONDS = 60

class PRReviewer:
    def __init__(self, api_key: str, model_name: str, provider: str = "openai"):
        self.provider = provider.lower()
        self.model_name = model_name
        
        if self.provider == "gemini":
            self.client = genai.Client(api_key=api_key)
        elif self.provider == "openai":
            self.client = OpenAI(api_key=api_key, timeout=AI_REQUEST_TIMEOUT_SECONDS)
        else:
            raise ValueError(f"Unsupported provider: {provider}")

    def get_review(self, diff: str) -> str:
        prompt = self._build_prompt(diff)
        
        if self.provider == "gemini":
            response = self.client.models.generate_content(model=self.model_name, contents=prompt)
            return response.text
        elif self.provider == "openai":
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}]
            )
            return response.choices[0].message.content
        return ""

    def _build_prompt(self, diff: str) -> str:
        return f"""
You are an expert software engineer reviewing a Pull Request.
Your primary objective is to identify CRITICAL DEFECTS, BUGS, and ACCIDENTAL FILE COMMITS.

STRICT RULES:
1. **Accidental Files**: Explicitly flag any files that look like logs, temporary data, binary artifacts, or local environment files (e.g., `*.log`, `*output.txt`, `tmp*`, secrets, `.DS_Store`).
2. **Real Defects**: Identify logic bugs, race conditions, or incorrect infrastructure usage (e.g., mocktail state errors).
3. **Line Numbers**: The PR DIFF DATA below is annotated with line numbers (e.g., ` 123: + added line`). You MUST use these explicit line numbers for your report.
4. **No Fluff**: Do NOT provide praise, do NOT comment on minor style issues, and do NOT provide "verify" reminders for correct code.
5. **Format**: Use a structured Markdown table for the summary of issues, followed by detailed sections for each issue.

### PROPOSED FORMAT:
# 🛡️ PR Review Report

| Level | File | Lines | Issue Summary |
| :--- | :--- | :--- | :--- |
| 🔴 CRITICAL | `path/to/file` | L123 | Brief summary of the bug |
| 🟠 ACCIDENTAL | `path/to/file` | All | Script/Log file committed |

---

### 🔍 Detailed Findings

#### 🔴 [CRITICAL] `path/to/file` (L123-L125)
- **Issue**: Precise description of the defect.
- **Recommendation**: Exact fix or action to take.
```dart
// Code snippet showing the fix if applicable
```

---

If the diff is clean and has no issues, reply with "✅ **No critical issues found. Great job!**"

PR DIFF DATA (Annotated with line numbers):
{diff}

REVIEW:
"""
