from __future__ import annotations

import json
from typing import Any

import streamlit as st
from streamlit_cookies_manager import EncryptedCookieManager

from config import get_secret


_COOKIE_PREFIX = "jooganbogo/"
_STATE_KEY = "_jooganbogo_cookie_manager"


def _get_password() -> str:
    value = get_secret("COOKIE_PASSWORD")
    if not value:
        raise RuntimeError("COOKIE_PASSWORD 시크릿(또는 환경변수)이 필요합니다.")
    return value


def get_cookies() -> EncryptedCookieManager:
    manager = EncryptedCookieManager(
        prefix=_COOKIE_PREFIX,
        password=_get_password(),
    )
    st.session_state[_STATE_KEY] = manager
    if not manager.ready():
        st.stop()
    return manager


def _current() -> EncryptedCookieManager:
    manager = st.session_state.get(_STATE_KEY)
    if manager is None:
        raise RuntimeError(
            "cookie_store.get_cookies()가 Streamlit 스크립트 최상단에서 먼저 호출되어야 합니다."
        )
    return manager


def load_json(key: str) -> Any:
    cookies = _current()
    raw = cookies.get(key)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        delete_key(key)
        return None


def save_json(key: str, value: Any) -> None:
    cookies = _current()
    cookies[key] = json.dumps(value, ensure_ascii=False)
    cookies.save()


def delete_key(key: str) -> None:
    cookies = _current()
    if key in cookies:
        del cookies[key]
        cookies.save()
