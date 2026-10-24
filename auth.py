import functools
import os
import time

import jwt
from flask import g, jsonify, request

from models import User, db

ALGORITHM = "HS256"
ACCESS_TOKEN_TTL = int(os.environ.get("ACCESS_TOKEN_TTL", 900))          # 15 min
REFRESH_TOKEN_TTL = int(os.environ.get("REFRESH_TOKEN_TTL", 7 * 24 * 3600))  # 7 days


def _secret():
    secret = os.environ.get("JWT_SECRET")
    if not secret:
        raise RuntimeError("JWT_SECRET is not set (see .env.example)")
    return secret


def create_token(user, token_type):
    """token_type is 'access' or 'refresh'. A refresh token can't be used as an access token."""
    ttl = ACCESS_TOKEN_TTL if token_type == "access" else REFRESH_TOKEN_TTL
    now = int(time.time())
    payload = {
        "sub": str(user.id),
        "type": token_type,
        "iat": now,
        "exp": now + ttl,
    }
    return jwt.encode(payload, _secret(), algorithm=ALGORITHM)


def decode_token(token, expected_type):
    """Returns the payload, or raises jwt.InvalidTokenError (includes expiry)."""
    payload = jwt.decode(
        token, _secret(), algorithms=[ALGORITHM], options={"require": ["exp", "sub", "type"]}
    )
    if payload["type"] != expected_type:
        raise jwt.InvalidTokenError("Wrong token type")
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
                payload = decode_token(token, "access")
            except jwt.ExpiredSignatureError:
                return _unauthorized("Access token has expired")
            except jwt.InvalidTokenError:
                return _unauthorized()

            user = db.session.get(User, int(payload["sub"]))
            if user is None:
                return _unauthorized()
            if roles and user.role not in roles:
                return jsonify({"error": "You do not have permission to do this"}), 403

            g.current_user = user
            return fn(*args, **kwargs)

        return wrapper

    return decorator
