"""Test: Patchright WITH anti-detect patches — can it load reCAPTCHA on Xiaomi?"""
import asyncio
from patchright.async_api import async_playwright
from mimo_farmer.anti_detect import random_fingerprint, apply_stealth

async def main():
    fp = random_fingerprint()
    print(f"[1] Fingerprint: UA={fp['user_agent'][:50]}...")
    print(f"    Viewport: {fp['viewport']['width']}x{fp['viewport']['height']}")
    print(f"    Timezone: {fp['timezone']}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            viewport=fp["viewport"],
            user_agent=fp["user_agent"],
            timezone_id=fp["timezone"],
            locale=fp.get("locale", "en-US"),
        )
        page = await context.new_page()
        apply_stealth(page, fp)
        print("[2] Anti-detect patches applied")

        print("[3] Navigating to Xiaomi MiMo signup...")
        await page.goto("https://account.xiaomi.com/pass/signup", timeout=30000)
        await asyncio.sleep(5)

        frames = page.frames
        recaptcha = [f for f in frames if "recaptcha" in (f.url or "")]
        print(f"[4] Found {len(frames)} total frames, {len(recaptcha)} reCAPTCHA frames")

        if recaptcha:
            print("[OK] reCAPTCHA loaded WITH anti-detect!")
        else:
            body = await page.inner_text("body")
            if "cannot contact" in body.lower():
                print("[FAIL] 'Cannot contact reCAPTCHA' with anti-detect patches")
            elif "10025" in body:
                print("[FAIL] Error 10025 (anti-bot)")
            else:
                print(f"[?] Page title: {await page.title()}")
                print(f"[?] URL: {page.url}")
                # Print first 300 chars of body for debug
                print(f"[?] Body preview: {body[:300]}")

        # Now try reCAPTCHA demo with same patches
        print("\n[5] Navigating to reCAPTCHA demo WITH patches...")
        await page.goto("https://www.google.com/recaptcha/api2/demo", timeout=30000)
        await asyncio.sleep(3)

        frames2 = page.frames
        recaptcha2 = [f for f in frames2 if "recaptcha" in (f.url or "")]
        print(f"[6] Found {len(frames2)} total frames, {len(recaptcha2)} reCAPTCHA frames")
        if recaptcha2:
            print("[OK] reCAPTCHA demo works WITH anti-detect")
        else:
            print("[FAIL] reCAPTCHA demo broken WITH anti-detect")

        print("\nDone. Close browser to exit.")
        await asyncio.sleep(20)
        await browser.close()

asyncio.run(main())
