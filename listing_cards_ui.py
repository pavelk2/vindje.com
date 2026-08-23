"""The MCP Apps (SEP-1865) `ui://` resource for search_marktplaats_listings.

Hosts that support MCP Apps (e.g. claude.ai) render this HTML in a sandboxed
iframe instead of, or alongside, the tool's plain-text result, turning each
listing into a photo card. Hosts that don't support MCP Apps simply ignore
the resource and fall back to the tool's normal text/structured output, so
this is purely additive.

Kept dependency-free on purpose (no npm package, no build step) to match the
rest of this project: it hand-rolls the small JSON-RPC-over-postMessage
handshake described in the MCP Apps spec
(https://github.com/modelcontextprotocol/ext-apps) instead of pulling in
`@modelcontextprotocol/ext-apps`.
"""

LISTING_CARDS_UI_RESOURCE_URI = "ui://marktplaats/listing-cards"

LISTING_CARDS_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>Marktplaats listings</title>
<style>
  :root {
    --mp-bg: #ffffff;
    --mp-fg: #14161a;
    --mp-muted: #5b6270;
    --mp-border: #e4e6ea;
    --mp-card-bg: #ffffff;
    --mp-accent: #f36c21;
  }
  :root[data-theme="dark"] {
    --mp-bg: #14161a;
    --mp-fg: #f2f3f5;
    --mp-muted: #9aa1ad;
    --mp-border: #2a2d33;
    --mp-card-bg: #1c1f24;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    padding: 12px;
    background: var(--mp-bg);
    color: var(--mp-fg);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  }
  #status { color: var(--mp-muted); font-size: 14px; padding: 4px 2px 12px; }
  #grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(170px, 1fr));
    gap: 12px;
  }
  .card {
    border: 1px solid var(--mp-border);
    border-radius: 12px;
    overflow: hidden;
    background: var(--mp-card-bg);
    display: flex;
    flex-direction: column;
    text-decoration: none;
    color: inherit;
  }
  .card:hover { border-color: var(--mp-accent); }
  .thumb {
    aspect-ratio: 4 / 3;
    background: var(--mp-border);
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--mp-muted);
    font-size: 12px;
  }
  .thumb img { width: 100%; height: 100%; object-fit: cover; display: block; }
  .body { padding: 10px; display: flex; flex-direction: column; gap: 4px; flex: 1; }
  .price { font-weight: 700; font-size: 15px; }
  .title {
    font-size: 13px;
    line-height: 1.3;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }
  .meta { font-size: 12px; color: var(--mp-muted); margin-top: auto; }
</style>
</head>
<body>
  <div id="status">Waiting for search results…</div>
  <div id="grid"></div>
  <script>
  (function () {
    "use strict";

    var nextId = 1;
    var pending = {};

    function send(method, params) {
      window.parent.postMessage({ jsonrpc: "2.0", method: method, params: params }, "*");
    }

    function request(method, params) {
      var id = nextId++;
      return new Promise(function (resolve, reject) {
        pending[id] = { resolve: resolve, reject: reject };
        window.parent.postMessage({ jsonrpc: "2.0", id: id, method: method, params: params }, "*");
      });
    }

    function applyTheme(theme) {
      var resolved = theme === "dark" || theme === "light"
        ? theme
        : (window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
      document.documentElement.setAttribute("data-theme", resolved);
    }

    function renderCard(item) {
      var card = document.createElement("a");
      card.className = "card";
      card.href = item.url || "#";
      card.target = "_blank";
      card.rel = "noopener noreferrer";

      var thumb = document.createElement("div");
      thumb.className = "thumb";
      if (item.image) {
        var img = document.createElement("img");
        img.src = item.image;
        img.alt = "";
        img.loading = "lazy";
        img.referrerPolicy = "no-referrer";
        img.onerror = function () {
          img.remove();
          thumb.textContent = "No photo";
        };
        thumb.appendChild(img);
      } else {
        thumb.textContent = "No photo";
      }

      var body = document.createElement("div");
      body.className = "body";

      var price = document.createElement("div");
      price.className = "price";
      price.textContent = item.price || "Price on request";

      var title = document.createElement("div");
      title.className = "title";
      title.textContent = item.title || "";

      var meta = document.createElement("div");
      meta.className = "meta";
      var metaBits = [];
      if (item.city) metaBits.push(item.city);
      if (typeof item.distance_km === "number") metaBits.push(item.distance_km + " km");
      meta.textContent = metaBits.join(" · ");

      body.appendChild(price);
      body.appendChild(title);
      body.appendChild(meta);
      card.appendChild(thumb);
      card.appendChild(body);
      return card;
    }

    function render(structuredContent) {
      var listings = (structuredContent && structuredContent.listings) || [];
      var status = document.getElementById("status");
      var grid = document.getElementById("grid");
      grid.innerHTML = "";

      if (!listings.length) {
        status.textContent = "No listings in this result.";
        return;
      }
      status.textContent = listings.length + " listing" + (listings.length === 1 ? "" : "s");
      listings.forEach(function (item) {
        grid.appendChild(renderCard(item));
      });
    }

    window.addEventListener("message", function (event) {
      var data = event.data;
      if (!data || data.jsonrpc !== "2.0") return;

      if (typeof data.id !== "undefined" && (data.result || data.error)) {
        var p = pending[data.id];
        if (!p) return;
        delete pending[data.id];
        if (data.error) p.reject(new Error(data.error.message || "MCP Apps host error"));
        else p.resolve(data.result);
        return;
      }

      if (data.method === "ui/notifications/tool-result") {
        render((data.params || {}).structuredContent);
      } else if (data.method === "ui/notifications/tool-input") {
        document.getElementById("status").textContent = "Searching…";
      } else if (data.method === "ui/notifications/host-context-changed") {
        var ctx = (data.params || {}).hostContext || {};
        if (ctx.theme) applyTheme(ctx.theme);
      }
    });

    applyTheme();
    request("ui/initialize", {
      capabilities: {},
      clientInfo: { name: "marktplaats-listing-cards", version: "1.0.0" },
      protocolVersion: "2026-01-26",
    }).then(function (result) {
      applyTheme((result && result.hostContext && result.hostContext.theme) || undefined);
      send("ui/notifications/initialized", {});
    }).catch(function () {
      document.getElementById("status").textContent = "Could not connect to host.";
    });
  })();
  </script>
</body>
</html>
"""
