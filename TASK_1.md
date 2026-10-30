# TASK 1 (Copilot): Project setup, custom User, auth, error handler

Read CONTRACT.md first, including "Rules for every agent". Build only what is listed here.

## Files you may create or edit (create no other files)
- manage.py, config/ (settings.py, urls.py, exceptions.py, wsgi.py, asgi.py, __init__.py)
- accounts/ (__init__.py, apps.py, models.py, serializers.py, views.py, urls.py, migrations/)
- DECISIONS.md
- Do NOT touch accounts/tests.py. It is already written.

## Steps, in this order
1. Create the Django project `config` and the app `accounts`.
2. Set `AUTH_USER_MODEL = "accounts.User"` BEFORE running any migrate.
3. Settings read these from environment variables: SECRET_KEY, DEBUG, DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT. Database engine is PostgreSQL. Use python-dotenv to load a .env file. Do not create the .env file.
4. DRF settings: JWT authentication as the default authentication class, pagination PageNumberPagination with page size 10, and the custom exception handler (step 7).
5. `accounts.User`: as in the CONTRACT (role employer or candidate, email required and unique).
6. Endpoints exactly as the CONTRACT: register, login, me. Login uses SimpleJWT's token view. Register never returns the password.
7. `config/exceptions.py`: one DRF exception handler that returns the CONTRACT error shape for every error, with the correct code for each status (401 not_authenticated, 403 permission_denied, 404 not_found, 400 validation_error). Message is one plain sentence, never a raw serializer dump.
8. In `config/urls.py`: set handler404 and handler500 so unknown URLs and server errors also return the JSON error shape (not_found, server_error). The 500 handler hides details from the user.
9. Create DECISIONS.md with one entry for this task, in the format at the bottom of CONTRACT.md. Use only reasons given in CONTRACT.md or this file.

## Done when
`python manage.py test accounts` passes with no test edited.

## Report back
1. Result of the test run.
2. Table: each CONTRACT line you implemented and the file it lives in.
3. Anything you were unsure about. Do not guess, list it.
