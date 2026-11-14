`cloudflare_challenge.html` and `api_unauthenticated.json` are REAL responses (2026-10-13): beatport.com answers HTTP 403
"Just a moment..." (Cloudflare managed challenge) to plain HTTP, headless and headed Chromium, and api.beatport.com/v4
answers 401 without a token.

`UNVERIFIED_*.json` are NOT real responses. No real Beatport data could be fetched, so they are written by hand in the shape
of Beatport's public v4 API documentation (track and release lists under "results"). Replace them with saved real responses
once a BEATPORT_TOKEN is available (`pytest --live` with the token set will show whether the shape holds).
