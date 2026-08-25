#!/usr/bin/env python3
"""Affiliate link helpers for eBay Partner Network and Awin.

Stdlib-only, same style as app.py. Every function degrades gracefully to
"not configured" (returns None / the plain input URL) when its env vars
are missing, so the app and deal hunter keep working without these
integrations set up — same pattern as OPENROUTER_API_KEY and Upstash.

Env vars (all optional; see README for where to get each one):
  EBAY_CLIENT_ID, EBAY_CLIENT_SECRET  — eBay Developer Program application
                                         keys (production keyset)
  EBAY_EPN_CAMPAIGN_ID                — eBay Partner Network Campaign ID
  AWIN_PUBLISHER_ID                   — Awin publisher (affiliate) ID
"""

import base64
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

EBAY_CLIENT_ID = os.environ.get("EBAY_CLIENT_ID", "")
EBAY_CLIENT_SECRET = os.environ.get("EBAY_CLIENT_SECRET", "")
EBAY_EPN_CAMPAIGN_ID = os.environ.get("EBAY_EPN_CAMPAIGN_ID", "")
EBAY_OAUTH_URL = os.environ.get(
    "EBAY_OAUTH_URL", "https://api.ebay.com/identity/v1/oauth2/token"
)

AWIN_PUBLISHER_ID = os.environ.get("AWIN_PUBLISHER_ID", "")

# ---------------------------------------------------------------- eBay

_ebay_token_lock = threading.Lock()
_ebay_token = {"value": None, "expires_at": 0}


def ebay_configured():
    return bool(EBAY_CLIENT_ID and EBAY_CLIENT_SECRET)


def ebay_epn_configured():
    return bool(EBAY_EPN_CAMPAIGN_ID)


def ebay_oauth_token():
    """Application access token via the client credentials grant, cached
    in-process until shortly before it expires. Returns None if
    EBAY_CLIENT_ID/EBAY_CLIENT_SECRET aren't set, or on any failure."""
    if not ebay_configured():
        return None
    with _ebay_token_lock:
        if _ebay_token["value"] and time.time() < _ebay_token["expires_at"]:
            return _ebay_token["value"]
        basic = base64.b64encode(
            f"{EBAY_CLIENT_ID}:{EBAY_CLIENT_SECRET}".encode()
        ).decode()
        body = urllib.parse.urlencode(
            {"grant_type": "client_credentials",
             "scope": "https://api.ebay.com/oauth/api_scope"}
        ).encode()
        req = urllib.request.Request(
            EBAY_OAUTH_URL,
            data=body,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Authorization": "Basic " + basic,
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode())
            token = data["access_token"]
            # refresh a bit early rather than racing the real expiry
            _ebay_token["value"] = token
            _ebay_token["expires_at"] = time.time() + int(data.get("expires_in", 7200)) - 60
            return token
        except Exception:
            return None


def ebay_enduserctx_header():
    """Value for the X-EBAY-C-ENDUSERCTX header that makes the Browse API
    return itemAffiliateWebUrl (the EPN-tracked link) on each item. None
    if EBAY_EPN_CAMPAIGN_ID isn't set."""
    if not ebay_epn_configured():
        return None
    return f"affiliateCampaignId={EBAY_EPN_CAMPAIGN_ID}"


# ---------------------------------------------------------------- Awin

def awin_configured():
    return bool(AWIN_PUBLISHER_ID)


def awin_link(destination_url, advertiser_id, clickref=None):
    """Wrap destination_url as an Awin tracking (deep) link for
    advertiser_id, via the standard awin1.com/cread.php redirect —
    https://www.awin1.com/cread.php?awinmid=<advertiser>&awinaffid=<publisher>&ued=<url>

    Returns destination_url unchanged if AWIN_PUBLISHER_ID or
    advertiser_id isn't set, so callers degrade to a plain (non-affiliate)
    link rather than failing.
    """
    if not awin_configured() or not advertiser_id or not destination_url:
        return destination_url
    params = {
        "awinmid": str(advertiser_id),
        "awinaffid": AWIN_PUBLISHER_ID,
        "ued": destination_url,
    }
    if clickref:
        params["clickref"] = str(clickref)[:100]
    return "https://www.awin1.com/cread.php?" + urllib.parse.urlencode(params)
