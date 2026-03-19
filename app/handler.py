import asyncio
import hashlib
import json
import logging
import os
import re
import shutil
import time
from datetime import datetime, timezone
from urllib.parse import urlparse

import aiobotocore.session
import pybase64 as base64

# Chrome needs a writable HOME for .local, .config, etc.
os.environ.setdefault("HOME", "/tmp")

# Copy baked-in cdipy protocol cache to writable /tmp before importing cdipy
_CACHE_SRC = "/var/task/cdipy-cache"
_CACHE_DST = os.environ.get("CDIPY_CACHE", "/tmp/cdipy-cache")
if os.path.isdir(_CACHE_SRC) and not os.path.isdir(_CACHE_DST):
    shutil.copytree(_CACHE_SRC, _CACHE_DST, copy_function=shutil.copy)

from cdipy import ChromeDevTools, ChromeDevToolsTarget, ChromeRunner


LOGGER = logging.getLogger()
LOGGER.setLevel(logging.INFO)

BUCKET = os.environ["BUCKET"]

_BOTO_SESSION = aiobotocore.session.get_session()
_LOOP = asyncio.new_event_loop()
_S3_CLIENT = None


async def get_s3():
    global _S3_CLIENT
    if _S3_CLIENT is None:
        _S3_CLIENT = await _BOTO_SESSION.create_client("s3").__aenter__()
    return _S3_CLIENT

CHROME_ARGS = [
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--no-zygote",
    "--single-process",
    "--window-size=1920,1080",
]


async def crawl(url: str) -> tuple[bytes, str]:
    """Take a screenshot and capture MHTML snapshot. Returns (png_bytes, mhtml_str)."""
    chrome = ChromeRunner(ignore_cleanup_errors=True)
    try:
        await chrome.launch(extra_args=CHROME_ARGS)
        LOGGER.info("Chrome started, ws: %s", chrome.websocket_uri)

        cdi = ChromeDevTools(chrome.websocket_uri)
        await cdi.connect()

        target = await cdi.Target.createTarget(url="about:blank")
        session = await cdi.Target.attachToTarget(
            targetId=target["targetId"], flatten=True
        )
        cdit = ChromeDevToolsTarget(cdi, session["sessionId"])

        await cdit.Page.enable()
        await cdit.Network.enable()
        await cdit.Page.navigate(url=url)

        try:
            await cdit.wait_for("Page.loadEventFired", 10)
        except asyncio.TimeoutError:
            LOGGER.warning("Page load event did not fire within 15s for %s", url)

        # Let async content settle
        await asyncio.sleep(5)

        screenshot_resp, snapshot_resp = await asyncio.gather(
            cdit.Page.captureScreenshot(format="png"),
            cdit.Page.captureSnapshot(format="mhtml"),
        )

        png_bytes = base64.b64decode(screenshot_resp["data"])
        mhtml_str = snapshot_resp["data"]

        return png_bytes, mhtml_str
    finally:
        del chrome


async def upload(png_bytes: bytes, mhtml_str: str, base: str, ts: str):
    """Upload screenshot and snapshot to S3 concurrently."""
    s3 = await get_s3()
    await asyncio.gather(
        s3.put_object(
            Bucket=BUCKET,
            Key=f"screenshots/{base}/{ts}.png",
            Body=png_bytes,
            ContentType="image/png",
        ),
        s3.put_object(
            Bucket=BUCKET,
            Key=f"snapshots/{base}/{ts}.mhtml",
            Body=mhtml_str.encode(),
            ContentType="multipart/related",
        ),
    )


def s3_key_parts(url: str) -> tuple[str, str]:
    """Returns (path_base, timestamp) for constructing S3 keys."""
    domain = urlparse(url).netloc or "unknown"
    clean_domain = re.sub(r"[^a-zA-Z0-9-]", "-", domain)
    url_hash = hashlib.sha256(url.encode()).hexdigest()[:12]
    now = datetime.now(timezone.utc)
    return f"{clean_domain}/{url_hash}", f"{now:%Y%m%d-%H%M%S}"


def extract_url(event: dict) -> str | None:
    # CloudWatch scheduled event
    if event.get("source") == "aws.events":
        return event.get("detail", {}).get("url")

    # Lambda Function URL: query string or JSON body
    qs = event.get("queryStringParameters") or {}
    if "url" in qs:
        return qs["url"]

    if event.get("body"):
        body = event["body"]
        if event.get("isBase64Encoded"):
            body = base64.b64decode(body).decode()
        try:
            return json.loads(body).get("url")
        except (json.JSONDecodeError, AttributeError):
            pass

    return None


def lambda_handler(event, context):
    url = extract_url(event)
    if not url:
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "Missing required parameter"}),
        }

    async def run():
        t0 = time.monotonic()
        png_bytes, mhtml_str = await crawl(url)
        crawl_time = time.monotonic() - t0
        base, ts = s3_key_parts(url)
        await upload(png_bytes, mhtml_str, base, ts)
        return base, ts, crawl_time

    base, ts, crawl_time = _LOOP.run_until_complete(run())
    LOGGER.info("Crawled %s in %.1fs", url, crawl_time)

    return {
        "statusCode": 200,
        "body": json.dumps({
            "screenshot": f"screenshots/{base}/{ts}.png",
            "snapshot": f"snapshots/{base}/{ts}.mhtml",
            "crawl_time": round(crawl_time, 2),
        }),
    }
