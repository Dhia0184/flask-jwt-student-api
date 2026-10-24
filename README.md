# Student Reports API

A REST API built with Flask for managing students and their reports, with JWT authentication and role-based access control (admin / student).


## Features

- CRUD endpoints for **students** and **reports**
- **Login with username and password**, returning a short-lived access token and a longer-lived refresh token (JWT)
- **Roles**: admins manage everything; students can read their own record and manage only their own reports
- Input validation with clear JSON error messages and consistent status codes
- Pagination on list endpoints (`?page=` and `?limit=`)
- Database migrations with Flask-Migrate
- Automated tests with pytest

## Tech stack

Python, Flask, Flask-SQLAlchemy (SQLAlchemy), SQLite, Flask-Migrate (Alembic), PyJWT, pytest

## Getting started

```bash
# 1. Clone and enter the project
git clone https://github.com/Dhia0184/flask-jwt-student-api.git
cd flask-jwt-student-api

# 2. Create a virtual environment and install dependencies
python -m venv venv
venv\Scripts\activate            # Windows  (macOS/Linux: source venv/bin/activate)
pip install -r requirements-dev.txt

# 3. Configure your environment
copy .env.example .env           # macOS/Linux: cp .env.example .env
# Open .env and set JWT_SECRET. Generate a value with:
python -c "import secrets; print(secrets.token_hex(32))"

# 4. Create the database tables
flask --app api db upgrade

# 5. Create the first admin account (you will be asked for a password)
flask --app api create-admin yourname

# 6. Run the API
flask --app api run
```

The API is now available at `http://127.0.0.1:5000`.

## Authentication

1. `POST /auth/login` with your username and password. You receive an `access_token` (valid 15 minutes) and a `refresh_token` (valid 7 days).
2. Send the access token on every protected request: `Authorization: Bearer <access_token>`.
3. When the access token expires, `POST /auth/refresh` with the refresh token to get a new one.

Only an admin can create accounts (`POST /auth/register`). A student account can be linked to a student record so that the student can access their own data.

Example:

```http
POST /auth/login
Content-Type: application/json

{ "username": "yourname", "password": "your-password" }
```

## Endpoints

| Method | Path | Access | Description |
|---|---|---|---|
| POST | `/auth/login` | public | Get access and refresh tokens |
| POST | `/auth/refresh` | refresh token | Get a new access token |
| GET | `/auth/me` | logged in | Current user |
| POST | `/auth/register` | admin | Create a user |
| GET | `/students` | admin | List students (paginated) |
| GET | `/students/count` | admin | Number of students |
| GET | `/students/<id>` | admin, or the linked student | One student |
| POST | `/students` | admin | Create a student |
| PUT | `/students/<id>` | admin | Update a student |
| DELETE | `/students/<id>` | admin | Delete a student (and their reports) |
| GET | `/reports` | public | List reports (paginated) |
| GET | `/reports/<id>` | public | One report |
| POST | `/reports` | admin, or the owning student | Create a report |
| PUT | `/reports/<id>` | admin, or the owning student | Update a report |
| DELETE | `/reports/<id>` | admin, or the owning student | Delete a report |

Business rule: a student can have at most **two** reports.

### Data

**Student**: `ID_S`, `FN` (first name), `LN` (last name), `DMjr` (boolean), `Level` (integer 1 to 4)

**Report**: `ID_R`, `ID_S`, `Title`, `Type`, `K1`, `K2`, `K3`, `Release_Date` (`YYYY-MM-DD`)

## Design decisions

- **Passwords are hashed**, never stored in plain text.
- **Two token types.** A refresh token cannot be used as an access token (the token carries a `type` claim that is checked).
- **Roles are read from the database** on each request, not from the token, so changing or deleting a user takes effect immediately.
- **Validation happens in layers**: request shape, then values (types, lengths, ranges), then database constraints. Text fields are trimmed before being checked and saved.
- **Failing early**: each route checks authentication, permissions, input and then the database in that order, and returns as soon as something is wrong.
- **Unexpected errors** are logged on the server, and the client only sees a generic message.

## Running the tests

```bash
pytest
```

The tests use their own temporary database, so they never touch your real data.

## Project structure

```
api.py                 routes, validation and helpers
auth.py                token creation and the @auth_required decorator
models.py              database models (Student, Report, User)
test_api.py            automated tests
migrations/            database migration history
requirements.txt       runtime dependencies
requirements-dev.txt   dependencies for development and tests
.env.example           template for environment variables
```

## Known limitations

- Tokens cannot be revoked before they expire (there is no logout or token blacklist).
- The "two reports per student" check is not atomic, so two simultaneous requests could both pass it.
- No rate limiting on the login endpoint yet.
- SQLite is used for simplicity.

## Planned improvements

- Docker setup
- Restructuring into an application package with blueprints
- Interactive API documentation
- Continuous integration with GitHub Actions
