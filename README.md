# Tripwire

A GitHub Action that reviews every PR for security smells (hardcoded
secrets, injection risks, weakened security controls) using a local LLM —
no API keys, no cost per PR. Comments on the PR with findings, and fails
the CI check if anything high/critical is found. Named for what it does:
catches something crossing a line before it goes any further.

This project is a direct, applied follow-up to two things covered
separately first:

**Tool calling**, applied to a use case beyond "call an external API":
here, the `report_finding` tool exists purely to force structured output.
Instead of asking the model to write a findings list in free text (which
you'd then have to fragile-regex-parse out of a paragraph), the model
calls `report_finding` once per issue, and each call arrives as clean,
already-typed JSON — `{file, line, severity, title, description,
recommendation}`. No parsing, no guessing whether the model's exact
wording is what you expected.

**Skills / packaged expertise**, applied without needing a specific
platform feature for it: `playbook.md` is a plain checklist of what to
look for and what NOT to flag (false-positive guidance), loaded into the
system prompt at review time. It's editable independently of the code —
tune the playbook without touching `reviewer.py` at all. This is the same
underlying idea as Anthropic's Agent Skills feature (packaged instructions
the model consults for a specific kind of task), implemented here as a
plain file + prompt injection, since Ollama doesn't have a native Skills
mechanism.

## Project layout

tripwire/
├── .github/workflows/security-review.yml
├── src/
│ ├── reviewer.py
│ └── playbook.md
├── test-samples/
│ ├── vulnerable_example.py
│ └── safe_example.py
├── requirements.txt
└── README.md

## Setup

1. Copy `.github/workflows/security-review.yml`, `src/reviewer.py`,
   `src/playbook.md`, and `requirements.txt` into your repo, preserving
   the `src/` folder.
2. That's it for a first pass — `GITHUB_TOKEN` is provided automatically
   by GitHub Actions, no secrets to configure.
3. Open a PR with something like a hardcoded API key or a string-built SQL
   query and watch it get flagged.

## Local testing (without waiting on GitHub Actions)

```bash
pip install -r requirements.txt
ollama pull llama3.2

export GITHUB_TOKEN="a real token with repo access"
export GITHUB_REPOSITORY="yourname/yourrepo"
export GITHUB_EVENT_PATH="./test_event.json"   # a fake PR event, see below
python src/reviewer.py
```

A minimal `test_event.json` for local testing:
```json
{"pull_request": {"number": 1}}
```
(Needs to point at a real open PR number in a real repo you have push
access to, since it fetches the real diff and posts a real comment.)

## Testing it on a real PR

`test-samples/` has two files built for exactly this:

- **`vulnerable_example.py`** — one clear example of each category from
  `playbook.md` (hardcoded secrets, SQL injection, command injection,
  `eval()`, insecure deserialization, disabled TLS verification, weak
  password hashing, debug mode left on). Nothing here is commented with
  "this is bad" — the point is to see whether Tripwire catches each one
  without being told.
- **`safe_example.py`** — patterns that *look* similar at a glance but are
  actually done correctly (env-loaded secrets, parameterized queries,
  bcrypt instead of MD5, an obvious placeholder value). This is the more
  important test: if Tripwire flags heavily here, that's a signal the
  playbook needs tuning to cut false positives, not that the model is
  working well.

**To test:**
1. Copy `test-samples/` into your repo alongside the other Tripwire files.
2. Open one PR adding `vulnerable_example.py` — expect several findings,
   including at least one `critical` (the hardcoded Stripe key), which
   should fail the CI check.
3. Open a separate PR adding only `safe_example.py` — expect a clean pass,
   or at most a low-severity note on the MD5 cache-key function (that one
   is a legitimate edge case, not a bug in the reviewer).
4. If reality doesn't match expectations on either PR, that's your signal
   for what to tune in `playbook.md` first — the false-positive/false-
   negative behavior on these two files is a fast feedback loop for
   playbook changes, much faster than waiting on a hunch about a real PR.

## Reading the code in the right order

1. **`playbook.md` first.** This is what actually determines review
   quality — read it and tune it before touching any Python. Notice it
   has both "what to flag" and "what NOT to flag" — the false-positive
   guidance matters as much as the detection rules, especially with a
   smaller local model that's more prone to over-flagging.
2. **`reviewer.py`'s `review_diff()` function.** This is the whole
   tool-calling part: one call to `ollama.chat()` with `report_finding` as
   the only available tool, then a loop over
   `response["message"]["tool_calls"]` to collect each one into a plain
   list of dicts.
3. **`format_comment()`** — pure string formatting, no LLM involved. Takes
   the structured findings and turns them into a readable Markdown
   comment, sorted by severity.
4. **`main()`** — wires it together: fetch diff → review → post comment →
   decide the exit code.

## Known limitations (be upfront about these)

- **`llama3.2` is a small model (1B/3B params).** It's good enough to
  demonstrate the pattern and will genuinely catch obvious issues
  (hardcoded keys, `eval()` on user input), but it will both miss subtler
  vulnerabilities and occasionally flag false positives more than a larger
  model would. Swapping `MODEL = "llama3.2"` to something like
  `qwen2.5-coder:7b` (code-specialized) or a hosted API model would
  meaningfully improve accuracy, at the cost of CI runtime (bigger model =
  slower pull + slower inference on a CPU-only runner) or API cost.
- **The diff gets truncated at `MAX_DIFF_CHARS`** (12,000 chars) to stay
  within a small model's comfortable context window. A very large PR will
  only get partially reviewed — worth surfacing this in the comment itself
  if you extend this (e.g. "diff was truncated, only the first N files
  were reviewed").
- **No inline PR review comments** — this posts one summary comment on the
  PR, not line-anchored review comments (GitHub's review API for that
  requires matching against the diff's line-position mapping, which is
  meaningfully more complex). A good next step if you want to extend this.
- **Every run pulls Ollama and the model fresh** — there's no caching of
  the Ollama install or the model weights between workflow runs, so every
  PR pays the full install+pull cost. Adding `actions/cache` keyed on the
  Ollama version and model name would speed this up substantially.
- **No handling of extremely small/trivial diffs** (e.g. a PR that only
  touches a `README.md`) — it'll still run the full review, wasting a
  cycle. Worth adding a cheap pre-check (file extension filtering) before
  spending the LLM call.

## Natural next steps

- Cache the Ollama binary + model weights between runs (`actions/cache`)
  to cut the per-PR time significantly.
- Add inline, line-anchored review comments instead of one summary
  comment.
- Add a second tool, `skip_file`, that lets the model explicitly say "this
  file is generated/vendored, not reviewing it" — teaches the model to use
  more than one tool per task, and you can log when it's invoked to sanity
  check the model isn't skipping things it shouldn't.
- Try swapping in `qwen2.5-coder` and comparing false-positive rates on a
  handful of real PRs — a good concrete way to build intuition for "when
  does model choice actually matter" in an agentic system.