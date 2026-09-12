#!/usr/bin/env python3
"""Host-side delivery sinks for the ambient channel drills.

    python3 sinks.py --http 9099 --smtp 8025 --log sinks.log

* HTTP sink: accepts any POST (the `webhook` channel's JSON envelope — the
  SMS/push-gateway shape) and appends one JSON line per request.
* SMTP sink: a minimal RFC 5321 receiver (HELO/EHLO, MAIL, RCPT, DATA, QUIT)
  that appends one JSON line per message with the envelope and the raw body.

Both bind 0.0.0.0 so containers reach them at the docker bridge gateway
(172.18.0.1 on a default compose network). Nothing here is production code.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

LOG = "sinks.log"


def record(kind: str, **fields: object) -> None:
    line = json.dumps({"kind": kind, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **fields})
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    print(line, flush=True)


class Hook(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        n = int(self.headers.get("content-length") or 0)
        raw = self.rfile.read(n).decode("utf-8", "replace")
        try:
            body: object = json.loads(raw)
        except ValueError:
            body = raw
        record("webhook", path=self.path, headers={k: v for k, v in self.headers.items() if k.lower() in ("content-type", "user-agent", "x-ambient-mode")}, body=body)
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok": true}')

    def do_GET(self) -> None:  # noqa: N802
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"sink up\n")

    def log_message(self, *args: object) -> None:
        pass


async def smtp_session(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    async def send(line: str) -> None:
        writer.write((line + "\r\n").encode())
        await writer.drain()

    await send("220 sink ESMTP")
    mail_from, rcpts, data = "", [], []
    while True:
        line = (await reader.readline()).decode("utf-8", "replace").rstrip("\r\n")
        if not line:
            break
        verb = line.split(" ", 1)[0].upper()
        if verb in ("HELO", "EHLO"):
            await send("250 sink")
        elif verb == "MAIL":
            mail_from = line.split(":", 1)[-1].strip()
            await send("250 ok")
        elif verb == "RCPT":
            rcpts.append(line.split(":", 1)[-1].strip())
            await send("250 ok")
        elif verb == "DATA":
            await send("354 end with <CRLF>.<CRLF>")
            while True:
                l2 = (await reader.readline()).decode("utf-8", "replace")
                if l2.rstrip("\r\n") == ".":
                    break
                data.append(l2)
            body = "".join(data)
            subject = next((l.split(":", 1)[1].strip() for l in data if l.lower().startswith("subject:")), "")
            record("smtp", mail_from=mail_from, rcpts=rcpts, subject=subject, size=len(body), body=body[:4000])
            data = []
            await send("250 queued")
        elif verb == "QUIT":
            await send("221 bye")
            break
        elif verb in ("RSET", "NOOP"):
            await send("250 ok")
        else:
            await send("250 ok")
    writer.close()


async def smtp_main(port: int) -> None:
    server = await asyncio.start_server(smtp_session, "0.0.0.0", port)  # noqa: S104
    async with server:
        await server.serve_forever()


def main() -> None:
    global LOG
    ap = argparse.ArgumentParser()
    ap.add_argument("--http", type=int, default=9099)
    ap.add_argument("--smtp", type=int, default=8025)
    ap.add_argument("--log", default=LOG)
    a = ap.parse_args()
    LOG = a.log
    httpd = ThreadingHTTPServer(("0.0.0.0", a.http), Hook)  # noqa: S104
    Thread(target=httpd.serve_forever, daemon=True).start()
    print(f"sinks: http :{a.http}  smtp :{a.smtp}  log {LOG}", flush=True)
    asyncio.run(smtp_main(a.smtp))


if __name__ == "__main__":
    main()
