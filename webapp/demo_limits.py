"""Single-process public demo limits; not a distributed abuse-prevention service."""

import asyncio
import time
from collections import deque

from starlette.responses import JSONResponse


class DemoLimits:
    def __init__(self, app, max_body=32768, requests_per_minute=12, concurrency=2):
        self.app = app
        self.max_body = max_body
        self.requests_per_minute = requests_per_minute
        self.concurrency = concurrency
        self.requests = deque()
        self.active = 0

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not (scope["path"] == "/api/chat" or scope["path"].startswith("/api/history")):
            return await self.app(scope, receive, send)
        now = time.monotonic()
        while self.requests and self.requests[0] <= now - 60:
            self.requests.popleft()
        if self.active >= self.concurrency or len(self.requests) >= self.requests_per_minute:
            response = JSONResponse({"detail": "Demo request limit reached. Please try again shortly."}, 429, headers={"Retry-After": "60"})
            return await response(scope, receive, send)
        self.requests.append(now)
        self.active += 1
        try:
            body = bytearray()
            async with asyncio.timeout(10):
                while True:
                    event = await receive()
                    if event["type"] == "http.disconnect":
                        return
                    body.extend(event.get("body", b""))
                    if len(body) > self.max_body:
                        return await JSONResponse({"detail": "Request body too large."}, 413)(scope, receive, send)
                    if not event.get("more_body"):
                        break
            delivered = False

            async def replay():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {"type": "http.request", "body": bytes(body), "more_body": False}
                return await receive()

            await self.app(scope, replay, send)
        except TimeoutError:
            await JSONResponse({"detail": "Request timed out."}, 408)(scope, receive, send)
        finally:
            self.active -= 1