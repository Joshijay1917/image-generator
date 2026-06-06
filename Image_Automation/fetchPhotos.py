from playwright.sync_api import Page
import os
import time

# Photos saved next to this script
PHOTOS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "photos")

# Thumbnail container selectors — tried in order, first non-empty match wins
THUMB_SELECTORS = [
    'div[jsname="dTDiAc"]',
    'div[data-id][jsaction*="click"]',
    'div.eA0Zfd',
    'div.islrc > div > div',
    'div[id="islrg"] div[jsaction]',
    'div[jsaction*="mousedown"] g-img',
    'div[role="list"] div[role="listitem"]',
]

# Large preview image selectors (side panel after clicking a thumbnail)
PREVIEW_SELECTORS = [
    'img.sFlh5c',
    'img[jsname="iPVvob"]',
    'img.r48jcc',
    'img[jsname="kn3ccd"]',
]


def _find_thumbnails(page: Page):
    """Try each selector. Falls back to encrypted-tbn img elements."""
    for sel in THUMB_SELECTORS:
        try:
            items = page.locator(sel).all()
            if items:
                print(f"[fetchPhotos] Selector '{sel}' matched {len(items)} items.")
                return items, sel
        except Exception:
            continue

    # Fallback: click the thumbnail <img> elements directly
    print("[fetchPhotos] CSS selectors found nothing - trying img fallback...")
    imgs = page.locator('img[src*="encrypted-tbn"]').all()
    if imgs:
        print(f"[fetchPhotos] Found {len(imgs)} encrypted-tbn thumbnail images.")
        return imgs, 'img[src*="encrypted-tbn"]'

    return [], None


def _wait_for_preview_src(page: Page, timeout_s: float = 8.0):
    """Poll until a full-size preview image appears. Returns src or None."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        time.sleep(0.25)
        for sel in PREVIEW_SELECTORS:
            for el in page.locator(sel).all():
                src = el.get_attribute("src") or ""
                if src.startswith("https") and "encrypted-tbn" not in src:
                    return src
    return None


def fetch_photos(page: Page, query: str = "t-shirt", count: int = 5) -> int:
    """
    Search Google Images for `query` and download the first `count` full-size
    photos into photos/. Returns number of images saved.
    """
    os.makedirs(PHOTOS_DIR, exist_ok=True)

    # ── Navigate ──────────────────────────────────────────────────────────────
    print(f'\n[fetchPhotos] Searching Google Images: "{query}"')
    page.goto(f"https://www.google.com/search?q={query}&tbm=isch&hl=en")

    # Wait for the image grid container (not just domcontentloaded)
    try:
        page.wait_for_selector(
            'div#islrg, div.islrc, div[role="list"], div[jsname="dTDiAc"]',
            timeout=15000,
        )
    except Exception:
        pass  # will still try selectors and print debug info below

    time.sleep(2)  # let JS finish rendering image tiles

    # ── Debug info (helps identify consent/CAPTCHA pages) ─────────────────────
    print(f"[fetchPhotos] Page title : {page.title()}")
    print(f"[fetchPhotos] Page URL   : {page.url}")

    # Save a screenshot so you can visually inspect what Chrome opened
    screenshot_path = os.path.join(PHOTOS_DIR, "debug_google_images.png")
    page.screenshot(path=screenshot_path)
    print(f"[fetchPhotos] Screenshot : {screenshot_path}")

    # ── Find thumbnails ───────────────────────────────────────────────────────
    thumbnails, used_sel = _find_thumbnails(page)
    if not thumbnails:
        print("[fetchPhotos] ERROR: No thumbnails found on the page.")
        print("[fetchPhotos] Check the screenshot above to see what Google loaded.")
        return 0

    downloaded = 0
    index = 0

    while downloaded < count:
        if index >= len(thumbnails):
            # Scroll down to load more images, then re-query
            page.keyboard.press("End")
            time.sleep(1.5)
            thumbnails, _ = _find_thumbnails(page)
            if index >= len(thumbnails):
                print("[fetchPhotos] No more thumbnails after scrolling.")
                break

        try:
            thumbnails[index].click()
            index += 1

            img_src = _wait_for_preview_src(page)
            if not img_src:
                print(f"[fetchPhotos] Preview did not load for item {index}, skipping.")
                continue

            # Download via Playwright HTTP client (uses browser User-Agent)
            resp = page.request.get(img_src)
            if not resp.ok:
                print(f"[fetchPhotos] HTTP {resp.status} for item {index}, skipping.")
                continue

            ct  = resp.headers.get("content-type", "image/jpeg")
            ext = "webp" if "webp" in ct else ("png" if "png" in ct else "jpg")

            filename = f"{query.replace(' ', '_')}_{downloaded + 1}.{ext}"
            filepath = os.path.join(PHOTOS_DIR, filename)
            with open(filepath, "wb") as f:
                f.write(resp.body())

            print(f"[fetchPhotos] OK ({downloaded + 1}/{count}) saved -> {filename}")
            downloaded += 1

        except Exception as exc:
            print(f"[fetchPhotos] Error on item {index}: {exc}")

    print(f"[fetchPhotos] Finished - {downloaded} photo(s) saved to: {PHOTOS_DIR}\n")
    return downloaded
