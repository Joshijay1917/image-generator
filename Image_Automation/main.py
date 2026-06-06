from geminiImage import image_to_gemini
from fetchPhotos import fetch_photos
from playwright.sync_api import sync_playwright
import time
import shutil
import os

CHROME_USER_DATA   = r"C:\Users\Jay\AppData\Local\Google\Chrome\User Data"
PLAYWRIGHT_PROFILE = r"C:\Users\Jay\AppData\Local\Google\Chrome\PlaywrightProfile"
PHOTOS_DIR         = os.path.join(os.path.dirname(__file__), "photos")
IMAGE_EXTENSIONS   = {".jpg", ".jpeg", ".png", ".webp", ".gif"}

def setup_profile():
    """One-time copy of the Chrome Default profile into the Playwright profile dir."""
    dst = os.path.join(PLAYWRIGHT_PROFILE, "Default")
    if not os.path.exists(dst):
        print("First run: copying Chrome profile (one-time setup)...")
        shutil.copytree(os.path.join(CHROME_USER_DATA, "Default"), dst)
        print("Profile ready!")
    else:
        print("Using existing Playwright profile.")

def getPhotos():
    """Return the first unprocessed image path from photos/."""
    if not os.path.isdir(PHOTOS_DIR):
        return None
    
    valid_photos = sorted(
        os.path.join(PHOTOS_DIR, f)
        for f in os.listdir(PHOTOS_DIR)
        if os.path.splitext(f)[1].lower() in IMAGE_EXTENSIONS
        and not f.startswith("debug_")
        and " - done" not in f
    )
    
    return valid_photos[0] if valid_photos else None

def main():
    setup_profile()

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=PLAYWRIGHT_PROFILE,
            channel="chrome",
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--no-default-browser-check",
            ],
            ignore_default_args=["--enable-automation"],
        )

        page = context.new_page()

        try:
            photo_process = getPhotos()
            if not photo_process:
                fetch_photos(page, query="t-shirt", count=5)
                photo_process = getPhotos()
            
            if not photo_process:
                print("No new photos available to process.")
                context.close()
                return

            saved = image_to_gemini(page, image_path=photo_process, prompt="give me a new t-shirt image from this")

            if saved:
                print(f"\nDone! Generated image saved to: {saved}")
                
                # Rename the photo to mark it as done
                name, ext = os.path.splitext(photo_process)
                new_path = name + " - done" + ext
                os.rename(photo_process, new_path)
                print(f"Marked original photo as finished: {os.path.basename(new_path)}")
            else:
                print("\nGemini did not return a generated image.")
            
            page.pause()
        except Exception as e:
            print(e)

if __name__ == "__main__":
    main()