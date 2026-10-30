# TASK 6 (Copilot): Admin, README, DECISIONS.md, diagrams, seed command, API docs

Read CONTRACT.md first, including "Rules for every agent". Build only what is listed here.
Tasks 1 to 5 already pass. Do not change their behavior. Wisdom installs drf-spectacular himself and updates requirements.txt himself. Do not install anything.

## Files you may create or edit (create no other files)
- accounts/admin.py, jobs/admin.py, applications/admin.py
- applications/management/__init__.py, applications/management/commands/__init__.py, applications/management/commands/seed_demo.py
- config/settings.py : add "drf_spectacular" to INSTALLED_APPS and set it as the DEFAULT_SCHEMA_CLASS only
- config/urls.py : add /api/schema/ and /api/docs/ (Swagger page) only
- README.md, DECISIONS.md, .env.example
- Do NOT touch any test file.

## Steps, in this order
1. Admin: register User, Company, Job, Resume, Application, Notification with a useful list_display and search_fields. No custom pages.
2. seed_demo command: creates one employer, one candidate, one company and three open jobs with different filters. Running it twice must not create duplicates. It prints the usernames and the demo password. Use only the CONTRACT models and rules.
3. drf-spectacular: schema at /api/schema/ and the Swagger page at /api/docs/. Both return 200.
4. .env.example: the variable names from CONTRACT with placeholder values, no real secrets.
5. README.md: what the project is (one paragraph), stack, a 5 step setup (venv, install, Postgres and .env, migrate, run), how to run the tests, how to try it (seed_demo, then the Swagger page), the two Mermaid diagrams, and a link to DECISIONS.md. Diagram 1: an ER diagram of the six models and their relations. Diagram 2: the apply flow (JWT check, role check, job open check, resume ownership check, unique constraint, Application and Notification created in one transaction).
6. DECISIONS.md: keep the entries from earlier tasks. Add a section "Not covered by tests" (simultaneous requests, dropped connections, database down) and a section "If this grew 10x" containing exactly the line "WISDOM TO CONFIRM: <ideas to be filled in>". Do not invent claims, numbers or dates anywhere.
7. No em dashes in any text file. Plain wording.

## Done when
`python manage.py test accounts jobs applications` passes, and `python manage.py seed_demo` runs twice without error.

## Report back
1. Result of the test run and of the two seed runs.
2. Table: each step above and the file it lives in.
3. Anything you were unsure about. Do not guess, list it.
