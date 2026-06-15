import os
from playwright.sync_api import Page
import time

OPENAI_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "openai")

def image_to_openai(page: Page, image_path: str, prompt: str):
    print('[OPENAI] Process with image!')
    os.makedirs(OPENAI_DIR, exist_ok=True)

    page.goto("https://chatgpt.com")
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
                    print(f"[openAiImage] Network capture: {len(body) // 1024} KB  ({ct})")
            except Exception:
                pass

    page.on("response", on_response)

    log_in_visible = page.locator(
        'button:has-text("Log in"), div:has-text("Sign in")'
    ).first.is_visible(timeout=2000)

    if log_in_visible:
        print("\n" + "=" * 60)
        print("[openAiImage] NOT LOGGED IN to ChatGPT.")
        print("  -> Sign in with your Google account in the browser.")
        print("  -> The script will auto-continue once login is detected.")
        print("=" * 60 + "\n")

        logged_in = False
        for _ in range(150):
            time.sleep(2)
            try:
                # Skip if still on Google sign-in pages
                if "chatgpt.com" not in page.url:
                    continue

                # The real login signal: the attachment button is visible
                prompt_ready = page.locator(
                    'button[id^="composer-plus-btn"], button[aria-label="Add files and more"], button[aria-label="Attach files"]'
                ).first.is_visible(timeout=2000)

                if prompt_ready:
                    print("[openAiImage] Login detected — chat UI is ready!")
                    time.sleep(1.5)   # let the UI fully settle
                    logged_in = True
                    break
            except Exception:
                pass

        if not logged_in:
            print("[openAiImage] Login timeout (5 min). Please run again.")
            return None
        
    page.locator('button[id^="composer-plus-btn"], button[aria-label="Add files and more"], button[aria-label="Attach files"]').first.click() 
    print("Clicked the + button!")
    time.sleep(0.8)

    UPLOAD_SELECTORS = [
        'div[role="menuitem"]:has-text("Add photos & files")',
        'div[data-radix-collection-item]:has-text("Add photos & files")',
        '[tabindex="0"]:has-text("Add photos & files")',
        '[role="menuitem"]:has-text("computer")',
        '[role="menuitem"]:has-text("Upload")',
        'button:has-text("Upload from computer")',
        'div[aria-label*="computer" i]',
        'span:has-text("Upload from computer")'
    ]

    with page.expect_file_chooser(timeout=10000) as fc_info:
        clicked = False
        for sel in UPLOAD_SELECTORS:
            try:
                item = page.locator(sel).first
                if item.is_visible(timeout=1500):
                    print(f"[openAiImage] Clicking menu item: '{sel}'")
                    item.click()
                    clicked = True
                    break
            except Exception:
                continue
        
        if not clicked:
            # Fallback to the one that worked for you just in case
            page.locator('div[role="menuitem"], div[data-radix-collection-item], [tabindex="0"]').filter(has_text="Add photos & files").first.click()
    file_chooser = fc_info.value
    file_chooser.set_files(image_path)
    time.sleep(1.5)   # wait for thumbnail preview to appear

    # find textarea and paste the prompt
    page.locator('#prompt-textarea, div[contenteditable="true"], textarea[placeholder*="Message"]').first.fill(prompt)
    time.sleep(0.5)

    print("[openAiImage] Waiting for image upload to finish...")
    send_btn = page.locator('button[data-testid="send-button"], button[aria-label="Send prompt"], button[aria-label="Send message"]').first
    
    # Wait up to 15 seconds for the send button to become active
    for _ in range(30):
        if send_btn.is_enabled() and send_btn.get_attribute("disabled") is None:
            break
        time.sleep(0.5)

    print("[openAiImage] Clicking Send button...")
    # Count only assistant messages before sending
    initial_message_count = page.locator('[data-turn="assistant"]').count()
    
    captured.clear()
    send_btn.click()

    new_message_locator = page.locator('[data-turn="assistant"]').nth(initial_message_count)
    try:
        new_message_locator.wait_for(state="attached", timeout=30000)
    except Exception:
        print("[openAiImage] Timed out waiting for ChatGPT to start a new response.")
        return None
        
    print("[openAiImage] Waiting for image generation inside new message...")
    
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
        existing = [f for f in os.listdir(OPENAI_DIR) if f.startswith("openai_tshirt")]
        return os.path.join(OPENAI_DIR, f"openai_tshirt_{len(existing) + 1}.{ext}")

    if img_src:
        if img_src.startswith("blob:"):
            try:
                img_element = new_message_locator.locator(f'img[src="{img_src}"]').first
                
                base64_data = img_element.evaluate('''img => {
                    const canvas = document.createElement("canvas");
                    canvas.width = img.naturalWidth || img.width;
                    canvas.height = img.naturalHeight || img.height;
                    const ctx = canvas.getContext("2d");
                    ctx.drawImage(img, 0, 0);
                    return canvas.toDataURL("image/jpeg", 1.0);
                }''')
                
                import base64
                header, data = base64_data.split(',', 1)
                ct = header.split(';')[0].replace('data:', '')
                ext = "png" if "png" in ct else ("webp" if "webp" in ct else "jpg")
                filepath = _next_filename(ext)
                
                with open(filepath, "wb") as f:
                    f.write(base64.b64decode(data))
                print(f"[openAiImage] Saved (canvas blob): {os.path.basename(filepath)}")
                return filepath
            except Exception as e:
                print(f"[openAiImage] Failed to extract blob image via canvas: {e}")
        else:
            resp = page.request.get(img_src)
            if resp.ok:
                ct   = resp.headers.get("content-type", "image/jpeg")
                ext  = "png" if "png" in ct else ("webp" if "webp" in ct else "jpg")
                filepath = _next_filename(ext)
                with open(filepath, "wb") as f:
                    f.write(resp.body())
                print(f"[openAiImage] Saved (http): {os.path.basename(filepath)}")
                return filepath
    else:
        print("[openAiImage] No image src found in new message")
    
    print("[openAiImage] No generated image found in ChatGPT response.")
    return None