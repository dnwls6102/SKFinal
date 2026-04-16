from __future__ import annotations

import os

import streamlit as st


def get_secret(name: str) -> str:
    try:
        value = st.secrets.get(name)
    except Exception:
        value = None
    if value is not None:
        text = str(value).strip()
        if text:
            return text
    return os.getenv(name, "").strip()
