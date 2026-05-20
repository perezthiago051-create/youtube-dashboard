import os
import pickle
import base64
import json
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]
CLIENT_SECRETS_FILE = "client_secrets.json"
TOKEN_FILE = "token.pickle"


def _running_on_cloud() -> bool:
    try:
        import streamlit as st
        return "token_b64" in st.secrets
    except Exception:
        return False


def authenticate():
    # ── En la nube: leer token desde st.secrets ───────────────────────────
    if _running_on_cloud():
        import streamlit as st
        token_bytes = base64.b64decode(st.secrets["token_b64"])
        creds = pickle.loads(token_bytes)
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        return creds

    # ── Local: flujo normal con archivo ──────────────────────────────────
    creds = None
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "rb") as f:
            creds = pickle.load(f)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "wb") as f:
            pickle.dump(creds, f)

    return creds


def get_youtube(creds):
    return build("youtube", "v3", credentials=creds)


def get_analytics(creds):
    return build("youtubeAnalytics", "v2", credentials=creds)
