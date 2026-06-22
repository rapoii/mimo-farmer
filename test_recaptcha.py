"""Test: can Patchright load reCAPTCHA without anti-detect patches?"""
import asyncio
from patchright.async_api import async_playwright

async def main():
    print("[1] Launching Patchright (no anti-detect patches)...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page(viewport={"width": 1920, "height": 1080})

        print("[2] Navigating to Google reCAPTCHA demo...")
        await page.goto("https://www.google.com/recaptcha/api2/demo", timeout=30000)
        await asyncio.sleep(3)

        # Check if reCAPTCHA loaded
        frames = page.frames
        recaptcha_frames = [f for f in frames if "recaptcha" in (f.url or "")]
        print(f"[3] Found {len(frames)} total frames, {len(recaptcha_frames)} reCAPTCHA frames")

        if recaptcha_frames:
            print("[OK] reCAPTCHA loaded successfully!")
        else:
            print("[FAIL] No reCAPTCHA frames found")
            # Check for error text
            body = await page.inner_text("body")
            if "cannot contact" in body.lower():
                print("[FAIL] 'Cannot contact reCAPTCHA' detected")
            print(f"    Page title: {await page.title()}")
            print(f"    Page URL: {page.url}")

        # Also try Xiaomi signup
        print("\n[4] Navigating to Xiaomi MiMo signup...")
        await page.goto("https://account.xiaomi.com/pass/signup", timeout=30000)
        await asyncio.sleep(5)

        frames2 = page.frames
        recaptcha2 = [f for f in frames2 if "recaptcha" in (f.url or "")]
        print(f"[5] Found {len(frames2)} total frames, {len(recaptcha2)} reCAPTCHA frames")

        if recaptcha2:
            print("[OK] reCAPTCHA loaded on Xiaomi!")
        else:
            body2 = await page.inner_text("body")
            if "cannot contact" in body2.lower():
                print("[FAIL] 'Cannot contact reCAPTCHA' on Xiaomi")
            elif "10025" in body2:
                print("[FAIL] Error 10025 (anti-bot)")
            else:
                print(f"[?] Page title: {await page.title()}")
                print(f"[?] URL: {page.url}")

        print("\nDone. Close browser to exit.")
        await asyncio.sleep(30)
        await browser.close()

asyncio.run(main())
