"""
reviewer.py -- runs inside a GitHub Action on every PR.

Same tool-calling pattern as agent-loop-101, applied to a different job:
here the tool isn't fetching external data, it's forcing STRUCTURED
output. Instead of asking the model to write a findings list in free text
(which you'd then have to fragile-regex-parse), we give it one tool --
`report_finding` -- and let it call that tool once per issue it finds.
Every call arrives as clean, already-parsed JSON: {file, line, severity,
title, description, recommendation}. This is one of the most common real
uses of tool calling that has nothing to do with "acting in the world."

Flow:
  1. Fetch the PR diff via the GitHub API.
  2. Load playbook.md (the review checklist) into the system prompt.
  3. Ask the local model to review the diff, with `report_finding` as the
     only available tool.
  4. Collect every report_finding call into a findings list.
  5. Post one summary comment on the PR.
  6. Exit non-zero if any finding is "high" or "critical" severity --
     this is what fails the CI check.
"""
import json
import os
import sys
from pathlib import Path

import ollama
import requests

MODEL = "llama3.2"
PLAYBOOK_PATH = Path(__file__).parent / "playbook.md"
FAIL_ON_SEVERITIES = {"high", "critical"}
MAX_DIFF_CHARS = 12000  # keep the prompt within a small local model's comfortable context

REPORT_FINDING_TOOL = {
    "type": "function",
    "function": {
        "name": "report_finding",
        "description": "Report one security issue found in the diff. Call this once per issue.",
        "parameters": {
            "type": "object",
            "properties": {
                "file": {"type": "string", "description": "File path where the issue was found"},
                "line": {"type": "string", "description": "Line number or approximate location, as shown in the diff"},
                "severity": {
                    "type": "string",
                    "enum": ["low", "medium", "high", "critical"],
                    "description": "How serious this issue is",
                },
                "title": {"type": "string", "description": "Short one-line summary of the issue"},
                "description": {"type": "string", "description": "What the problem is and why it matters"},
                "recommendation": {"type": "string", "description": "How to fix it"},
            },
            "required": ["file", "severity", "title", "description", "recommendation"],
        },
    },
}


def get_pr_diff(repo: str, pr_number: str, token: str) -> str:
    url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3.diff",
    }
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.text


def review_diff(diff: str) -> list[dict]:
    playbook = PLAYBOOK_PATH.read_text()

    if len(diff) > MAX_DIFF_CHARS:
        diff = diff[:MAX_DIFF_CHARS] + "\n\n[... diff truncated for length ...]"

    system_prompt = (
        "You are a security-focused code reviewer. Review the following "
        "pull request diff using the playbook below. Only flag real "
        "issues -- follow the playbook's guidance on what NOT to flag to "
        "avoid false positives.\n\n" + playbook
    )

    response = ollama.chat(
        model=MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Review this diff:\n\n{diff}"},
        ],
        tools=[REPORT_FINDING_TOOL],
    )

    findings = []
    for call in response.get("message", {}).get("tool_calls", []) or []:
        args = call["function"]["arguments"]
        # Ollama may return arguments as a dict already, or as a JSON string
        # depending on version -- handle both rather than assuming one.
        if isinstance(args, str):
            args = json.loads(args)
        findings.append(args)

    return findings


def format_comment(findings: list[dict]) -> str:
    if not findings:
        return "## 🪤 Tripwire\n\nNo security issues found in this diff."

    severity_emoji = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🔵"}
    order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    findings_sorted = sorted(findings, key=lambda f: order.get(f.get("severity", "low"), 3))

    lines = [f"## 🪤 Tripwire\n\nFound {len(findings)} issue(s):\n"]
    for f in findings_sorted:
        emoji = severity_emoji.get(f.get("severity", "low"), "⚪")
        location = f.get("file", "unknown file")
        if f.get("line"):
            location += f":{f['line']}"
        lines.append(f"### {emoji} {f.get('severity', '?').upper()} — {f.get('title', 'Untitled')}")
        lines.append(f"**Location:** `{location}`\n")
        lines.append(f"{f.get('description', '')}\n")
        lines.append(f"**Recommendation:** {f.get('recommendation', '')}\n")
        lines.append("---")

    lines.append(
        "\n*Automated review by Tripwire, running a local LLM (llama3.2 via Ollama) -- "
        "use judgment, this is a first pass, not a substitute for human review.*"
    )
    return "\n".join(lines)


def post_comment(repo: str, pr_number: str, token: str, body: str) -> None:
    url = f"https://api.github.com/repos/{repo}/issues/{pr_number}/comments"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    resp = requests.post(url, headers=headers, json={"body": body}, timeout=30)
    resp.raise_for_status()


def main():
    repo = os.environ["GITHUB_REPOSITORY"]
    token = os.environ["GITHUB_TOKEN"]

    event_path = os.environ["GITHUB_EVENT_PATH"]
    event = json.loads(Path(event_path).read_text())
    pr_number = str(event["pull_request"]["number"])

    print(f"Reviewing PR #{pr_number} in {repo}...")
    diff = get_pr_diff(repo, pr_number, token)
    print(f"Diff fetched: {len(diff)} chars")

    findings = review_diff(diff)
    print(f"Findings: {len(findings)}")
    for f in findings:
        print(f"  [{f.get('severity')}] {f.get('file')}: {f.get('title')}")

    comment = format_comment(findings)
    post_comment(repo, pr_number, token, comment)
    print("Comment posted.")

    serious = [f for f in findings if f.get("severity") in FAIL_ON_SEVERITIES]
    if serious:
        print(f"\n❌ Failing CI: {len(serious)} high/critical finding(s).")
        sys.exit(1)

    print("\n✅ No high/critical findings.")
    sys.exit(0)


if __name__ == "__main__":
    main()
