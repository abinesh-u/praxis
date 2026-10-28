"""Small deployment-bound identity verifier for the API boundary.

The production identity provider is intentionally external to this package. For
the current vertical slice, operators configure opaque bearer tokens through
``PRAXIS_AUTH_TOKENS`` (``owner_id=token`` pairs). When configured, route code
derives the owner from the verified token and rejects caller-supplied identity
claims that do not match it.
"""

from __future__ import annotations

import hmac
import os
from dataclasses import dataclass

from fastapi import HTTPException, Request, status


@dataclass(frozen=True)
class IdentityProvider:
    tokens: dict[str, str]

    @classmethod
    def from_environment(cls) -> IdentityProvider:
        raw = os.environ.get("PRAXIS_AUTH_TOKENS", "")
        tokens: dict[str, str] = {}
        for item in raw.split(","):
            if "=" not in item:
                continue
            owner, token = item.split("=", 1)
            if owner.strip() and token.strip():
                tokens[owner.strip()] = token.strip()
        return cls(tokens=tokens)

    def resolve(self, request: Request, claimed_owner: str) -> str:
        """Return the trusted owner, or reject an invalid/mismatched identity."""
        if not self.tokens:
            # Local development remains backwards-compatible until operators
            # configure an auth map. Production deployments must configure it.
            return claimed_owner

        authorization = request.headers.get("authorization", "")
        scheme, _, presented = authorization.partition(" ")
        if scheme.lower() != "bearer" or not presented:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Bearer authentication is required",
                headers={"WWW-Authenticate": "Bearer"},
            )

        for owner, expected in self.tokens.items():
            if hmac.compare_digest(presented, expected):
                if owner != claimed_owner:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Authenticated identity does not match requested owner",
                    )
                return owner

        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid bearer token")

    def resolve_operator(self, request: Request, claimed_owner: str | None = None) -> str:
        """Resolve authenticated operator identity for management routes.

        Enforces fail-closed authentication:
        - In production or when PRAXIS_AUTH_TOKENS is configured, valid bearer credentials
          are strictly required.
        - In development mode without auth tokens, access is explicitly restricted
          to a trusted local environment (PRAXIS_ENV in {'development', 'dev', 'test'}).
        - Conflicting owner identity between token and claimed_owner returns 403 Forbidden.
        - Missing or invalid credentials return 401 Unauthorized.
        - Never returns None or allows wildcard access across tenants.
        """
        authorization = request.headers.get("authorization", "")
        scheme, _, presented = authorization.partition(" ")
        has_bearer = scheme.lower() == "bearer" and bool(presented)

        if has_bearer:
            for owner, expected in self.tokens.items():
                if hmac.compare_digest(presented, expected):
                    if claimed_owner is not None and owner != claimed_owner:
                        raise HTTPException(
                            status_code=status.HTTP_403_FORBIDDEN,
                            detail="Authenticated identity does not match requested owner",
                        )
                    return owner
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid bearer token",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if self.tokens:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Bearer authentication is required",
                headers={"WWW-Authenticate": "Bearer"},
            )

        praxis_env = os.environ.get("PRAXIS_ENV", "").lower()
        dev_flag = os.environ.get("PRAXIS_ALLOW_DEV_NO_AUTH", "").lower()
        is_trusted_dev = praxis_env in ("development", "dev", "test") or dev_flag in ("1", "true")

        if not is_trusted_dev:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication is required in non-development deployment",
                headers={"WWW-Authenticate": "Bearer"},
            )

        return claimed_owner or "default_user"
