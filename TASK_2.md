# TASK 2 (Copilot): Company and Job models, company endpoints, job create, update, close

Read CONTRACT.md first, including "Rules for every agent" and "Failure rules". Build only what is listed here.
Task 1 must already pass. Wisdom has already run `python manage.py startapp jobs`.

## Files you may create or edit (create no other files)
- jobs/ : models.py, serializers.py, views.py, urls.py, permissions.py, migrations/
- config/settings.py : add "jobs" to INSTALLED_APPS only
- config/urls.py : include the jobs urls only
- config/exceptions.py : add the 405 mapping (code method_not_allowed) only
- DECISIONS.md : append one entry for this task
- Do NOT touch jobs/tests_write.py or any other test file. They are already written.

## Steps, in this order
1. Models `Company` and `Job` exactly as in the CONTRACT. Run `makemigrations` only. Do not run `migrate`.
2. Permissions in jobs/permissions.py: an employer-only permission, and an ownership check for jobs (a job belongs to the employer who owns its company).
3. Company endpoints: POST, GET, PATCH on /api/company/ as in the CONTRACT. The owner always comes from the logged in user.
4. Job endpoints for this task only: POST /api/jobs/, PATCH /api/jobs/<id>/, POST /api/jobs/<id>/close/. Build the job views so that Task 3 can add list and detail (GET) later without rewriting your code. Do not build GET list, GET detail or /api/my/jobs/ now.
5. Do not enable DELETE or PUT on jobs. They must return 405 with the JSON error shape.
6. Validation (CONTRACT failure rules 8, 14, 15): salary_min <= salary_max, also when only one of them is sent on PATCH (compare against the saved value). No negative salary. min_years_experience >= 0. `is_open`, `company` and `owner` are read-only in every serializer.
7. Append one entry to DECISIONS.md in the CONTRACT format. Use only reasons from CONTRACT.md or this file.

## Done when
`python manage.py test accounts jobs` passes with no test edited.

## Report back
1. Result of the test run.
2. Table: each CONTRACT line you implemented and the file it lives in.
3. Anything you were unsure about. Do not guess, list it.
