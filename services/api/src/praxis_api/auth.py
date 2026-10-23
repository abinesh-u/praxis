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
