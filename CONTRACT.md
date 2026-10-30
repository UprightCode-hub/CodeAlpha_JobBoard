# CodeAlpha_JobBoard: CONTRACT

Every decision is made in this file. Agents build exactly this. Agents decide nothing.

## Rules for every agent
1. Scope is this file. Build only what is written. If something is missing or unclear, stop and ask Wisdom. Do not add it.
2. Sized for a few hundred users. No caching, Celery, Redis, extra layers. Plain Django and DRF.
3. One task per session, in order. Finish it, then stop.
4. Never edit another task's files unless the task says so.
5. Do not edit any test file. If a test fails, fix the code, not the test. If you think a test is wrong, stop and report.
6. At the end, report: files changed, anything unsure.

## Stack
Django, DRF, SimpleJWT, PostgreSQL (settings read from environment variables), Django admin. Tests: DRF APITestCase, run with `python manage.py test <app>`.
Apps: `accounts`, `jobs`, `applications`. Project package: `config`.
All endpoints are under `/api/`. Pagination: page number, 10 per page, response has `results`.

## Error shape (every error, every endpoint)
```
{"error": {"code": "<code>", "message": "<plain sentence>"}}
```
Codes: `not_authenticated` (401), `permission_denied` (403), `not_found` (404), `validation_error` (400), `duplicate_application` (400), `job_closed` (400), `invalid_resume` (400), `invalid_transition` (400), `method_not_allowed` (405), `server_error` (500).
Unknown URLs also return `not_found` as JSON. 500 errors hide details from the user and log them on the server.

## Models
- `accounts.User` (extends AbstractUser): `role` = employer or candidate. `email` required and unique. Login by username and password. `AUTH_USER_MODEL` is set before the first migrate.
- `jobs.Company`: `owner` OneToOne to User (employer), `name`, `description`.
- `jobs.Job`: `company` FK, `title`, `description`, `location`, `job_type` (full_time, part_time, contract, internship), `work_model` (remote, hybrid, onsite), `experience_level` (entry, mid, senior), `min_years_experience` int, `salary_min` and `salary_max` (optional ints), `is_open` bool default True, `created_at` auto. Jobs are never deleted.
- `applications.Resume`: `candidate` FK, `title`, `file`, `uploaded_at`.
- `applications.Application`: `candidate` FK, `job` FK (PROTECT), `resume` FK (PROTECT), `status` default applied, `applied_at`, `updated_at`. UniqueConstraint on (candidate, job).
- `applications.Notification`: `recipient` FK (employer), `application` FK, `message`, `is_read` default False, `created_at`.

## Endpoints
| Method and path | Who | Result |
|---|---|---|
| POST /api/auth/register/ {username, email, password, role} | anyone | 201 {id, username, email, role}. Password never returned. |
| POST /api/auth/login/ {username, password} | anyone | 200 {access, refresh}. Wrong credentials: 401 not_authenticated. |
| GET /api/auth/me/ | logged in | 200 {id, username, email, role} |
| POST /api/company/ {name, description} | employer | 201. Second company for same employer: 400 validation_error. |
| GET, PATCH /api/company/ | employer | own company. No company yet: 404 not_found. |
| GET /api/jobs/ | anyone | open jobs only, filters below |
| GET /api/jobs/<id>/ | anyone | open job. Closed job: 404 for everyone except its owner. |
| POST /api/jobs/ | employer with a company | 201. Candidate: 403. Employer with no company: 400 validation_error. |
| PATCH /api/jobs/<id>/ | owner employer | 200. Other employer: 403. |
| POST /api/jobs/<id>/close/ | owner employer | 200, `is_open` False. Other employer: 403. |
| GET /api/my/jobs/ | employer | own jobs, open and closed |
| DELETE on any job | nobody | 405 |
| POST /api/resumes/ multipart {title, file} | candidate | 201. Only .pdf and .docx, max 2 MB, else 400 validation_error. Employer: 403. |
| GET /api/resumes/ | candidate | own resumes only |
| POST /api/applications/ {job, resume} | candidate | 201. Closed job: 400 job_closed. Duplicate: 400 duplicate_application. Resume belongs to someone else: 400 invalid_resume. Employer: 403. Also creates one Notification for the job's employer. |
| GET /api/applications/ | candidate or employer | candidate sees own. Employer sees applications to own jobs. |
| GET /api/applications/<id>/ | candidate who applied, or employer who owns the job | anyone else: 404 not_found |
| PATCH /api/applications/<id>/status/ {status} | employer who owns the job | allowed moves below. Candidate: 403. Other employer: 404 not_found. |
| GET /api/notifications/ | employer | own notifications only, newest first |

## Job search filters (query params on GET /api/jobs/)
`q` (title or description contains), `location` (contains), `job_type`, `work_model`, `experience_level`, `min_salary` (jobs where salary_max >= value, jobs with no salary are excluded), `posted_within_days`. Filters can be combined. Newest jobs first.

## Status moves (forward only)
applied -> reviewing or rejected
reviewing -> shortlisted or rejected
shortlisted -> hired or rejected
hired and rejected are final. Anything else: 400 invalid_transition.

## Failure rules (each one has a test)
1. Apply is atomic. The Application and its Notification are created in one transaction. If either fails, neither exists.
2. A failed apply (duplicate, closed job, invalid resume, employer role) creates no Application and no Notification.
3. Retrying a successful apply is safe: it returns 400 duplicate_application and creates no new rows. We chose a clear error over silently returning 201 again, so the client knows nothing new happened.
4. If the unique constraint fires despite the pre-check (two simultaneous requests), the API returns 400 duplicate_application, never 500.
5. Status update to the same status returns 400 invalid_transition. Nothing changes.
6. Closing a job: existing applications stay visible to both sides and the employer can still change their status. New applications are refused with job_closed.
7. Resume upload checks content, not only the name. PDF must start with `%PDF-`. DOCX must be a zip (starts with `PK`). Extension check is case-insensitive. Empty file refused. A failed upload leaves no Resume row.
8. Job validation: salary_min <= salary_max, no negative salary, min_years_experience >= 0. Otherwise 400 validation_error.
9. Invalid filter values (job_type=banana, posted_within_days=abc) return 400 validation_error. A page number out of range returns 404 not_found.
10. Body ids that do not exist or have the wrong type (job, resume) return 400 validation_error. Unknown ids in the URL return 404 not_found.
11. Malformed JSON, empty body, missing fields, wrong types: 400 validation_error. Login with missing fields: 400 validation_error.
12. Tokens: expired, tampered, refresh token used as access token, token of a deleted or inactive user: all 401 not_authenticated.
13. Search text is never injected into SQL. Input like `'; DROP TABLE jobs;--` returns a normal 200 with no results.

14. Closing an already closed job returns 200 and changes nothing (safe to retry).
15. `is_open` can only be changed by the close endpoint. Create and PATCH ignore it. `company` and `owner` are never taken from the request body.

Not tested, and we say so in DECISIONS.md: truly simultaneous requests, dropped connections, database down. Atomic transactions (rule 1) are our protection against half-finished work.

## Task order
1. (Copilot) Project setup, custom User, register, login, me, error handler. Tests: accounts.
2. (Copilot) Company and Job models, company endpoints, job create, update, close. Tests: jobs (write part).
3. (Codex) Job list, detail, my jobs, filters. Tests: jobs (read part).
4. (Copilot) Resume, Application, Notification models and constraint. Tests: applications (models).
5. (Codex) Resume upload, apply, application list and detail, status update, notifications. Tests: applications (api).
6. (Copilot) Admin registrations, README, DECISIONS.md.

## Decision log (agent fills one entry per task in DECISIONS.md, using only reasons given in this file or by Wisdom)
Entry format: decision, alternative rejected, why, what breaks if changed.

## Amendments (the body above is never rewritten, changes are added here)
A1. Error codes also include `method_not_allowed` (405). (already in the codes line above)
A2. Failure rule 14: closing an already closed job returns 200 and changes nothing. (already in the rules above)
A3. Failure rule 15: `is_open` can only be changed by the close endpoint. Create and PATCH ignore it. `company` and `owner` are never taken from the request body. (already in the rules above)
A4. Text filters (q, location) are case-insensitive "contains".
A5. A job is returned with exactly these fields: id, title, description, location, job_type, work_model, experience_level, min_years_experience, salary_min, salary_max, is_open, created_at, company_name. Nothing about the owner (no owner id, no email).
A6. min_salary must be an integer >= 0. posted_within_days must be an integer >= 1. Bad values return 400 validation_error.
A7. GET /api/my/jobs/ is paginated like every list. An employer with no jobs gets 200 with empty results.
A8. Every list endpoint returns {count, next, previous, results}.

## Amendments (added before Task 4)
A9. Deletion rules (on_delete). Resume.candidate: CASCADE. Application.candidate: PROTECT. Application.job: PROTECT. Application.resume: PROTECT. Notification.recipient: CASCADE. Notification.application: CASCADE. Reason: the record of who applied to what is never lost by accident, notifications are disposable.
A10. Application.status values are exactly: applied, reviewing, shortlisted, rejected, hired. Default applied.
A11. Text limits: Resume.title and Notification.message are 255 characters. Resume.file uploads to the folder "resumes/".
A12. The unique constraint on Application (candidate, job) is named `unique_application_per_candidate_job`.

## Amendments (added before Task 5)
A13. Task 5 decisions.
a. Response fields, exactly these and no others. Resume: id, title, file_name (the file name only, no URL, because there is no download endpoint in this scope), uploaded_at. Application: id, job (the job id), job_title, company_name, candidate_username, resume (the resume id), status, applied_at, updated_at. No emails. Notification: id, message, application (the application id), is_read, created_at.
b. Notification message text is exactly "<candidate username> applied for <job title>".
c. Settings: MEDIA_ROOT is BASE_DIR / "media" and MEDIA_URL is "/media/".
d. GET /api/applications/ and GET /api/notifications/ are newest first and paginated like every list (A8). A page number out of range is 404 not_found.
e. Apply checks run in this order: job and resume ids exist (else 400 validation_error), job is open (else job_closed), resume belongs to the candidate (else invalid_resume), not already applied (else duplicate_application).
f. PATCH /api/applications/<id>/status/ returns 200 with the Application fields from (a). Only `status` changes. Other fields in the body are ignored. The status can be changed even when the job is closed. Changing a status creates no Notification.
g. A failed Resume upload leaves no Resume row and no stored file.

## Amendments (added before Task 7)
A14. Task 7 (Copilot) adds Swagger schema hints only, with no change to endpoint behavior. Files: jobs/views.py, applications/views.py, config/settings.py (TITLE only), DECISIONS.md. Tests: applications/tests_schema.py.

A15. Task 7b: SPECTACULAR_SETTINGS may also contain COMPONENT_SPLIT_REQUEST set to True, so file uploads are documented as binary. Schema documentation only, no change to endpoint behavior.`