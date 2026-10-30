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
