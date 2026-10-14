"""Tests for the FastAPI app configuration."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestCorsConfig:
    def test_no_credentials_with_wildcard_origin(self):
        """Wildcard origin plus allow_credentials is rejected by browsers per
        the Fetch spec, and this API uses no cookies or auth, so credentials
        have nothing to grant. The previous configuration had both."""
        from api import app

        mw = app.user_middleware[0]
        assert mw.kwargs["allow_credentials"] is False
        assert "*" in mw.kwargs["allow_origins"]

    def test_methods_are_not_wildcarded(self):
        from api import app

        mw = app.user_middleware[0]
        assert set(mw.kwargs["allow_methods"]) == {"GET", "POST"}

    def test_origins_are_configurable(self):
        """CORS_ORIGINS must be read at import; an explicit list replaces the
        wildcard for deployments in front of real data."""
        import importlib

        os.environ["CORS_ORIGINS"] = "https://claims.example.ae, https://internal.example.ae"
        try:
            import api

            importlib.reload(api)
            mw = api.app.user_middleware[0]
            assert mw.kwargs["allow_origins"] == [
                "https://claims.example.ae",
                "https://internal.example.ae",
            ]
            assert mw.kwargs["allow_credentials"] is False
        finally:
            del os.environ["CORS_ORIGINS"]
            importlib.reload(api)
