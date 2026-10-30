# Job Board API

This project is a job board API where employers can publish job listings and candidates can maintain resumes and apply for jobs. It includes account authentication, company and job management, resume and application workflows, and employer notifications.

## Stack

- Python
- Django
- Django REST Framework
- SimpleJWT
- PostgreSQL
- drf-spectacular for OpenAPI and Swagger documentation

## Setup

1. Create and activate a virtual environment:

   ```powershell
   py -m venv .venv
   .venv\Scripts\Activate.ps1
   ```

2. Install project dependencies:

   ```powershell
   pip install -r requirements.txt
   ```

3. Create a PostgreSQL database and user, then copy `.env.example` to `.env` and set the local database values and a local `SECRET_KEY`.

4. Apply the database migrations:

   ```powershell
   python manage.py migrate
   ```

5. Start the development server:

   ```powershell
   python manage.py runserver
   ```

## Run the tests

Run the app tests with:

```powershell
python manage.py test accounts jobs applications
```

## Try the API

Create the repeatable demo employer, candidate, company, and jobs:

```powershell
python manage.py seed_demo
```

The command prints the demo usernames and password. Open the Swagger page at [http://127.0.0.1:8000/api/docs/](http://127.0.0.1:8000/api/docs/) to explore the API.

## Data model

```mermaid
erDiagram
    User ||--o| Company : owns
    Company ||--o{ Job : publishes
    User ||--o{ Resume : owns
    User ||--o{ Application : submits
    Job ||--o{ Application : receives
    Resume ||--o{ Application : attached_to
    User ||--o{ Notification : receives
    Application ||--o{ Notification : creates

    User {
        int id PK
        string username
        string email
        string role
    }
    Company {
        int id PK
        int owner_id FK
        string name
        string description
    }
    Job {
        int id PK
        int company_id FK
        string title
        string job_type
        string work_model
    }
    Resume {
        int id PK
        int candidate_id FK
        string title
        string file
    }
    Application {
        int id PK
        int candidate_id FK
        int job_id FK
        int resume_id FK
        string status
    }
    Notification {
        int id PK
        int recipient_id FK
        int application_id FK
        string message
        boolean is_read
    }
```

## Application flow

```mermaid
flowchart TD
    A[Request with JWT] --> B{JWT is valid?}
    B -- No --> X[Return not_authenticated]
    B -- Yes --> C{User is a candidate?}
    C -- No --> Y[Return permission_denied]
    C -- Yes --> D{Job is open?}
    D -- No --> Z[Return job_closed]
    D -- Yes --> E{Resume belongs to candidate?}
    E -- No --> W[Return invalid_resume]
    E -- Yes --> F[Start one database transaction]
    F --> G{Unique constraint allows application?}
    G -- No --> X2[Return duplicate_application]
    G -- Yes --> H[Create Application]
    H --> I[Create Notification]
    I --> J[Commit transaction]
```

See [DECISIONS.md](./DECISIONS.md) for recorded implementation decisions.
