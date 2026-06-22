"""Login test with Patchright + anti-detection."""
import asyncio
import sys
sys.path.insert(0, ".")

from patchright.async_api import async_playwright

LOGIN_URL = "https://global.account.xiaomi.com/fe/service/login?_locale=en&source=&region=ID&sid=api-platform"


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-features=IsolateOrigins,site-per-process',
                '--no-first-run',
                '--no-default-browser-check',
            ],
        )
        context = await browser.new_context(
            viewport={"width": 1366, "height": 768},
            locale="en-US",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
            timezone_id="America/New_York",
        )
        page = await context.new_page()

        # Anti-detection JS
        await page.evaluate("""() => {
            Object.defineProperty(navigator, 'webdriver', {get: () => false});
            Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
            Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
            window.chrome = {runtime: {}};
        }""")

        print("[1] Navigate to login...")
        await page.goto(LOGIN_URL, wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(2)

        # Accept cookies
        try:
            btn = page.locator('button:has-text("Accept cookies")')
            if await btn.is_visible(timeout=2000):
                await btn.click()
                await asyncio.sleep(0.5)
        except Exception:
            pass

        print("[2] Fill email...")
        email = page.get_by_role('textbox', name='Email/Phone/Xiaomi Account')
        await email.wait_for(state='visible', timeout=10000)
        await email.fill('4cniy0m9q8@rexornge.net')
        await asyncio.sleep(0.3)

        print("[3] Fill password...")
        pw = page.get_by_role('textbox', name='Password')
        await pw.fill('MmaTUm11MU!9')
        await asyncio.sleep(0.3)

        print("[4] Check agreement...")
        cb = page.locator('input[type="checkbox"]').first
        if not await cb.is_checked():
            await cb.click()
            await asyncio.sleep(0.3)

        print("[5] Click Sign in...")
        btn = page.locator('button:has-text("Sign in"):not(:has-text("Google")):not(:has-text("Facebook"))').first
        await btn.click()
        await asyncio.sleep(5)

        url = page.url
        print(f"[6] URL: {url}")

        # Check if actually redirected to platform (not just 'platform' substring)
        if 'platform.xiaomimimo.com' in url:
            print("[✓] Login success! Checking balance...")
            result = await page.evaluate("""async () => {
                const r = await fetch('https://platform.xiaomimimo.com/api/v1/balance', {credentials: 'include'});
                return r.ok ? await r.json() : {error: r.status};
            }""")
            print(f"[✓] Balance: {result}")
        else:
            # Still on login page — check why
            body = await page.evaluate("document.body?.innerText || ''")
            if '10025' in body:
                print("[✗] Error :10025 — IP blocked by Xiaomi")
            elif 'automated' in body.lower():
                print("[✗] reCAPTCHA automated queries detected")
            elif 'incorrect' in body.lower() or 'wrong' in body.lower():
                print("[✗] Wrong password or account issue")
            else:
                # Check for reCAPTCHA
                frames = page.frames
                recaptcha = [f for f in frames if 'recaptcha' in f.url]
                if recaptcha:
                    print("[!] reCAPTCHA detected — solve manually in browser (120s timeout)...")
                    try:
                        await page.wait_for_url("**/platform.xiaomimimo.com/**", timeout=120000)
                        print("[✓] Login success after CAPTCHA!")
                    except Exception:
                        print("[✗] Login timeout after 120s")
                else:
                    print(f"[?] Unknown. Page text: {body[:300]}")

        await browser.close()

asyncio.run(main())
