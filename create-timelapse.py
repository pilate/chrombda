#!/usr/bin/env python3

"""Generate a timelapse video from screenshots stored in S3."""

import argparse
import hashlib
import os
import re
import subprocess
import sys
import tempfile
from urllib.parse import urlparse

import boto3


def s3_prefix_for(url: str) -> str:
    domain = urlparse(url).netloc or "unknown"
    clean_domain = re.sub(r"[^a-zA-Z0-9-]", "-", domain)
    url_hash = hashlib.sha256(url.encode()).hexdigest()[:12]
    return f"screenshots/{clean_domain}/{url_hash}/"


def main():
    parser = argparse.ArgumentParser(description="Generate timelapse from S3 screenshots")
    parser.add_argument("environment", choices=["dev", "staging", "prod"])
    parser.add_argument("url", help="URL to generate timelapse for")
    parser.add_argument("-o", "--output", default="timelapse.mp4", help="Output file (default: timelapse.mp4)")
    parser.add_argument("--fps", type=int, default=4, help="Frames per second (default: 2)")
    args = parser.parse_args()

    account_id = boto3.client("sts").get_caller_identity()["Account"]
    bucket = f"chrombda-{args.environment}-{account_id}"
    prefix = s3_prefix_for(args.url)

    print(f"Listing s3://{bucket}/{prefix}")
    s3 = boto3.client("s3")
    paginator = s3.get_paginator("list_objects_v2")
    keys = []
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            if obj["Key"].endswith(".png"):
                keys.append(obj["Key"])

    keys.sort()

    if not keys:
        print("No screenshots found.")
        sys.exit(1)

    print(f"Found {len(keys)} screenshots")

    with tempfile.TemporaryDirectory() as tmpdir:
        for i, key in enumerate(keys):
            dest = os.path.join(tmpdir, f"frame_{i:06d}.png")
            print(f"  Downloading {key}", end="\r")
            s3.download_file(bucket, key, dest)
        print()

        cmd = [
            "ffmpeg", "-y",
            "-framerate", str(args.fps),
            "-i", os.path.join(tmpdir, "frame_%06d.png"),
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            args.output,
        ]
        print(f"Encoding {args.output} at {args.fps} fps...")
        subprocess.run(cmd, check=True)

    print(f"Done: {args.output}")


if __name__ == "__main__":
    main()
