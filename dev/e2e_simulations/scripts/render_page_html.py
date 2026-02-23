#!/usr/bin/env python3

import argparse
import os

from playwright.sync_api import sync_playwright


def main() -> int:
    parser = argparse.ArgumentParser(description="Render a page with Playwright and dump HTML.")
    parser.add_argument("url", help="URL to open")
    parser.add_argument(
        "--output",
        default=os.path.join(os.getcwd(), "artifacts", "rendered_page.html"),
        help="Path to write HTML output",
    )
    parser.add_argument(
        "--wait",
        default="domcontentloaded",
        choices=["load", "domcontentloaded", "networkidle"],
        help="Wait condition before dumping HTML",
    )
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.output), exist_ok=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(args.url, wait_until=args.wait)
        html = page.content()
        browser.close()

    with open(args.output, "w", encoding="utf-8") as handle:
        handle.write(html)

    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
