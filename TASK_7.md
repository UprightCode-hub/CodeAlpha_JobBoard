# TASK 7 (Copilot): Swagger schema hints

Read CONTRACT.md first, including "Rules for every agent" and amendment A14. Build only what is listed here.
Tasks 1 to 6 already pass. Do not change how any endpoint behaves.

## Why
The views are plain APIView classes with no serializer_class, so drf-spectacular cannot tell what each endpoint accepts or returns. The Swagger page then shows no request bodies, no filters and no response shapes. This task only adds documentation hints. Behavior stays identical.

## Files you may edit (create no files)
- jobs/views.py and applications/views.py : add `@extend_schema` decorators and the imports they need. Do not change any method body, permission, status code or query.
- config/settings.py : add `"TITLE": "CodeAlpha Job Board API"` to SPECTACULAR_SETTINGS (create that dict if it does not exist). Nothing else.
- DECISIONS.md : append one entry for this task.
- Do NOT touch any test file, model, serializer, URL file or accounts/views.py.
Use only `drf_spectacular.utils` (`extend_schema`, `inline_serializer`, `OpenApiParameter`, `OpenApiTypes`). Reuse the existing serializers for responses. If an existing serializer would show a wrong field in a request body (for example is_open, company, owner, id or created_at as writable), describe the request with `inline_serializer` instead. Do not edit the real serializer.

## What each endpoint must document
| Endpoint | Request | Query parameters | Response |
|---|---|---|---|
| GET /api/jobs/ | none | q, location (text); job_type, work_model, experience_level (with the allowed values from CONTRACT); min_salary, posted_within_days (integers); page (integer) | 200 paginated list of jobs |
| POST /api/jobs/ | JSON: title, description, location, job_type, work_model, experience_level, min_years_experience, salary_min, salary_max | none | 201 job |
| GET /api/jobs/{id}/ | none | none | 200 job |
| PATCH /api/jobs/{id}/ | same fields as create, all optional | none | 200 job |
| POST /api/jobs/{id}/close/ | no body at all | none | 200 job |
| GET /api/my/jobs/ | none | page | 200 paginated list of jobs |
| GET, POST, PATCH /api/company/ | POST and PATCH: JSON name, description | none | 200 or 201 company (name and description, no owner) |
| POST /api/resumes/ | multipart/form-data: title (text), file (binary) | none | 201 resume |
| GET /api/resumes/ | none | page | 200 paginated list of resumes |
| POST /api/applications/ | JSON: job (integer), resume (integer), nothing else | none | 201 application |
| GET /api/applications/ | none | page | 200 paginated list of applications |
| GET /api/applications/{id}/ | none | none | 200 application |
| PATCH /api/applications/{id}/status/ | JSON: status, one of applied, reviewing, shortlisted, rejected, hired | none | 200 application |
| GET /api/notifications/ | none | page | 200 paginated list of notifications |

Response fields are exactly the ones in CONTRACT A5 (job) and A13 (resume, application, notification).
A paginated list is documented as an object with count, next, previous and results, where results is a list of the item above.
Set `operation_id` on the two list and detail pairs so Swagger has no numbered duplicates: jobs_list, jobs_detail, applications_list, applications_detail. Every other operation id must also be unique with no number suffix.

## Done when
`python manage.py test accounts jobs applications` passes with no test edited, and the Swagger page at /api/docs/ shows a request body for every POST and PATCH above.

## Report back
1. Result of the test run.
2. Table: each endpoint above and the file where you added its hint.
3. Anything you were unsure about. Do not guess, list it.

## DECISIONS.md entry (use only these reasons)
Decision: describe requests and responses with `@extend_schema` on the existing views. Alternative rejected: rewrite the views as GenericAPIView so spectacular can guess serializers. Why: the views already pass their tests and the contract says change nothing that works; hints add documentation without touching behavior. What breaks if changed: a rewrite risks changing status codes or error shapes that Tasks 1 to 5 test.
