#!/usr/bin/env python3
"""Extract XCTAttachment PNGs from an .xcresult bundle.

Used by generate_screenshots.sh. Calls `xcrun xcresulttool` (Xcode 15+) to
walk attachments, keeps only PNGs whose `name` matches `NN_label.png`
(e.g. `01_login.png`), and writes them to --out.

Skeleton implementation — robust enough for first run; refine after first
real device pass.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

PNG_NAME = re.compile(r"^\d{2}_[a-z0-9_]+\.png$")


def xcresulttool(*args: str) -> bytes:
    cmd = ["xcrun", "xcresulttool", *args]
    return subprocess.check_output(cmd)


def get_json(xcresult: Path, ref_id: str | None = None) -> dict:
    args = ["get", "--path", str(xcresult), "--format", "json"]
    if ref_id:
        args += ["--id", ref_id]
    return json.loads(xcresulttool(*args))


def walk(node, callback):
    if isinstance(node, dict):
        callback(node)
        for v in node.values():
            walk(v, callback)
    elif isinstance(node, list):
        for v in node:
            walk(v, callback)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--xcresult", required=True, type=Path)
    p.add_argument("--out", required=True, type=Path)
    args = p.parse_args()

    if not args.xcresult.exists():
        print(f"!! xcresult not found: {args.xcresult}", file=sys.stderr)
        return 0  # don't fail the whole pipeline

    args.out.mkdir(parents=True, exist_ok=True)

    root = get_json(args.xcresult)
    found = []

    def visit(d):
        if d.get("_type", {}).get("_name") == "ActionTestAttachment":
            name = d.get("filename", {}).get("_value") or d.get("name", {}).get("_value", "")
            ref = d.get("payloadRef", {}).get("id", {}).get("_value")
            if name and ref and PNG_NAME.match(name):
                found.append((name, ref))

    walk(root, visit)
    print(f"-- found {len(found)} screenshot attachments")

    for name, ref in found:
        target = args.out / name
        try:
            data = xcresulttool("get", "--path", str(args.xcresult), "--id", ref)
            target.write_bytes(data)
            print(f"   wrote {target}")
        except subprocess.CalledProcessError as exc:
            print(f"!! failed to extract {name}: {exc}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
