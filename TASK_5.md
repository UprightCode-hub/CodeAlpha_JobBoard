# TASK 5 (Codex): Resume upload, apply, application list and detail, status update, notifications

Read CONTRACT.md first, including "Rules for every agent", "Endpoints", "Failure rules" and all Amendments (A1 to A13). Build only what is listed here.
Tasks 1 to 4 already pass. Do not change their behavior.

## Files you may create or edit (create no other files)
- applications/serializers.py, applications/views.py, applications/urls.py, applications/permissions.py
- config/urls.py : include the applications urls only
- config/settings.py : add MEDIA_ROOT = BASE_DIR / "media" and MEDIA_URL = "/media/" only
- DECISIONS.md : append one entry for this task
- Do NOT touch any test file or any model. Models are done.

## Response fields (exactly these, no others)
- Resume: id, title, file_name (name only, no URL), uploaded_at
- Application: id, job (id), job_title, company_name, candidate_username, resume (id), status, applied_at, updated_at. No emails.
- Notification: id, message, application (id), is_read, created_at

## Steps, in this order
1. POST /api/resumes/ (multipart: title, file) and GET /api/resumes/, candidates only, own resumes only. Validation exactly as CONTRACT failure rule 7 (content checks, 2 MB limit, empty file refused, case-insensitive extension). A failed upload leaves no Resume row and no stored file.
2. POST /api/applications/ {job, resume}, candidates only. Check in this order: job exists, resume exists (wrong or missing ids are 400 validation_error), job is open (job_closed), resume belongs to the candidate (invalid_resume), not already applied (duplicate_application). Create the Application and one Notification (recipient is the job's employer, message is "<candidate username> applied for <job title>") inside one transaction, so both exist or neither does (failure rule 1).
3. If the database unique constraint fires despite the checks, return 400 duplicate_application, never 500 (failure rule 4).
4. A failed apply creates no Application and no Notification (failure rule 2).
5. GET /api/applications/ : a candidate sees their own, an employer sees applications to their own jobs. Newest first, paginated.
6. GET /api/applications/<id>/ : only the candidate who applied or the employer who owns the job. Anyone else gets 404 not_found.
7. PATCH /api/applications/<id>/status/ {status} : employer who owns the job only. Allowed moves are in the CONTRACT "Status moves". Same status or any other move is 400 invalid_transition. An unknown status value is 400 validation_error. Candidates get 403, another employer gets 404. Allowed even when the job is closed (failure rule 6). Only `status` changes.
8. GET /api/notifications/ : employers only, own only, newest first, paginated.
9. Anonymous requests to any endpoint here get 401 not_authenticated.
10. Do not use raw SQL. Avoid one extra query per row in the lists (select_related).
11. Append one entry to DECISIONS.md in the CONTRACT format. Use only reasons from CONTRACT.md or this file.

## Done when
`python manage.py test accounts jobs applications` passes with no test edited.

## Report back
1. Result of the test run.
2. Table: each CONTRACT line, failure rule and amendment you implemented and the file it lives in.
3. Anything you were unsure about. Do not guess, list it.
