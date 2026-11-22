"""Run the BookMyShow Actor and save a compact movie-only snapshot."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv


load_dotenv(Path(__file__).resolve().parent / ".env")


ACTOR_RUN_URL = "https://api.apify.com/v2/acts/thirdwatch~bookmyshow-scraper/runs"
ACTOR_RUN_TIMEOUT_SECONDS = int(os.getenv("BOOKYOURSHOW_RUN_TIMEOUT_SECONDS", "600"))
HTTP_REQUEST_TIMEOUT_SECONDS = int(os.getenv("BOOKYOURSHOW_HTTP_TIMEOUT_SECONDS", "900"))
DATA_PATH = Path(__file__).resolve().parent / "data" / "now_showing.json"

INDIAN_LANGUAGE_NAMES = {
    "assamese", "bengali", "bodo", "dogri", "gujarati", "hindi", "kannada",
    "konkani", "maithili", "malayalam", "manipuri", "marathi", "odia",
    "punjabi", "sanskrit", "tamil", "telugu", "urdu",
}


def _token() -> str:
    value = os.getenv("APIFY_API_TOKEN", "").strip()
    if not value:
        raise RuntimeError("APIFY_API_TOKEN is not configured")
    return value


def _is_non_indian_movie(item: dict[str, Any]) -> bool:
    """Exclude listings whose BookMyShow language metadata identifies Indian cinema."""
    languages = item.get("languages")
    if not isinstance(languages, list):
        return True
    normalized = {
        str(language).strip().casefold()
        for language in languages
        if str(language).strip()
    }
    return not normalized.intersection(INDIAN_LANGUAGE_NAMES)


def _run_actor(city: str, max_results: int) -> dict[str, Any]:
    response = requests.post(
        ACTOR_RUN_URL,
        # Apify caps this synchronous wait at 60 seconds. We poll below when
        # the run is still READY/RUNNING after the initial response.
        params={"token": _token(), "waitForFinish": "60"},
        json={
            "city": city,
            "includeDetails": True,
            "maxResults": max_results,
            "mode": "movies",
            "queries": [city],
        },
        timeout=HTTP_REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    run = response.json()
    run_data = run.get("data") or {}
    run_id = run_data.get("id")
    status = str(run_data.get("status") or "").upper()
    terminal_statuses = {"SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"}
    deadline = time.monotonic() + ACTOR_RUN_TIMEOUT_SECONDS

    while run_id and status not in terminal_statuses and time.monotonic() < deadline:
        time.sleep(5)
        poll_response = requests.get(
            f"https://api.apify.com/v2/actor-runs/{run_id}",
            params={"token": _token(), "waitForFinish": "60"},
            timeout=HTTP_REQUEST_TIMEOUT_SECONDS,
        )
        poll_response.raise_for_status()
        run = poll_response.json()
        run_data = run.get("data") or {}
        status = str(run_data.get("status") or "").upper()

    if status not in terminal_statuses:
        raise RuntimeError(f"Apify run timed out while waiting: {status or 'unknown'}")
    if status != "SUCCEEDED":
        message = run_data.get("statusMessage") or status
        raise RuntimeError(f"Apify run failed: {message}")
    return run


def sync_movies(city: str, max_results: int) -> dict[str, Any]:
    run = _run_actor(city, max_results)
    dataset_id = (run.get("data") or {}).get("defaultDatasetId")
    status = ((run.get("data") or {}).get("status") or "").upper()
    if status != "SUCCEEDED" or not dataset_id:
        raise RuntimeError(f"Apify run did not succeed: {status or 'unknown'}")

    items_response = requests.get(
        f"https://api.apify.com/v2/datasets/{dataset_id}/items",
        params={"token": _token(), "clean": "true", "format": "json"},
        timeout=HTTP_REQUEST_TIMEOUT_SECONDS,
    )
    items_response.raise_for_status()
    items = [
        item
        for item in items_response.json()
        if isinstance(item, dict)
        and str(item.get("type") or "movie").strip().lower() == "movie"
        and _is_non_indian_movie(item)
    ]
    snapshot = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "city": city,
        "mode": "movies",
        "filters": {"non_indian_movies_only": True},
        "run_id": (run.get("data") or {}).get("id", ""),
        "dataset_id": dataset_id,
        "items": items,
    }
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    DATA_PATH.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    return snapshot


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--city", default=os.getenv("BOOKYOURSHOW_CITY", "Bengaluru"))
    parser.add_argument("--max-results", type=int, default=int(os.getenv("BOOKYOURSHOW_MAX_RESULTS", "200")))
    args = parser.parse_args()
    snapshot = sync_movies(args.city, args.max_results)
    print(f"Saved {len(snapshot['items'])} movies for {snapshot['city']} to {DATA_PATH}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (requests.RequestException, RuntimeError) as exc:
        print(f"BookYourShow sync failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
