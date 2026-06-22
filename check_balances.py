"""Balance check via login — waits for manual CAPTCHA solve."""
import asyncio
import sys
sys.path.insert(0, ".")

from patchright.async_api import async_playwright

ACCOUNTS = [
    {"email": "4cniy0m9q8@rexornge.net", "password": "MmaTUm11MU!9", "label": "MAIN"},
    {"email": "5st2v8tlap@wildan.tech", "password": "Mm7E6a4itZ!9", "label": "1"},
    {"email": "e3cs9db7s9@pipmmotube.store", "password": "MmoEcP6_pV!9", "label": "2"},
    {"email": "xi362gqhwh@wintersmail.site", "password": "Mmf8VoeXMR!9", "label": "3"},
    {"email": "vreezq2t8d@mnvr.site", "password": "MmbKyX6kcz!9", "label": "4"},
    {"email": "47pv4hax6i@reestore.site", "password": "MmMILFMCr5!9", "label": "5"},
]

LOGIN_URL = "https://global.account.xiaomi.com/fe/service/login?_locale=en&source=&region=ID&sid=api-platform"


async def check_balance(pw, account):
    browser = await pw.chromium.launch(headless=False)
    context = await browser.new_context()
    page = await context.new_page()

    try:
        print(f"  [{account['label']}] Login {account['email']}...")
        await page.goto(LOGIN_URL, wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(2)

        # Accept cookies
        try:
            accept_btn = page.locator('button:has-text("Accept cookies")')
            if await accept_btn.is_visible(timeout=2000):
                await accept_btn.click()
                await asyncio.sleep(0.5)
        except Exception:
            pass

        # Fill email
        email_field = page.get_by_role('textbox', name='Email/Phone/Xiaomi Account')
        await email_field.wait_for(state='visible', timeout=10000)
        await email_field.fill(account['email'])
        await asyncio.sleep(0.5)

        # Fill password
        pw_field = page.get_by_role('textbox', name='Password')
        await pw_field.wait_for(state='visible', timeout=5000)
        await pw_field.fill(account['password'])
        await asyncio.sleep(0.5)

        # Check agreement checkbox
        checkbox = page.locator('input[type="checkbox"]').first
        if not await checkbox.is_checked():
            await checkbox.click()
            await asyncio.sleep(0.5)

        # Click sign in
        sign_in = page.locator('button:has-text("Sign in"):not(:has-text("Google")):not(:has-text("Facebook"))').first
        await sign_in.click(timeout=5000)
        print(f"  [{account['label']}] Signing in... (solve CAPTCHA kalau muncul)")

        # Wait for redirect — give 2 minutes for manual CAPTCHA solve
        try:
            await page.wait_for_url("**/platform.xiaomimimo.com/**", timeout=120000)
            print(f"  [{account['label']}] Logged in!")
        except Exception:
            current = page.url
            if 'platform' not in current:
                return {"label": account["label"], "email": account["email"], "balance": 0.0, "error": f"Login timeout: {current}"}

        # Wait a bit for session to settle
        await asyncio.sleep(2)

        # API call for balance
        result = await page.evaluate("""async () => {
            try {
                const r = await fetch('https://platform.xiaomimimo.com/api/v1/balance', {credentials: 'include'});
                if (!r.ok) return {error: r.status};
                return await r.json();
            } catch(e) {
                return {error: e.message};
            }
        }""")

        if result.get("data"):
            gift = float(result["data"].get("giftBalance", "0.00"))
            cash = float(result["data"].get("cashBalance", "0.00"))
            total = float(result["data"].get("balance", "0.00"))
            print(f"  [{account['label']}] ✓ ${total:.2f} (gift=${gift:.2f}, cash=${cash:.2f})")
            return {"label": account["label"], "email": account["email"], "balance": total, "gift": gift, "cash": cash}
        else:
            print(f"  [{account['label']}] ✗ API: {result}")
            return {"label": account["label"], "email": account["email"], "balance": 0.0, "error": str(result)}

    except Exception as e:
        err = str(e)[:120]
        print(f"  [{account['label']}] ✗ {err}")
        return {"label": account["label"], "email": account["email"], "balance": 0.0, "error": err}
    finally:
        await browser.close()


async def main():
    async with async_playwright() as pw:
        results = []
        for acc in ACCOUNTS:
            r = await check_balance(pw, acc)
            results.append(r)
            await asyncio.sleep(1)

        print("\n" + "=" * 60)
        print("  BALANCE SUMMARY")
        print("=" * 60)
        total = 0.0
        for r in results:
            bal = r.get("balance", 0.0)
            total += bal
            err = f" [{r.get('error', '')}]" if r.get("error") else ""
            print(f"  [{r['label']}] {r['email']}: ${bal:.2f}{err}")
        print(f"\n  TOTAL: ${total:.2f}")
        print("=" * 60)


asyncio.run(main())
