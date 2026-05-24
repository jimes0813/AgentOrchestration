"""FastAPI application server."""

import os
from typing import Dict

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from .routes import router
from .middleware import (
    AuthMiddleware,
    RateLimitMiddleware,
    LoggingMiddleware,
    RedactMetadataMiddleware,
    validate_diagnostics_request,
)


def create_app(config: Dict = None) -> FastAPI:
    app = FastAPI(
        title="Agent Orchestrator API",
        version="2.4.1",
        description="Enterprise Agent Orchestration Platform API",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=os.getenv("TRUSTED_HOSTS", "*").split(","),
    )

    app.add_middleware(AuthMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(LoggingMiddleware)

    # RedactMetadataMiddleware is outermost so it filters the final response
    # body before it reaches the client, regardless of which handler produced it.
    app.add_middleware(RedactMetadataMiddleware, strict=True)

    app.include_router(router, prefix="/api/v2")

    # ------------------------------------------------------------------
    # Fix: /health is a public liveness endpoint — no auth required.
    # Load balancers, Kubernetes probes, and uptime monitors all call it
    # without credentials. Gating it behind validate_diagnostics_request
    # would break all health-check tooling.
    #
    # Sensitive metadata redaction is still applied automatically by
    # RedactMetadataMiddleware for every JSON response, including this one.
    # ------------------------------------------------------------------
    @app.get("/health")
    async def health():
        """Public liveness endpoint — no authentication required.

        Returns minimal, safe fields only. Any sensitive keys that somehow
        reach this response are stripped by RedactMetadataMiddleware before
        serialization.
        """
        return {
            "status": "healthy",
            "version": "2.4.1",
        }

    # ------------------------------------------------------------------
    # Internal diagnostics endpoint — authentication enforced via guard.
    #
    # Fix (defense-in-depth): the handler itself only returns safe, public
    # fields. It does NOT generate sensitive operational data and rely on
    # middleware to strip it afterwards. If middleware is ever removed or
    # misconfigured, no sensitive data leaks.
    # ------------------------------------------------------------------
    @app.get("/api/v2/diagnostics/health")
    async def diagnostics_health(request: Request):
        """Internal diagnostics health endpoint.

        Gated by the shared validate_diagnostics_request guard — returns
        a deterministic 401/415 without performing any lookup when the
        request is malformed or unauthenticated (bounty acceptance criterion).
        """
        valid, err = validate_diagnostics_request(request)
        if not valid:
            return err

        # Return only safe, non-sensitive operational status.
        # Sensitive fields (hostname, internal_ip, commit, build_id …) are
        # intentionally never generated here — the correct fix is to not
        # produce sensitive data, not to rely solely on post-hoc redaction.
        return {
            "status": "operational",
            "version": "2.4.1",
        }

    return app
