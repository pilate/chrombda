import asyncio
import hashlib
import json
import logging
import os
import re
import shutil
from datetime import datetime, timezone
from urllib.parse import urlparse

import boto3
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

S3 = boto3.client("s3")
BUCKET = os.environ["BUCKET"]

CHROME_ARGS = [
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--no-zygote",
    "--single-process",
    "--window-size=1920,1080",
]


async def take_screenshot(url: str) -> bytes:
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
        await cdit.Page.navigate(url=url)

        try:
            await cdit.wait_for("Page.loadEventFired", 15)
        except asyncio.TimeoutError:
            LOGGER.warning("Page load event did not fire within 15s for %s", url)

        response = await cdit.Page.captureScreenshot(format="png")
        return base64.b64decode(response["data"])
    finally:
        del chrome


def s3_key_for(url: str) -> str:
    domain = urlparse(url).netloc or "unknown"
    clean_domain = re.sub(r"[^a-zA-Z0-9-]", "-", domain)
    url_hash = hashlib.sha256(url.encode()).hexdigest()[:12]
    now = datetime.now(timezone.utc)
    return f"screenshots/{clean_domain}/{url_hash}/{now:%Y%m%d-%H%M%S}.png"


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
    LOGGER.info("Event: %s", json.dumps(event, default=str))

    url = extract_url(event)
    if not url:
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "Missing required parameter: url"}),
        }

    screenshot_bytes = asyncio.run(take_screenshot(url))
    key = s3_key_for(url)
    S3.put_object(
        Bucket=BUCKET, Key=key, Body=screenshot_bytes, ContentType="image/png"
    )
    LOGGER.info("Saved to s3://%s/%s", BUCKET, key)

    return {"statusCode": 200, "body": json.dumps({"key": key})}
