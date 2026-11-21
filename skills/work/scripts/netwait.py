#!/usr/bin/env python3
import argparse
import sys
import time
import urllib.error
import urllib.request


def up(url, timeout):
    try:
        urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=timeout)
        return True
    except urllib.error.HTTPError:
        return True
    except (urllib.error.URLError, OSError):
        return False


def main():
    p = argparse.ArgumentParser(description="Wait until the model API answers again after a network drop, so a stopped workflow is resumed only when it can run.")
    p.add_argument("--url", default="https://api.anthropic.com")
    p.add_argument("--max", type=int, default=30, help="minutes to keep trying")
    p.add_argument("--every", type=int, default=20, help="seconds between tries")
    a = p.parse_args()
    start = time.time()
    tries = 0
    while True:
        tries += 1
        if up(a.url, 10):
            print(f"netwait: up after {int(time.time() - start)}s ({tries} tries)")
            return
        if time.time() - start > a.max * 60:
            print(f"netwait: still down after {a.max} min; stop and tell the owner")
            sys.exit(1)
        time.sleep(a.every)


if __name__ == "__main__":
    main()
