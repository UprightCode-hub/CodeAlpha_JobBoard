# Decisions

Each entry gives the decision, the alternative I rejected, why, and what breaks if it is changed.

## Accounts and errors

- **Decision:** Use a custom `accounts.User` with a required unique email and an explicit employer or candidate role.
- **Alternative rejected:** Django's default user model with no role.
- **Why:** Every permission in the API depends on the role, and an employer and a candidate must never be confused. Setting it up at the start avoids a painful user model migration later.
- **What breaks if changed:** Role checks would need a second source of truth, and the user responses would lose the role.

- **Decision:** Use SimpleJWT for username and password login. Register and me responses expose only id, username, email and role.
- **Alternative rejected:** Write a custom token flow, or return more user fields.
- **Why:** SimpleJWT is a tested library, and writing my own token code adds risk for no benefit. The password never leaves the server.
- **What breaks if changed:** A custom flow would need its own security testing, and extra fields could leak data.

- **Decision:** Every error uses one JSON shape with a code and a plain sentence. Server errors show no internal detail.
- **Alternative rejected:** Return serializer details or exception text to the client.
- **Why:** One shape is easy for a client to handle, and exception text can expose internals.
- **What breaks if changed:** Clients would face several error formats, and 500 responses could leak code details.

## Companies and jobs

- **Decision:** One company per employer, enforced by a database OneToOne relation. The owner always comes from the logged-in user.
- **Alternative rejected:** Accept an owner in the request body, or allow many companies per employer.
- **Why:** Taking the owner from the request would let anyone act for another employer. The database rule holds even if the application code has a bug.
- **What breaks if changed:** An employer could create several companies or write jobs for someone else's company.

- **Decision:** Company, owner and `is_open` are read-only in create and PATCH. A job is closed only through its own close endpoint.
- **Alternative rejected:** Let clients set these fields in the body.
- **Why:** It stops a client from moving a job to another company or reopening a closed job by accident.
- **What breaks if changed:** A client could assign a job to the wrong company or bypass the close rule.

- **Decision:** Check the salary range against saved values on partial updates, and reject negative salaries and experience.
- **Alternative rejected:** Check the range only when both values are in the request.
- **Why:** A PATCH that changes only the minimum could otherwise push it above the saved maximum.
- **What breaks if changed:** A job could be saved with a minimum salary above its maximum.

- **Decision:** Job create, PATCH and close return the same fields as job reads, including the company name.
- **Alternative rejected:** Return a different shape from write endpoints.
- **Why:** A client should see one job shape everywhere. I found the mismatch by running the real server, not from the tests.
- **What breaks if changed:** Clients would need two parsers for the same job.

## Job reading and search

- **Decision:** Public job reads return a fixed set of fields. Filters use Django ORM lookups, and the company is loaded together with the job.
- **Alternative rejected:** Expose owner data, or build SQL from the search text.
- **Why:** ORM lookups keep search text safe from SQL injection, and loading the company with the job avoids one extra query per job in a list.
- **What breaks if changed:** Owner details could leak, or search text could become an injection path.

## Resumes, applications and notifications

- **Decision:** Protect applications from deletion through the candidate, job or resume. Resumes are deleted with their candidate, and notifications are deleted with their recipient or application.
- **Alternative rejected:** Cascade-delete application history, or keep notifications after their application is gone.
- **Why:** Application history is a record that should not vanish by accident. Notifications are disposable.
- **What breaks if changed:** Deleting a user, job or resume could silently erase application records.

- **Decision:** One application per candidate and job, enforced by the database constraint `unique_application_per_candidate_job`. Status has exactly five values and starts as `applied`.
- **Alternative rejected:** Check duplicates only in application code, or allow free-text statuses.
- **Why:** Two simultaneous requests can both pass a code check. The constraint is the real guard. A fixed status list keeps the data consistent.
- **What breaks if changed:** Duplicates could be stored, and statuses could drift.

- **Decision:** Resume titles and notification messages are limited to 255 characters. Uploads are stored under `resumes/`.
- **Alternative rejected:** Unlimited text fields.
- **Why:** The database columns have a fixed length, so the limit must be known and handled.
- **What breaks if changed:** Long values would raise database errors.

- **Decision:** Check the resume extension, size and file signature before saving. Create the application and its notification in one transaction.
- **Alternative rejected:** Trust the file name, or create the two records separately.
- **Why:** A renamed file can pretend to be a PDF, so the content is checked. One transaction means an application never exists without its notification.
- **What breaks if changed:** Fake files could be stored, or an application could exist with no notification.

- **Decision:** When a long job title would overflow a notification, cut the message to 255 characters.
- **Alternative rejected:** Reject the application, or let the database raise an error.
- **Why:** A candidate should not be blocked from applying because of how long an employer wrote a title. Found with a 255 character title that caused a 500.
- **What breaks if changed:** Applying to a job with a very long title would fail with a server error.

## Input limits and errors found by real runs

- **Decision:** Reject numbers above 2147483647 in salary, experience and the salary filter, and return 400 for a null character in search or location.
- **Alternative rejected:** Let the database reject them.
- **Why:** These inputs made the real database raise errors that became 500 responses. A client mistake should be a 400, not a server error.
- **What breaks if changed:** Large numbers or a null character would return a server error.

- **Decision:** Add a catch-all route so unknown URLs return the JSON `not_found` shape.
- **Alternative rejected:** Rely on Django's default 404 page.
- **Why:** With `DEBUG=True`, Django shows an HTML debug page for unknown URLs. The test runner turns debug off, so the tests never saw this. I found it by running the real server.
- **What breaks if changed:** Unknown URLs would return HTML in local development.

- **Decision:** Log 500 errors to the console.
- **Alternative rejected:** No logging setting.
- **Why:** A server error that leaves no trace cannot be investigated. I confirmed that a test-run error prints its traceback.
- **What breaks if changed:** Server errors would be invisible to whoever runs the server.

- **Decision:** Remove a manual `updated_at` guard from the status view and fix the test that depended on it.
- **Alternative rejected:** Keep the guard.
- **Why:** `updated_at` is `auto_now`, so the guard did nothing. A test that compared two clock readings was flaky because the two could be equal on Windows. The test now moves the stored time back before the update.
- **What breaks if changed:** The test could fail at random.

## Admin, demo data and API docs

- **Decision:** Register all six models in the Django admin with useful columns and search fields.
- **Alternative rejected:** Leave them unregistered.
- **Why:** The admin is the fastest way to inspect and fix data while developing.
- **What breaks if changed:** Data would be hard to inspect.

- **Decision:** `seed_demo` uses fixed usernames and create-or-get logic for the company and jobs.
- **Alternative rejected:** Create new records on every run.
- **Why:** The command must be safe to run twice. The password is for demo use only.
- **What breaks if changed:** Repeated runs would create duplicate demo data.

- **Decision:** Serve the OpenAPI schema at `/api/schema/` and Swagger UI at `/api/docs/`. Describe requests and responses with `@extend_schema` on the existing views.
- **Alternative rejected:** Rewrite the views as `GenericAPIView` so the schema is guessed.
- **Why:** The views already work and are tested, and hints add documentation without touching behavior. Swagger is how a reviewer can try the API without a frontend.
- **What breaks if changed:** A rewrite risks changing status codes or error shapes.

- **Decision:** Set `COMPONENT_SPLIT_REQUEST` so the resume upload field appears as a file chooser.
- **Alternative rejected:** Leave the field documented as a URL.
- **Why:** Without it, Swagger showed a text box instead of a Choose File button for resume uploads.
- **What breaks if changed:** The upload could not be tried from the docs page.

## What was verified by hand

- A fresh clone in a new folder, with a new virtual environment and an empty database, installed from `requirements.txt`, migrated, seeded and served the docs page.
- 139 checks over real HTTP against the running server, with `DEBUG=True`, all passed.
- 10 simultaneous apply requests by one candidate for one job gave 1 x 201 and 9 x 400 `duplicate_application`, with no 500. Afterwards the database held exactly 1 application and 1 notification. I could not tell whether the code check or the unique constraint rejected the nine.

## Not covered by tests

- Several candidates applying to one job at once, two status changes on one application at once, and closing a job while someone applies. Only the duplicate apply case above was tried.
- Dropped connections.
- Database down.
- Load beyond a few hundred users.

## Known gaps

- No refresh token endpoint, even though login returns a refresh token.
- No resume download endpoint.
- No reporting or statistics endpoint.
- No CORS headers, so a browser frontend on another address would be blocked.
- No rate limiting on login.
- Runs locally on the Django development server. Not hardened for production: HTTPS, SECRET_KEY handling and DEBUG.
- `DEBUG=False` is not supported yet, because `ALLOWED_HOSTS` is not configurable.
- Logging goes to the console only.
- The docs page needs an internet connection, because it loads its scripts from a CDN.
- Four cosmetic drf-spectacular warnings remain: one missing type hint, and three enum name collisions.

## If this grew 10x

- Move resume files to cloud storage.
- Add indexes on the search columns.
- Send notifications from a background worker.
- Add a refresh token endpoint.
- Make `ALLOWED_HOSTS` and `DEBUG` configurable for a real deployment.
