"""Small WSGI adapter exposing the latest BookYourShow snapshot."""

from __future__ import annotations

import json
import os
from urllib.parse import parse_qs

from sync import DATA_PATH, sync_movies


def _response(start_response, status: str, payload: dict) -> list[bytes]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    start_response(status, [("Content-Type", "application/json; charset=utf-8"), ("Content-Length", str(len(body)))])
    return [body]


def application(environ, start_response):
    path = environ.get("PATH_INFO", "")
    if path == "/health":
        return _response(start_response, "200 OK", {"ok": True})

    if path == "/api/now-showing" and environ.get("REQUEST_METHOD") == "GET":
        if not DATA_PATH.exists():
            return _response(start_response, "404 Not Found", {"error": "No snapshot has been generated yet"})
        snapshot = json.loads(DATA_PATH.read_text(encoding="utf-8"))
        city = parse_qs(environ.get("QUERY_STRING", "")).get("city", [""])[0].strip().lower()
        if city and snapshot.get("city", "").lower() != city:
            return _response(start_response, "404 Not Found", {"error": "No snapshot for that city"})
        return _response(start_response, "200 OK", snapshot)

    if path == "/api/now-showing/sync" and environ.get("REQUEST_METHOD") == "POST":
        expected_key = os.getenv("BOOKYOURSHOW_SYNC_KEY", "").strip()
        supplied_key = environ.get("HTTP_X_SYNC_KEY", "")
        if expected_key and supplied_key != expected_key:
            return _response(start_response, "401 Unauthorized", {"error": "Invalid sync key"})
        city = os.getenv("BOOKYOURSHOW_CITY", "Bengaluru")
        max_results = int(os.getenv("BOOKYOURSHOW_MAX_RESULTS", "50"))
        try:
            return _response(start_response, "200 OK", sync_movies(city, max_results))
        except Exception as exc:  # keep the endpoint response JSON for the importer
            return _response(start_response, "502 Bad Gateway", {"error": str(exc)})

    return _response(start_response, "404 Not Found", {"error": "Not found"})
