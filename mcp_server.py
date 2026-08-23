#!/usr/bin/env python3
"""Marktplaats MCP server — exposes Marktplaats.nl search as an MCP tool.

Unlike app.py (which uses a free LLM via OpenRouter to parse wishes and
filter results), this server runs NO AI on our side. It only fetches and
returns raw listing data. The connecting client — Claude, using the user's
own subscription — is expected to translate the user's wish into Dutch
search keywords and to judge which returned listings actually satisfy the
user's requirements.

Deployed on Vercel as a Streamable HTTP endpoint (see api/mcp.py and
vercel.json) and added to Claude.ai as a custom connector at:
  https://<your-app>.vercel.app/mcp

Local test:
  pip install mcp uvicorn
  python3 mcp_server.py
  # then point an MCP client (e.g. `npx @modelcontextprotocol/inspector`)
  # at http://localhost:8001/mcp
"""

import os

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from app import ALLOWED_RADII, search_marktplaats

INSTRUCTIONS = """This server searches Marktplaats.nl, the largest Dutch classifieds
site, and returns raw listing data. It does not run any AI itself.

When a user describes what they want to buy (in any language), you must:
1. Call search_marktplaats with concise DUTCH search keywords (the words a
   Dutch seller would put in a listing title), plus any price/radius bounds
   the user mentioned.
2. Read each returned listing's title, description and attributes yourself
   and judge which ones genuinely satisfy the user's stated requirements
   (size, condition, materials, features, ...) — the search only filters by
   keyword, price and distance, nothing else.
3. Present only the listings that hold up, with a short reason each, and
   link to the Marktplaats page (the `url` field) so the user can buy or
   contact the seller directly."""

mcp = FastMCP(
    "marktplaats",
    instructions=INSTRUCTIONS,
    stateless_http=True,
    json_response=True,
    # FastMCP auto-enables Host-header ("DNS rebinding") protection when it
    # thinks it's bound to localhost, which is the default. That protection
    # guards a server on your own machine against malicious webpages; it
    # doesn't apply to a public Vercel deployment reached over HTTPS by
    # Claude's backend (no browser, no cookies), and would otherwise reject
    # every real request since the Host header is the Vercel domain, not
    # "localhost".
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)


@mcp.tool()
def search_marktplaats_listings(
    query: str,
    postcode: str | None = None,
    radius_km: float | None = None,
    price_min_euro: float | None = None,
    price_max_euro: float | None = None,
    limit: int = 60,
) -> dict:
    """Search live listings on Marktplaats.nl (Dutch classifieds).

    This performs a real, live search — it does not filter or judge results
    beyond keyword/price/radius; you must read the returned listings and
    decide which ones match the user's actual requirements.

    Args:
        query: 2-4 concise DUTCH keywords, the way a Dutch seller would title
            the listing (e.g. "kledingkast hout"). Translate the user's wish
            into Dutch yourself — do not pass a full sentence or non-Dutch text.
        postcode: Dutch postcode (e.g. "1012AB"). Required if radius_km is set.
        radius_km: Only include listings within this many km of postcode.
            Snapped to the radii Marktplaats supports:
            1, 2, 3, 5, 10, 15, 25, 50, 75, 100 km.
        price_min_euro: Minimum price in euros, if the user gave one.
        price_max_euro: Maximum price in euros, if the user gave one.
        limit: Max listings to fetch, 1-100 (default 60).

    Returns:
        A dict with:
        - listings: list of {id, title, description, price, city,
          distance_km, attributes, image, url}, each a full, untruncated
          listing — read title/description/attributes to validate against
          the user's requirements.
        - total_on_marktplaats: total hits Marktplaats reports for this
          query (may be larger than len(listings) if it was capped by limit).
        - radius_km_used: the actual radius applied, after snapping to an
          allowed value (or null if no radius filter was applied).
    """
    if not query or not query.strip():
        raise ValueError("query must not be empty")
    limit = max(1, min(int(limit), 100))
    distance_meters = radius_km * 1000 if radius_km else None
    if distance_meters and not postcode:
        raise ValueError("postcode is required when radius_km is set")

    listings, total = search_marktplaats(
        query.strip(),
        postcode=postcode,
        distance_meters=distance_meters,
        price_min_euro=price_min_euro,
        price_max_euro=price_max_euro,
        limit=limit,
    )
    radius_used = None
    if distance_meters:
        radius_used = min(ALLOWED_RADII, key=lambda r: abs(r - distance_meters)) / 1000
    return {
        "listings": listings,
        "total_on_marktplaats": total,
        "radius_km_used": radius_used,
    }


app = mcp.streamable_http_app()


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "8001"))
    print(f"Marktplaats MCP server -> http://localhost:{port}/mcp")
    uvicorn.run(app, host="0.0.0.0", port=port)
