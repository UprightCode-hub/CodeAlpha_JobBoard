# Handoff: Django Job Board review and implementation

## Original user requirements

The user requested implementation of six security, data-integrity, and maintainability items, one at a time. After each item, the requested workflow is to run `ruff check .`, `ruff format --check .`, `mypy` (if configured), and only the relevant existing test files; stage and locally commit with a conventional commit message (never push); then summarize and wait for approval before proceeding. **The user explicitly instructed not to write or modify test files**, because test authoring is separate.

1. **Environment configuration:** Add the missing `.env.example`; document required/optional settings; configure `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, database URL/settings, production fail-fast validation, production secure cookie/HTTPS defaults, and align README setup.
2. **Employer registration:** Public registration must not let callers choose employer role; public signups become candidates. Employer promotion is admin-only; document the trust model.
3. **Resume validation/storage:** Validate PDF structure and DOCX ZIP/OOXML contents, reject malformed files; document storage/access and production object-storage/antivirus considerations.
4. **Permission/error logic:** Consolidate role/ownership rules into reusable DRF permissions; replace hand-built errors with DRF exceptions using the shared handler.
5. **Company race:** Handle OneToOne duplicate-company insert races cleanly as 400 and validate against existing tests.
6. **OpenAPI duplication:** Use actual serializer classes for schemas; preserve multipart metadata where needed; run schema validation/tests.

## Work already performed

### Item 1 — implemented, but confirm on this machine

- Added `.env.example`.
- Added environment-driven settings in `config/settings.py`: parsed `ALLOWED_HOSTS`, either `DATABASE_URL` or individual `DB_*` database settings, production checks for long/non-obvious `SECRET_KEY` and non-empty hosts, and secure redirect/cookie/HSTS defaults when `DEBUG=False` with environment overrides.
- Updated README setup guidance.
- Added `requirements-dev.txt` and `pyproject.toml` with Ruff, mypy, django-stubs and DRF stubs plus Ruff/mypy plugin configuration.
- Removed the earlier placeholder `config/tests_settings.py` as directed; no test files should be added or modified.
- In the previous environment, the tool installation command did not complete, so Ruff/mypy checks for item 1 were not verified there. This machine's Git log now has commit `30ee543 style: pass ruff and mypy checks`; inspect it and the working tree to determine whether the main Codex agent has already verified/committed item 1.

### Item 2 — implementation present, uncommitted here

- `accounts/serializers.py`: `role` is read-only for registration, and `create()` forces `User.ROLE_CANDIDATE`.
- `README.md`: states public registration creates candidate users, submitted role is ignored, and only trusted administrators should promote users via Django Admin.
- No tests were modified. Existing `accounts/tests.py` has stale expectations that public employer registration works and that role is required. Do not alter it; report the mismatch to the user/main agent and rely on user-maintained tests or a manual check.
- In the earlier environment, `python manage.py test accounts.tests` could not connect to PostgreSQL at localhost:5432. The user confirms no PostgreSQL instance is available in that environment. Try the now-available PC's configured database or another safe way to run relevant existing tests, but do not author/modify test files. If tests cannot run, document that precisely.

## Current checkout state (observed while generating this handoff)

- Workspace: `C:\Users\ekwug\OneDrive\Desktop\CodeAlpha_JobBoard`.
- This workspace is now a Git checkout (unlike the prior environment).
- `git status --short` showed `M README.md` and `M accounts/serializers.py` when checked.
- Latest commit observed: `30ee543 style: pass ruff and mypy checks`.
- `config/tests_settings.py` is absent.
- Item 2 changes are uncommitted. Inspect latest commit and item 1 diffs first; avoid duplicating or overwriting main-agent changes.
- User wants itemized execution and an explicit pause for approval after each item. Only proceed with item 3 after item 2 is reviewed, verified as far as environment allows, committed locally, summarized, and approved.

## Suggested next actions for main Codex agent

1. Read this file and inspect `git status`, recent commits, and diffs.
2. Confirm item 1's commit/check state without rewriting it unnecessarily.
3. Review the item 2 serializer behavior and README wording; run Ruff formatting/lint and mypy per the user's workflow if available. Run only existing relevant account tests if a database is available. Do not change tests.
4. Commit item 2 locally with a conventional message (for example, `fix(auth): restrict public signup to candidates`) once checks are resolved or any test limitation is clearly reported.
5. Summarize item 2 and stop for the user's go-ahead before item 3.

## Prompt for main Codex agent

Please read `HANDOFF.md` in the JobBoard repository and continue from the recorded state. First inspect the Git status, latest commits, and diffs; item 1 may already have been committed by you. Continue with item 2 only: verify that public registration always creates candidates, keep employer promotion admin-only, and preserve the README trust-model documentation. Do not add, edit, or delete any test files. Run the requested formatter, linter, mypy, and only relevant existing account tests where available. The prior environment had no PostgreSQL and account tests could not connect; report any test limitation accurately. Stage and commit item 2 locally with a conventional commit message, do not push, then summarize and wait for my approval before beginning item 3. Do not overwrite existing work or assume the prior environment's checkout state matches this one.
