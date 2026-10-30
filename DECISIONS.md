# Decisions

## Task 1 — Project setup, custom User, auth, error handler

- **Decision:** Use a custom `accounts.User` with required unique email and an explicit employer/candidate role.
- **Alternative rejected:** Use Django's default user model without a role.
- **Why:** The contract requires `accounts.User`, unique email, and one of the two roles.
- **What breaks if changed:** Registration and authenticated user responses would not meet the contract.

- **Decision:** Use SimpleJWT's token obtain view for username/password login and expose only id, username, email, and role in register/me responses.
- **Alternative rejected:** Return a password field or implement a separate login token flow.
- **Why:** The contract specifies username/password login using SimpleJWT and forbids returning the password.
- **What breaks if changed:** The login response or user response shapes would not match the contract.

- **Decision:** Normalize API errors to the contract's JSON envelope and use generic messages.
- **Alternative rejected:** Return serializer details or exception text to API clients.
- **Why:** The contract requires one error shape and plain-sentence messages, with 500 details hidden.
- **What breaks if changed:** Error responses could expose implementation details or differ from the required shape.

## Task 2 — Company and Job models and write endpoints

- **Decision:** Enforce one company per employer with a database OneToOne relation and take company ownership from the authenticated user.
- **Alternative rejected:** Accept an owner from request data or allow multiple companies for one employer.
- **Why:** The contract specifies one company per owner, and Task 2 requires owners to come from the logged-in user.
- **What breaks if changed:** An employer could create multiple companies or act on behalf of another owner.

- **Decision:** Keep company, job openness, and ownership fields read-only in API serializers; close jobs through the dedicated close endpoint.
- **Alternative rejected:** Allow clients to choose a company or change `is_open` through create/PATCH.
- **Why:** The contract states that company and owner are never taken from the body and `is_open` changes only through close.
- **What breaks if changed:** Clients could assign jobs to another company or bypass the close endpoint.

- **Decision:** Validate salary ranges using supplied values and saved values for partial updates, and reject negative salaries or experience.
- **Alternative rejected:** Validate salary bounds only when both values are present in the request.
- **Why:** The contract explicitly requires PATCH comparisons against saved values and non-negative values.
- **What breaks if changed:** A partial update could persist a salary range with its minimum above its maximum.

## Task 3 — Job read endpoints and filters

- **Decision:** Serialize job reads with the contract's exact public fields, filter with Django ORM lookups, and select the related company for its name.
- **Alternative rejected:** Expose ownership data or interpolate filter text into SQL.
- **Why:** Amendment A5 fixes the response fields, and failure rule 13 requires search text to remain safe from SQL injection.
- **What breaks if changed:** Responses could leak owner data or filters could violate the required safe search behavior.

## Task 4 — Resume, Application, and Notification models

- **Decision:** Protect applications from deletion through candidate, job, or resume deletion, while cascading resume deletion with its candidate and notification deletion with its recipient or application.
- **Alternative rejected:** Cascade-delete application history or retain notifications after their application is removed.
- **Why:** Amendment A9 states that application history must not be lost accidentally and notifications are disposable.
- **What breaks if changed:** Deleting a candidate, job, or resume could remove an application record; notifications could outlive their application.

- **Decision:** Enforce one application per candidate/job with the database constraint `unique_application_per_candidate_job` and use exactly the five status values with `applied` as the default.
- **Alternative rejected:** Rely only on application code for duplicates or allow additional status values.
- **Why:** Amendment A10 defines the allowed status values, and A12 requires the named database constraint.
- **What breaks if changed:** Duplicate applications could be stored or application statuses could diverge from the contract.

- **Decision:** Limit resume titles and notification messages to 255 characters and store uploaded resume files under `resumes/`.
- **Alternative rejected:** Use unrestricted text fields or a different upload folder.
- **Why:** Amendment A11 specifies these limits and upload location.
- **What breaks if changed:** These model fields would not match the contract.

## Task 5 — Resume and application APIs

- **Decision:** Validate resume extension, size, and file signature before saving, and create each application with its notification inside one transaction.
- **Alternative rejected:** Trust file names alone or create the application and notification separately.
- **Why:** Failure rules 1 and 7 require atomic apply behavior and content-based upload validation with no row or stored file on failed validation.
- **What breaks if changed:** Invalid resume content could be stored or an application could exist without its notification.
