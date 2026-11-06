"""Local-only review UI. Intentionally no publish/send endpoint."""
from __future__ import annotations

import html
import json
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .store import connect, counts, find_posts, initialize, review
from .validators import ValidationError


STYLE = """
:root{color-scheme:light;font-family:system-ui,Segoe UI,sans-serif}
body{max-width:1000px;margin:38px auto;padding:0 20px;background:#f5f7fb;color:#16243a}
header{display:flex;justify-content:space-between;align-items:baseline;gap:20px;flex-wrap:wrap}
h1{margin:0}p{line-height:1.6}.muted{color:#60718b}.card{background:white;border:1px solid #dce3ee;
 border-radius:12px;padding:20px;margin:14px 0;box-shadow:0 2px 8px #243b5310}
.badge{display:inline-block;background:#e9eef8;padding:3px 9px;border-radius:20px;font-size:13px}
.post{white-space:pre-wrap;overflow-wrap:anywhere;background:#f7f9fc;border-radius:8px;padding:12px}
small{color:#63748d}a{color:#1759b1}button{background:#1554a4;color:white;border:0;border-radius:6px;
 padding:10px 14px;cursor:pointer}button.reject{background:#a23548}form{display:inline-block;margin:6px 6px 0 0}
.alert{border-left:4px solid #1554a4;padding:12px;background:#eaf2fb}
"""


def e(value: object) -> str:
    return html.escape(str(value), quote=True)


def serve(db_path: str, port: int) -> None:
    token = secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        def _reply(self, content: str, status: int = 200) -> None:
            data = content.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(data)

        def _redirect(self, message: str = "") -> None:
            self.send_response(303)
            self.send_header("Location", "/?message=" + ("updated" if message else ""))
            self.end_headers()

        def _host_allowed(self) -> bool:
            return self.headers.get("Host", "") in (f"127.0.0.1:{port}", f"localhost:{port}")

        def do_GET(self) -> None:
            if not self._host_allowed():
                self._reply("Forbidden host", 403)
                return
            if urlparse(self.path).path != "/":
                self._reply("Not found", 404)
                return
            with connect(db_path) as conn:
                initialize(conn)
                tally = counts(conn)
                rows = find_posts(conn, limit=200)
            cards = []
            for row in rows:
                p = json.loads(row["body"])
                source = e(p["source_url"])
                variants = "".join(f"<details><summary>Alternative {idx}</summary><p class='post'>{e(t)}</p></details>" for idx,t in enumerate(p["alt_texts"],1))
                forms = ""
                if row["status"] != "exported":
                    for choice, label, klass in [("approved", "Approve", ""), ("rejected", "Reject", "reject")]:
                        forms += (f"<form method='post' action='/review'><input type='hidden' name='csrf' value='{token}'>"
                                  f"<input type='hidden' name='id' value='{row['id']}'>"
                                  f"<input type='hidden' name='decision' value='{choice}'>"
                                  f"<button class='{klass}' type='submit'>{label}</button></form>")
                cards.append(f"""<article class='card'>
                    <span class='badge'>#{row['id']} · {e(row['status'])}</span>
                    <h2>{e(p['event_id'])} <small>({e(p['account'])} / {e(p['lang'])})</small></h2>
                    <p class='post'>{e(p['text'])}</p>{variants}
                    <p><strong>Evidence:</strong> {e(p['source_name'])} ({e(p['source_tier'])})<br>
                    <a href='{source}' target='_blank' rel='noopener noreferrer'>{source}</a></p>
                    <blockquote>{e(p['source_quote'])}</blockquote>
                    <small>Stage: {e(p['evidence_stage'])} · Priority: {e(p['priority'])} · Pillar: {e(p['pillar'])}</small>
                    <div>{forms}</div>
                    </article>""")
            message = "<div class='alert'>Review updated.</div>" if "message=updated" in self.path else ""
            body = f"""<!doctype html><html lang='en'><head><meta charset='utf-8'>
            <meta name='viewport' content='width=device-width,initial-scale=1'>
            <title>XOps Core • Human Review</title><style>{STYLE}</style></head>
            <body><header><h1>XOps Core</h1><span class='badge'>Local-only • No auto-publishing</span></header>
            <p class='muted'>Review imported PUBLIC_POSTS_V1 candidates. Approval is required before export.
            The tool does not send to X, Buffer, or email.</p>{message}
            <div class='card'><strong>Queue</strong><p>Pending {tally['pending']} · Approved {tally['approved']} ·
            Rejected {tally['rejected']} · Exported {tally['exported']}</p></div>
            {''.join(cards) if cards else '<p>No candidates. Import sample JSON using the CLI.</p>'}
            </body></html>"""
            self._reply(body)

        def do_POST(self) -> None:
            if not self._host_allowed():
                self._reply("Forbidden host", 403)
                return
            if self.path != "/review":
                self._reply("Not found", 404)
                return
            size_text = self.headers.get("Content-Length", "")
            try:
                size = int(size_text)
            except ValueError:
                self._reply("Invalid length", 400)
                return
            if not 0 < size <= 4096 or self.headers.get("Content-Type", "").split(";")[0] != "application/x-www-form-urlencoded":
                self._reply("Invalid form", 400)
                return
            try:
                values = parse_qs(self.rfile.read(size).decode("utf-8"))
                if values.get("csrf") != [token]:
                    raise ValidationError("Invalid review token")
                post_id = int(values["id"][0])
                decision = values["decision"][0]
                with connect(db_path) as conn:
                    initialize(conn)
                    review(conn, post_id, decision)
            except (ValueError, KeyError, ValidationError, UnicodeDecodeError, IndexError) as exc:
                self._reply("Invalid review request: " + e(exc), 400)
                return
            self._redirect("updated")

    with ThreadingHTTPServer(("127.0.0.1", port), Handler) as server:
        print(f"Local review page: http://127.0.0.1:{port}/")
        print("Press Ctrl+C to stop. Browser approval does NOT publish content.")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
