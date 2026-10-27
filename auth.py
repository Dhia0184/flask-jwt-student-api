import functools
import os
import time

import jwt
from jwt import PyJWKClient
from flask import g, jsonify, request

from models import User, db

ALGORITHM = "HS256"
KEYCLOAK_ISSUER = os.environ.get(
    "KEYCLOAK_ISSUER", ""
).rstrip("/")

KEYCLOAK_AUDIENCE = os.environ.get("KEYCLOAK_AUDIENCE", "")
KEYCLOAK_JWKS_URL = os.environ.get("KEYCLOAK_JWKS_URL", "")

_jwks_client = (
    PyJWKClient(KEYCLOAK_JWKS_URL)
    if KEYCLOAK_JWKS_URL
    else None
)

def decode_keycloak_access_token(token):
    """Verify a Keycloak access token and return its claims."""

    if not all((
        KEYCLOAK_ISSUER,
        KEYCLOAK_AUDIENCE,
        KEYCLOAK_JWKS_URL,
    )):
        raise RuntimeError(
            "Keycloak settings are missing from the environment"
        )

    if _jwks_client is None:
        raise RuntimeError("Keycloak JWKS client is not configured")

    signing_key = _jwks_client.get_signing_key_from_jwt(token)

    payload = jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        issuer=KEYCLOAK_ISSUER,
        audience=KEYCLOAK_AUDIENCE,
        options={
            "require": ["exp", "iat", "sub", "iss", "aud"]
        },
    )

    if not isinstance(payload.get("sub"), str) or not payload["sub"]:
        raise jwt.InvalidTokenError("Invalid subject claim")

    return payload


def _unauthorized(message="A valid Bearer access token is required"):
    response = jsonify({"error": message})
    response.headers["WWW-Authenticate"] = "Bearer"
    return response, 401


def auth_required(*roles):
    """Protect a route. With no roles: any logged-in user. With roles: only those roles.
    Sets g.current_user. The role is read from the database, not from the token,
    so changing or deleting a user takes effect immediately."""

    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            scheme, _, token = request.headers.get("Authorization", "").partition(" ")
            if scheme.lower() != "bearer" or not token:
                return _unauthorized()
            try:
                payload = decode_keycloak_access_token(token)
            except jwt.ExpiredSignatureError:
                return _unauthorized("Access token has expired")
            except jwt.PyJWTError:
                return _unauthorized()
            user = User.query.filter_by(keycloak_sub=payload["sub"]).first()
            if user is None:
                return jsonify({"error": "This Keycloak identity is not linked to any local account"}), 403
            if roles and user.role not in roles:
                return jsonify({"error": "You do not have permission to do this"}), 403

            g.current_user = user
            return fn(*args, **kwargs)

        return wrapper

    return decorator
