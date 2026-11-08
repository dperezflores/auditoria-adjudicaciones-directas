"""Bloqueo de un único proceso Streamlit para escrituras de Google Sheets.

Este bloqueo NO sustituye una transacción distribuida. En producción,
utilizar backend transaccional o un servicio escritor único.
"""
from __future__ import annotations

import threading
import streamlit as st


@st.cache_resource
def get_writer_lock() -> threading.Lock:
    return threading.Lock()
