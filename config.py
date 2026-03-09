"""Configuration helper: works with both Streamlit Cloud secrets and local .env."""

import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import streamlit as st


def get_secret(key: str, default: str = "") -> str:
    """Retrieve a secret from Streamlit secrets or environment variables.

    Priority: st.secrets > os.environ > default.
    """
    try:
        return st.secrets[key]
    except (KeyError, FileNotFoundError):
        pass
    return os.environ.get(key, default)


def get_bamboohr_credentials() -> tuple[str, str]:
    """Return (api_key, subdomain) from available secret stores."""
    api_key = get_secret("BAMBOOHR_API_KEY")
    subdomain = get_secret("BAMBOOHR_SUBDOMAIN")
    if not api_key or not subdomain:
        raise ValueError(
            "Missing BAMBOOHR_API_KEY or BAMBOOHR_SUBDOMAIN. "
            "Set them in .streamlit/secrets.toml (cloud) or .env (local)."
        )
    return api_key, subdomain
