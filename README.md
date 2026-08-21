# Author ID Finder (HKUST Library - Research & Learning Support)

Internal web application MVP for retrieving key researcher identifiers from a publication title.

## What it does

Given a publication title (plus optional author name, year, DOI), the app finds and displays:

- Scopus Author ID
- Web of Science ResearcherID (when available via ORCID external IDs)
- Google Scholar profile ID/URL (optional integration)
- ORCID iD

It also provides:

- Candidate disambiguation list
- Confidence label and source note for each identifier
- One-click copy controls
- Plain text and JSON export
- Internal-use privacy notice

## Tech stack

- Python 3.10+
- Streamlit
- Requests

## Data sources

Primary:

- OpenAlex API
- ORCID public API

Optional / conditional:

- Scopus API (requires `SCOPUS_API_KEY`)
- Google Scholar via SerpAPI (requires `SERPAPI_API_KEY`)

## Quick start

1. Create and activate a Python virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Configure environment variables (optional keys):

```bash
copy .env.example .env
```

4. Run the app:

```bash
streamlit run app.py
```

## Deploy on Render

This project includes [render.yaml](render.yaml) for Render deployment.

1. Push this project to a Git repository that Render can access.
2. In Render, create a new Blueprint instance from that repository.
3. Confirm the detected web service configuration from [render.yaml](render.yaml).
4. Add environment variables in Render:

```text
SCOPUS_API_KEY=...
SERPAPI_API_KEY=...
CONTACT_EMAIL=...
```

5. Deploy the service.

Render start command used by the app:

```bash
streamlit run app.py --server.address 0.0.0.0 --server.port $PORT
```

Health check path:

```text
/_stcore/health
```

## Environment variables

- `SCOPUS_API_KEY`: optional, enables Scopus author profile verification.
- `SERPAPI_API_KEY`: optional, enables Google Scholar profile lookups.
- `CONTACT_EMAIL`: optional polite contact string for API User-Agent.

## Precision-first behavior

The app is tuned to avoid false positives:

- Uses title similarity + DOI/year/name evidence
- Prioritizes high-confidence candidates
- Surfaces "No high-confidence match found" when uncertain

## Limitations

- Web of Science identifiers are not always public; availability depends on ORCID or licensed services.
- Google Scholar has no official free public API; optional third-party integration is used.
- This MVP does not harvest full publication lists and does not create repository profiles automatically.

## Privacy

Search metadata is kept in Streamlit session state for troubleshooting and is not persisted by default.
