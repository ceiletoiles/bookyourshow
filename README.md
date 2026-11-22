# BookYourShow Apify sync

This folder owns the Apify integration for the MyFilmPeople “Now showing”
feature. It runs the `thirdwatch/bookmyshow-scraper` Actor in movie mode and
stores a small JSON snapshot that MyFilmPeople can import.

## Configuration

Set `APIFY_API_TOKEN` in the environment. Never commit the token.

Optional settings:

- `BOOKYOURSHOW_CITY` (default: `Bengaluru`)
- `BOOKYOURSHOW_MAX_RESULTS` (default: `200`)
- `BOOKYOURSHOW_RUN_TIMEOUT_SECONDS` (default: `600`)
- `BOOKYOURSHOW_HTTP_TIMEOUT_SECONDS` (default: `900`)
- `BOOKYOURSHOW_SYNC_KEY` to protect the sync endpoint

The service keeps movie records only, excludes listings with Indian-language
metadata, and stores one record per movie rather than one record per showtime.

## Run a snapshot

```powershell
python sync.py --city Bengaluru --max-results 50
```

The output is written to `data/now_showing.json`.

On Windows, start the local API with Waitress after installing the requirements:

```powershell
waitress-serve --listen=127.0.0.1:8001 app:application
```

## HTTP service

The WSGI application in `app.py` exposes:

- `GET /health`
- `GET /api/now-showing?city=Bengaluru`
- `POST /api/now-showing/sync` (requires `X-Sync-Key` when a key is configured)

It can be served with Gunicorn:

```powershell
gunicorn app:application
```
