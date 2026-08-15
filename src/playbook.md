# Tripwire's Security Review Playbook

This is the checklist the review agent consults on every PR. It's kept as
a separate file (not hardcoded in the prompt) so it can be tuned without
touching `reviewer.py` -- the same idea as an Anthropic "Skill": packaged,
editable expertise the model is handed at the start of a task, rather than
capability baked into code.

## What to flag

**Hardcoded secrets**
- API keys, tokens, passwords, private keys embedded directly in code
  (not read from environment variables or a secrets manager)
- Connection strings containing credentials
- AWS/GCP/Azure access keys matching common patterns (e.g. `AKIA...`)

**Injection risks**
- SQL queries built with string concatenation/formatting instead of
  parameterized queries (`f"SELECT * FROM users WHERE id={user_input}"`)
- Shell commands built from unsanitized input, especially
  `subprocess` calls with `shell=True`, or `os.system(...)` with any
  variable interpolated into the command string
- Use of `eval()` or `exec()` on anything that could contain user input

**Insecure deserialization**
- `pickle.loads()` on data from an untrusted source (network, file upload,
  user input)
- `yaml.load()` without `Loader=yaml.SafeLoader` (or `yaml.safe_load`)

**Weakened security controls**
- TLS/SSL certificate verification disabled (`verify=False`,
  `ssl._create_unverified_context()`)
- Weak or outdated hashing used for passwords (MD5, SHA1 instead of
  bcrypt/scrypt/argon2)
- Overly permissive CORS (`Access-Control-Allow-Origin: *` alongside
  credentialed requests)
- Debug mode left enabled in what looks like production config
  (`DEBUG = True`, `app.run(debug=True)`)

**Path / file handling**
- File paths built from user input without validation (path traversal
  risk, e.g. `open(base_dir + user_supplied_filename)`)
- Insecure temp file creation (predictable names, world-writable
  permissions)

## What NOT to flag (avoid false positives)

- Placeholder/example values that are obviously not real secrets:
  `"changeme"`, `"your-api-key-here"`, `"xxx"`, values in files named
  `.env.example`, `config.sample.*`, or similar
- Secrets correctly loaded from environment variables or a secrets
  manager (`os.environ["API_KEY"]`, `os.getenv(...)`) -- this is the
  correct pattern, not a finding
- Test fixtures using obviously fake credentials for testing purposes
  (e.g. in files under a `tests/` or `fixtures/` directory using values
  like `"test-token-123"`)
- Commented-out code -- note it only if it looks like an accidentally
  left-in real credential, not as a style issue

## Severity guide

- **critical** -- a real secret is exposed, or there's a clear, directly
  exploitable injection vulnerability in a code path reachable by
  untrusted input
- **high** -- a security control is disabled or weakened in a way that
  matters in production (cert verification off, weak hashing for
  passwords, debug mode in what looks like prod config)
- **medium** -- a risky pattern that isn't immediately exploitable as
  written but is bad practice and could become a real issue (e.g.
  string-built SQL query where the input happens to be internally
  controlled today, but the pattern itself is fragile)
- **low** -- worth mentioning but minor (e.g. slightly weak but
  non-password-related hashing, missing input validation on a
  low-sensitivity field)

## How to report

For every issue found, call the `report_finding` tool once per issue --
don't bundle multiple issues into one call. If you find nothing, don't
call the tool at all; just say so in your final response.
