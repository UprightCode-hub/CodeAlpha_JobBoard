# TASK 4 (Copilot): Resume, Application and Notification models

Read CONTRACT.md first, including "Rules for every agent", "Models", "Failure rules" and the "Amendments" at the bottom (A9 to A12 matter here). Build only what is listed here.
Tasks 1 to 3 already pass. Do not change their behavior. This task has no endpoints.
Wisdom has already run `python manage.py startapp applications`.

## Files you may create or edit (create no other files)
- applications/models.py
- applications/migrations/ (makemigrations only)
- config/settings.py : add "applications" to INSTALLED_APPS only
- DECISIONS.md : append one entry for this task
- Do NOT touch applications/tests.py or any other test file. They are already written.

## Steps, in this order
1. `Resume`: candidate (FK to the user model), title, file, uploaded_at (set automatically). A candidate can have many resumes.
2. `Application`: candidate, job, resume, status, applied_at (set automatically on creation), updated_at (updates on every save). on_delete rules exactly as in A9. Status values and default exactly as in A10.
3. A database UniqueConstraint on (candidate, job), named as in A12. Do not rely on code checks for this.
4. `Notification`: recipient (FK to the user model), application, message, is_read (default False), created_at (set automatically). on_delete rules as in A9.
5. Text limits as in A11.
6. Run `makemigrations` only. Do not run `migrate`.
7. Append one entry to DECISIONS.md in the CONTRACT format. Use only reasons from CONTRACT.md or this file.

## Done when
`python manage.py test accounts jobs applications` passes with no test edited.

## Report back
1. Result of the test run.
2. Table: each CONTRACT line and amendment you implemented and the file it lives in.
3. Anything you were unsure about. Do not guess, list it.
