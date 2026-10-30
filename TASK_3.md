# TASK 3 (Codex): Job list, detail, my jobs, filters

Read CONTRACT.md first, including "Rules for every agent", "Failure rules" and the "Amendments" at the bottom. Build only what is listed here.
Tasks 1 and 2 already pass. Do not change their behavior.

## Files you may create or edit (create no other files)
- jobs/serializers.py : add one read serializer
- jobs/views.py : add the GET list, GET detail and my jobs views
- jobs/urls.py : add the routes
- jobs/filters.py : new file, hand-written filtering (do NOT use django-filter and do NOT install anything)
- config/urls.py : only if needed so the full path /api/my/jobs/ works
- DECISIONS.md : append one entry for this task
- Do NOT touch any test file. They are already written.

## Steps, in this order
1. Read serializer with exactly these fields (Amendment A5): id, title, description, location, job_type, work_model, experience_level, min_years_experience, salary_min, salary_max, is_open, created_at, company_name. Nothing about the owner.
2. GET /api/jobs/ : anyone, open jobs only, newest first, paginated.
3. GET /api/jobs/<id>/ : anyone. A closed job returns 404 not_found for everyone except the employer who owns it.
4. GET /api/my/jobs/ : employers only, their own jobs, open and closed, paginated. Candidates get 403, anonymous gets 401.
5. Filters on the list (CONTRACT "Job search filters" and Amendments A4 and A6). Invalid values return 400 validation_error. Search text must never be put into raw SQL.
6. Avoid one extra query per job for the company name (use select_related).
7. The existing POST and PATCH on jobs must keep working. Permissions are per method: GET is open to anyone, POST and PATCH stay as they are.
8. Append one entry to DECISIONS.md in the CONTRACT format. Use only reasons from CONTRACT.md or this file.

## Done when
`python manage.py test accounts jobs` passes with no test edited.

## Report back
1. Result of the test run.
2. Table: each CONTRACT line and amendment you implemented and the file it lives in.
3. Anything you were unsure about. Do not guess, list it.
