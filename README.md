
# Student Reports API

A REST API built with Flask for managing students and their reports. It uses Keycloak for authentication and database-driven role-based access control.

## Features

- Student and report CRUD operations
- OAuth 2.0 / OpenID Connect authentication with Keycloak
- Access-token validation using Keycloak's JWKS public signing keys
- Database-driven authorization with `admin` and `student` roles
- Student ownership checks for records and reports
- Input validation and consistent JSON error responses
- Pagination for list endpoints
- Database schema migrations using Flask-Migrate and Alembic
- Automated tests with pytest

## Tech Stack

- Python
- Flask
- Flask-SQLAlchemy and SQLAlchemy
- SQLite
- Flask-Migrate and Alembic
- Keycloak
- PyJWT with cryptographic support
- pytest
- Insomnia for API testing

## Authentication Architecture

Keycloak is responsible for authenticating users and issuing access tokens. Flask does not issue its own access or refresh tokens.

For protected requests:

1. The client authenticates with Keycloak using OpenID Connect.
2. Keycloak issues an access token.
3. The client sends the token in the HTTP `Authorization` header.
4. Flask verifies the token signature, issuer, audience, and required claims.
5. Flask resolves the token's `sub` to a local user through `users.keycloak_sub`.
6. Flask checks the local user's role and student ownership before permitting the operation.

The local database stores application roles and student associations. Keycloak identities are mapped using the token's `sub` claim rather than relying on username equality.

## Requirements

- Python installed on your machine
- Docker Desktop for a local Keycloak instance
- Git
- Insomnia or another OAuth 2.0-compatible client

## Local Setup

### 1. Clone the repository

```powershell
git clone https://github.com/Dhia0184/flask-jwt-student-api.git
cd flask-jwt-student-api
```

### 2. Create a virtual environment and install dependencies

On Windows PowerShell:

```powershell
python -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

### 3. Configure environment variables

Create a local `.env` file:

```powershell
Copy-Item .env.example .env
```

Configure these values in `.env`:

```dotenv
KEYCLOAK_ISSUER=http://localhost:8080/realms/university-api
KEYCLOAK_AUDIENCE=university-api
KEYCLOAK_JWKS_URL=http://localhost:8080/realms/university-api/protocol/openid-connect/certs
```

The default database is the local SQLite file `students.db`. Set `DATABASE_URL` only when you need to use a different database.

Never commit `.env` or actual credentials to GitHub.

### 4. Start Keycloak locally

For local development, Keycloak can run in Docker:

```powershell
docker run --name keycloak-dev -p 127.0.0.1:8080:8080 -e KC_BOOTSTRAP_ADMIN_USERNAME=admin -e KC_BOOTSTRAP_ADMIN_PASSWORD=replace-with-a-local-password quay.io/keycloak/keycloak:26.8.1 start-dev
```

This uses Keycloak development mode and is not a production deployment configuration.

Open the Keycloak Admin Console at:

`http://localhost:8080`

Create a realm named `university-api`. Configure a client for Insomnia with:

- Client type: OpenID Connect
- Client authentication: Off
- Standard flow: On
- PKCE: Required, using S256
- Valid redirect URI: `https://app.insomnia.rest/oauth/redirect`

Configure an Audience mapper so that `university-api` is included in the access token's audience claim.

For subsequent development sessions, start the existing container with:

```powershell
docker start keycloak-dev
```

### 5. Apply database migrations

From the project directory:

```powershell
.\venv\Scripts\python.exe -m flask --app api db upgrade
```

This applies the recorded schema migrations to the configured database.

### 6. Start the Flask API

```powershell
.\venv\Scripts\python.exe -m flask --app api run
```

The API is available at:

`http://localhost:5000`

## Using Insomnia

Configure OAuth 2.0 with Authorization Code and PKCE (S256).

- Authorization URL: `http://localhost:8080/realms/university-api/protocol/openid-connect/auth`
- Token URL: `http://localhost:8080/realms/university-api/protocol/openid-connect/token`
- Client ID: `insomnia-client`
- Scope: `openid profile email`
- Redirect URI: `https://app.insomnia.rest/oauth/redirect`

Fetch an access token and send it with protected requests:

```http
Authorization: Bearer <access_token>
```

The access token must have the expected issuer and audience and must be issued by the configured Keycloak realm.

## User Provisioning

User authentication is handled by Keycloak, while application-specific roles and student associations are stored locally.

A Keycloak account must be linked to a local `User` record through `keycloak_sub` before it can access protected endpoints. The local record determines the application's role and, for students, the associated `ID_S`.

Automated user provisioning and account linking are not currently exposed as API endpoints.

## API Endpoints

| Method | Endpoint | Access |
|---|---|---|
| GET | `/auth/me` | Authenticated user |
| GET | `/students` | Admin |
| GET | `/students/count` | Admin |
| GET | `/students/<id>` | Admin or owning student |
| POST | `/students` | Admin |
| PUT | `/students/<id>` | Admin |
| DELETE | `/students/<id>` | Admin |
| GET | `/reports` | Public |
| GET | `/reports/<id>` | Public |
| POST | `/reports` | Admin or owning student |
| PUT | `/reports/<id>` | Admin or owning student |
| DELETE | `/reports/<id>` | Admin or owning student |

List endpoints support `page` and `limit` query parameters. The page size is capped at 100, and list responses include an `X-Total-Count` header.

Business rule: a student may have at most two reports.

## Data Models

**Student**

- `ID_S`: primary key
- `FN`: first name
- `LN`: last name
- `DMjr`: boolean
- `Level`: integer from 1 to 4

**Report**

- `ID_R`: primary key
- `ID_S`: associated student
- `Title`
- `Type`
- `K1`, `K2`, `K3`: keywords
- `Release_Date`: date in `YYYY-MM-DD` format

**User**

- `id`: local primary key
- `username`
- `keycloak_sub`: linked Keycloak subject
- `role`: `admin` or `student`
- `ID_S`: associated student ID, where applicable

## Running the Tests

Run the test suite with:

```powershell
.\venv\Scripts\python.exe -m pytest -q
```

The automated tests use a temporary database and mock token verification to test route authentication, roles, ownership, validation, and CRUD behavior without requiring a live Keycloak instance for every test.

## Project Structure

```text
api.py                 API routes and validation
auth.py                Keycloak token verification and authorization
models.py              Student, Report, and User models
test_api.py            Automated tests
migrations/            Database migration history
requirements.txt       Runtime dependencies
requirements-dev.txt   Runtime and test dependencies
.env.example           Environment configuration template
```

## Known Limitations

- Users must be provisioned and linked to local accounts through a trusted administrative workflow.
- Local development uses SQLite and Keycloak development mode.
- The maximum-reports-per-student check is not atomic under concurrent requests.
- Production deployment requires appropriate HTTPS, secrets management, and server configuration.
