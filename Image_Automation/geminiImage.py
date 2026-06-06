import os
from playwright.sync_api import Page
import time

GEMINI_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gemini")

def image_to_gemini(page: Page, image_path: str, prompt: str):
    print('Process with image!')
    os.makedirs(GEMINI_DIR, exist_ok=True)

    page.goto("https://gemini.google.com/")
    page.wait_for_load_state("domcontentloaded")
    time.sleep(3)

    captured = []

    def on_response(response):
        ct = response.headers.get("content-type", "")
        if response.ok and ct.startswith("image/"):
            try:
                body = response.body()
                if len(body) > 30_000:          # skip small UI icons (< 30 KB)
                    captured.append((body, ct))
                    print(f"[geminiImage] Network capture: {len(body) // 1024} KB  ({ct})")
            except Exception:
                pass

    page.on("response", on_response)

    sign_in_visible = page.locator(
        'button:has-text("Sign in"), a:has-text("Sign in")'
    ).first.is_visible(timeout=2000)

    if sign_in_visible:
        print("\n" + "=" * 60)
        print("[geminiImage] NOT LOGGED IN to Gemini.")
        print("  -> Sign in with your Google account in the browser.")
        print("  -> The script will auto-continue once login is detected.")
        print("=" * 60 + "\n")

        logged_in = False
        for _ in range(150):          # up to 5 minutes
            time.sleep(2)
            try:
                # Skip if still on Google sign-in pages
                if "gemini.google.com" not in page.url:
                    continue

                # The real login signal: the chat prompt area is visible
                prompt_ready = page.locator(
                    'button:has-text("Sign in"), a:has-text("Sign in")'
                ).first.is_visible(timeout=2000)

                if not prompt_ready:
                    print("[geminiImage] Login detected — chat UI is ready!")
                    time.sleep(1.5)   # let the UI fully settle
                    logged_in = True
                    break
            except Exception:
                pass

        if not logged_in:
            print("[geminiImage] Login timeout (5 min). Please run again.")
            return None

    page.locator('button:has(mat-icon[data-mat-icon-name="plus"])').first.click()
    print("Clicked the + button!")
    time.sleep(0.8)

    UPLOAD_FROM_COMPUTER_SELECTORS = [
        '[role="menuitem"]:has-text("computer")',
        '[role="menuitem"]:has-text("Upload")',
        '[role="option"]:has-text("Upload")',
        '[role="listitem"]:has-text("Upload")',
        'li:has-text("Upload")',
        'button:has-text("Upload from computer")',
        'div[aria-label*="computer" i]',
        'span:has-text("Upload from computer")',
    ]

    with page.expect_file_chooser(timeout=10000) as fc_info:
        for sel in UPLOAD_FROM_COMPUTER_SELECTORS:
            try:
                item = page.locator(sel).first
                if item.is_visible(timeout=1500):
                    print(f"[geminiImage] Clicking menu item: '{sel}'")
                    item.click()
                    break
            except Exception:
                continue

    file_chooser = fc_info.value
    file_chooser.set_files(image_path)
    time.sleep(1.5)   # wait for thumbnail preview to appear

    initial_message_count = page.locator("model-response, message-content, .response-container, structured-content-container").count()

    page.locator('div[role="textbox"], div[data-placeholder="Ask Gemini"]').first.fill(prompt)
    time.sleep(0.5)

    print("[geminiImage] Waiting for image upload to finish...")
    send_btn = page.locator('button[aria-label="Send message"], button[aria-label="Send"]').first
    
    # Wait up to 15 seconds for the send button to become active
    for _ in range(30):
        if send_btn.is_enabled() and send_btn.get_attribute("aria-disabled") != "true":
            break
        time.sleep(0.5)

    print("[geminiImage] Clicking Send button...")
    send_btn.click()

    new_message_locator = page.locator("model-response, message-content, .response-container, structured-content-container").nth(initial_message_count)
    try:
        new_message_locator.wait_for(state="attached", timeout=30000)
    except Exception:
        print("[geminiImage] Timed out waiting for Gemini to start a new response.")
        return None
    
    img_src = None
    for _ in range(60):   # wait up to 90 seconds
        time.sleep(1.5)
        
        candidates = new_message_locator.locator("img").all()
        for el in candidates:
            src = el.get_attribute("src") or ""
            if not src.startswith("http") and not src.startswith("blob:"):
                continue
            try:
                box = el.bounding_box()
                # A real generated image will be large, not a small UI icon
                if box and box["width"] > 100 and box["height"] > 100:
                    img_src = src
                    break
            except Exception:
                pass
                
        if img_src:
            break
    
    def _next_filename(ext: str) -> str:
        existing = [f for f in os.listdir(GEMINI_DIR) if f.startswith("gemini_tshirt")]
        return os.path.join(GEMINI_DIR, f"gemini_tshirt_{len(existing) + 1}.{ext}")

    if img_src:
        if img_src.startswith("blob:"):
            try:
                img_element = new_message_locator.locator(f'img[src="{img_src}"]').first
                
                base64_data = img_element.evaluate('''img => {
                    // Create a canvas with the same dimensions as the image
                    const canvas = document.createElement("canvas");
                    canvas.width = img.naturalWidth || img.width;
                    canvas.height = img.naturalHeight || img.height;
                    
                    // Draw the image onto the canvas
                    const ctx = canvas.getContext("2d");
                    ctx.drawImage(img, 0, 0);
                    
                    // Export canvas to base64 JPEG
                    return canvas.toDataURL("image/jpeg", 1.0);
                }''')
                
                import base64
                # base64_data format: "data:image/jpeg;base64,/9j/4AAQSk..."
                header, data = base64_data.split(',', 1)
                ct = header.split(';')[0].replace('data:', '')
                ext = "png" if "png" in ct else ("webp" if "webp" in ct else "jpg")
                filepath = _next_filename(ext)
                
                with open(filepath, "wb") as f:
                    f.write(base64.b64decode(data))
                print(f"[geminiImage] Saved (canvas blob): {os.path.basename(filepath)}")
                return filepath
            except Exception as e:
                print(f"[geminiImage] Failed to extract blob image via canvas: {e}")
        else:
            resp = page.request.get(img_src)
            if resp.ok:
                ct   = resp.headers.get("content-type", "image/jpeg")
                ext  = "png" if "png" in ct else ("webp" if "webp" in ct else "jpg")
                filepath = _next_filename(ext)
                with open(filepath, "wb") as f:
                    f.write(resp.body())
                print(f"[geminiImage] Saved (http): {os.path.basename(filepath)}")
                return filepath
    else:
        print("[geminiImage] No image src found")
    
    print("[geminiImage] No generated image found in Gemini response.")
    return None