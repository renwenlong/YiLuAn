#!/usr/bin/env python3
"""Pick an available iPhone simulator UDID from `xcrun simctl list devices available --json`.

Stdin: JSON output of simctl list. Stdout: a single UDID.
Strategy: prefer the highest iOS runtime, prefer iPhone 16/15 family.
"""
import json
import sys


def main() -> int:
    data = json.load(sys.stdin)
    runtimes = sorted(
        [k for k in data["devices"].keys() if "iOS" in k],
        reverse=True,
    )
    preferred = [
        "iPhone 16 Pro",
        "iPhone 16",
        "iPhone 15 Pro",
        "iPhone 15",
        "iPhone 14",
    ]
    for rt in runtimes:
        devs = [d for d in data["devices"][rt] if d.get("isAvailable")]
        if not devs:
            continue
        for name in preferred:
            for d in devs:
                if d["name"] == name:
                    print(d["udid"])
                    return 0
        for d in devs:
            if d["name"].startswith("iPhone"):
                print(d["udid"])
                return 0
    print("No available iPhone simulator found", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
