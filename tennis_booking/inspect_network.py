from __future__ import annotations

import json
from pathlib import Path

from tennis_booking.config import load_config
from tennis_booking.loisirs import CheckRequest, build_search_url
from playwright.sync_api import sync_playwright


OUTPUT_PATH = Path("data/network-inspection.json")


def main() -> None:
    config = load_config()
    url = build_search_url(CheckRequest.from_config(config))
    captures = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(locale="fr-CA")

        def capture_response(response):
            request = response.request
            resource_type = request.resource_type
            content_type = response.headers.get("content-type", "")
            if resource_type not in {"xhr", "fetch"} and "json" not in content_type:
                return

            item = {
                "method": request.method,
                "url": response.url,
                "status": response.status,
                "resource_type": resource_type,
                "content_type": content_type,
                "post_data": request.post_data,
                "body_preview": "",
            }

            try:
                body = response.text()
                item["body_preview"] = body[:4000]
            except Exception as error:
                item["body_preview"] = f"<unreadable: {error}>"

            captures.append(item)

        page.on("response", capture_response)
        page.goto(url, wait_until="domcontentloaded", timeout=45_000)
        page.wait_for_load_state("networkidle", timeout=30_000)
        page.wait_for_timeout(3_000)
        browser.close()

    OUTPUT_PATH.parent.mkdir(exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(captures, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {len(captures)} network captures to {OUTPUT_PATH}")
    for item in captures:
        print(f"{item['status']} {item['method']} {item['url']}")


if __name__ == "__main__":
    main()
