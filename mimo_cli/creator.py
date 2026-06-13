"""Core MiMo account creation pipeline.

PROVEN WORKING (2026-06-13):
  Patchright browser → fill signup → solve reCAPTCHA audio → OTP from temp email
  → enter OTP → Terms dialog (ant-modal) → referral code → verify balance
  → create API key → save credentials.

CRITICAL patterns preserved:
  - domcontentloaded (NOT networkidle — causes timeout on MiMo SPA)
  - Terms dialog: .ant-modal:has-text('Terms') → checkbox → Confirm button
  - Referral: 6-char OTP input fields via page.get_by_role('textbox')
  - API key: input[disabled] value extraction
  - Balance regex: r'Balance\s*\$\s*([\d.]+)'
"""

import asyncio
import json
import os
import re
import time

from patchright.async_api import async_playwright

from mimo_cli.config import (
    DEFAULT_PASSWORD, DEFAULT_REFERRAL_CODE, SIGNUP_URL,
    BALANCE_URL, API_KEYS_URL, LOGOUT_URL, ACCOUNTS_DIR,
    HUMAN_DELAY_MIN_MS, HUMAN_DELAY_MAX_MS,
    FAST_DELAY_MIN_MS, FAST_DELAY_MAX_MS, FAST_MODE_MULTIPLIER,
)
from mimo_cli.captcha import solve_recaptcha
from mimo_cli.email_handler import random_email, wait_for_otp


class Timer:
    """Simple phase timer for performance tracking."""

    def __init__(self):
        self._start = time.time()
        self._phases: list[tuple[str, float]] = []

    def phase(self, name: str):
        now = time.time()
        elapsed = now - self._start
        self._phases.append((name, elapsed))
        print(f"  * {name}: {elapsed:.1f}s")
        self._start = now

    def summary(self) -> str:
        total = sum(t for _, t in self._phases)
        lines = [f"  TOTAL: {total:.1f}s"]
        for name, t in self._phases:
            lines.append(f"    {name}: {t:.1f}s")
        return "\n".join(lines)

    @property
    def total(self) -> float:
        return sum(t for _, t in self._phases)


async def human_delay(min_ms: int = None, max_ms: int = None, fast: bool = False):
    """Random delay with optional fast-mode reduction."""
    if min_ms is None:
        min_ms = FAST_DELAY_MIN_MS if fast else HUMAN_DELAY_MIN_MS
    if max_ms is None:
        max_ms = FAST_DELAY_MAX_MS if fast else HUMAN_DELAY_MAX_MS
    if fast:
        min_ms = max(50, min_ms // 3)
        max_ms = max(100, max_ms // 3)
    await asyncio.sleep(min_ms / 1000 + (max_ms - min_ms) / 1000 * __import__('random').random())


async def smart_sleep(seconds: float, fast: bool = False):
    """Sleep with fast-mode reduction."""
    if fast:
        await asyncio.sleep(seconds * FAST_MODE_MULTIPLIER)
    else:
        await asyncio.sleep(seconds)


async def handle_dialogs(page, fast: bool = False):
    """Handle cookie banners, terms popups, skip buttons."""
    for _ in range(3):
        handled = False

        # Cookie banner
        try:
            cookie_btn = page.get_by_role('button', name='Accept All')
            if await cookie_btn.count() > 0:
                await cookie_btn.first.click()
                await human_delay(200, 400, fast)
                handled = True
        except Exception:
            pass

        # Terms/Agreement dialog — checkbox + Confirm
        try:
            cb = page.locator('[role="dialog"] [role="checkbox"]')
            if await cb.count() > 0:
                await cb.first.click()
                await human_delay(200, 400, fast)
                confirm = page.get_by_role('button', name='Confirm')
                if await confirm.count() > 0:
                    await confirm.first.click()
                    await human_delay(300, 600, fast)
                    handled = True
        except Exception:
            pass

        # Close button (X)
        try:
            close_btn = page.locator(
                'button[aria-label="Close"], button:has-text("×"), .ant-modal-close'
            )
            if await close_btn.count() > 0:
                await close_btn.first.click()
                await human_delay(200, 400, fast)
                handled = True
        except Exception:
            pass

        # Skip/Dismiss buttons
        try:
            skip = page.get_by_role(
                'button', name=re.compile('Maybe later|Skip|Not now|Dismiss', re.I)
            )
            if await skip.count() > 0:
                await skip.first.click()
                await human_delay(200, 400, fast)
                handled = True
        except Exception:
            pass

        if not handled:
            break
        await asyncio.sleep(0.3)


async def handle_terms_dialog(page, fast: bool = False):
    """Handle the Terms modal specifically (ant-modal pattern).

    CRITICAL: .ant-modal:has-text('Terms') → input[type='checkbox'] → button:has-text('Confirm')
    """
    for attempt in range(5):
        # Check if ant-modal with Terms is visible
        modal = page.locator('.ant-modal:has-text("Terms")')
        modal_count = await modal.count()

        if modal_count > 0:
            print(f"  Found Terms modal (attempt {attempt + 1})")

            # Click checkbox inside the modal
            checkbox = modal.locator('input[type="checkbox"]')
            cb_count = await checkbox.count()
            if cb_count > 0:
                await checkbox.first.click(force=True)
                await asyncio.sleep(0.8)
                print("  Checkbox clicked!")

            # Click Confirm button
            confirm = modal.locator('button:has-text("Confirm")')
            conf_count = await confirm.count()
            if conf_count > 0:
                await confirm.first.click(force=True)
                await asyncio.sleep(1.5)
                print("  Confirm clicked!")
                return True

        # Fallback: any visible checkbox + Confirm button
        try:
            cb = page.locator('input[type="checkbox"]:visible')
            if await cb.count() > 0:
                await cb.first.click(force=True)
                await asyncio.sleep(0.8)
                btn = page.locator('button:has-text("Confirm"):visible')
                if await btn.count() > 0:
                    await btn.first.click(force=True)
                    await asyncio.sleep(1.5)
                    print("  Fallback: checkbox + Confirm clicked!")
                    return True
        except Exception:
            pass

        await asyncio.sleep(1.5)

    print("  [!] Terms dialog NOT handled!")
    return False


async def enter_referral(page, referral_code: str, fast: bool = False):
    """Enter referral code using 6-char OTP input fields.

    CRITICAL: Uses page.get_by_role('textbox') for the 6 individual input fields.
    """
    print(f"  Entering referral: {referral_code}")
    try:
        invite_btn = page.get_by_role(
            'button', name=re.compile('invite|referral|Enter invite', re.I)
        )
        try:
            count = await invite_btn.count()
        except Exception:
            count = 0

        if count > 0:
            await invite_btn.first.click()
            await asyncio.sleep(1.5)

            otp_fields = page.get_by_role(
                'textbox', name=re.compile('OTP Input|Input', re.I)
            )
            count = await otp_fields.count()

            if count >= 6:
                for i, char in enumerate(referral_code):
                    await otp_fields.nth(i).fill(char)
                    await human_delay(50, 150, fast)
                await human_delay(300, 600, fast)

                await page.get_by_role(
                    'button', name=re.compile('Redeem|Submit|Bind', re.I)
                ).click()
                await asyncio.sleep(2)
                print("  Referral submitted!")
            else:
                print(f"  [!] Expected 6 OTP fields, found {count}")
        else:
            print("  [!] Invite button not found")
    except Exception as e:
        print(f"  [!] Referral error: {e}")


async def extract_balance(page) -> str:
    """Extract balance from page text.

    CRITICAL: Uses regex r'Balance\\s*\\$\\s*([\\d.]+)'
    """
    await page.goto(BALANCE_URL, wait_until='domcontentloaded')
    await asyncio.sleep(2)

    balance = "$0.00"
    try:
        body = await page.evaluate("document.body.innerText")
        m = re.search(r'Balance\s*\$\s*([\d.]+)', body)
        if m:
            balance = f"${m.group(1)}"
        else:
            m = re.search(r'\$([\d.]+)', body)
            if m:
                balance = f"${m.group(1)}"
    except Exception:
        pass

    return balance


async def create_api_key(page, label: str, fast: bool = False) -> str | None:
    """Create and extract API key.

    CRITICAL: Extracts from input[disabled] value.
    """
    print("  Creating API key...")
    await page.goto(API_KEYS_URL, wait_until='domcontentloaded')
    await asyncio.sleep(3)
    await handle_dialogs(page, fast)
    await asyncio.sleep(1)

    try:
        # Wait for page content
        try:
            await page.wait_for_selector('button', timeout=10000)
        except Exception:
            pass

        # Find create button
        create_btn = None
        for btn_text in ['Create API Key', 'Create New', 'Create', 'Add']:
            try:
                btn = page.get_by_role('button', name=re.compile(btn_text, re.I))
                if await btn.count() > 0:
                    create_btn = btn.first
                    break
            except Exception:
                continue

        if not create_btn:
            buttons = await page.evaluate("""
                () => Array.from(document.querySelectorAll('button')).map(b => b.textContent.trim())
            """)
            for btn in buttons:
                if 'create' in btn.lower():
                    create_btn = page.get_by_role('button', name=btn)
                    break

        if create_btn:
            await create_btn.click(timeout=5000)
            await asyncio.sleep(2)

            # Fill key name
            name_filled = False
            for name_pattern in ['API Key Name', 'Key Name', 'Name', 'Description']:
                try:
                    name_input = page.get_by_role(
                        'textbox', name=re.compile(name_pattern, re.I)
                    )
                    if await name_input.count() > 0:
                        await name_input.first.fill(label)
                        name_filled = True
                        break
                except Exception:
                    continue

            if not name_filled:
                try:
                    await page.locator(
                        'input[placeholder*="name" i], input[placeholder*="key" i]'
                    ).first.fill(label)
                except Exception:
                    pass

            await asyncio.sleep(0.5)

            # Confirm
            await page.get_by_role('button', name='Confirm').click(timeout=5000)

            # Wait for key to appear in disabled input
            try:
                await page.locator('input[disabled]').first.wait_for(
                    state='visible', timeout=8000
                )
            except Exception:
                await asyncio.sleep(2)

            # CRITICAL: Extract from input[disabled] value
            api_key = await page.evaluate(
                "document.querySelector('input[disabled]')?.value || null"
            )

            if api_key:
                print(f"  API Key: {api_key[:10]}...{api_key[-5:]}")
            else:
                print("  [!] Could not extract API key")
            return api_key
        else:
            print("  [!] No Create button found")
    except Exception as e:
        print(f"  [!] API key error: {e}")

    return None


async def create_account(
    referral_code: str = DEFAULT_REFERRAL_CODE,
    password: str = DEFAULT_PASSWORD,
    fast: bool = False,
) -> dict | None:
    """Full MiMo account creation pipeline.

    Steps:
    1. Launch Patchright browser (anti-detect Playwright)
    2. Navigate to signup URL with referral code
    3. Fill email + password form
    4. Submit and solve reCAPTCHA v2 (audio challenge)
    5. Get OTP from temp email (generator.email)
    6. Enter OTP
    7. Handle Terms dialog (ant-modal)
    8. Enter referral code
    9. Verify balance ($2.72 expected)
    10. Create API key
    11. Save credentials

    Args:
        referral_code: 6-char MiMo referral code
        password: Account password
        fast: Enable fast mode (reduced delays)

    Returns:
        Dict with credentials or None on failure
    """
    email, user, domain = random_email()
    account_num = int(time.time()) % 1000
    timer = Timer()

    mode_label = "FAST" if fast else "NORMAL"
    print("=" * 60)
    print(f"  MiMo Account Creator — Mode: {mode_label}")
    print("=" * 60)
    print(f"  Email: {email}")
    print(f"  Referral: {referral_code}")
    print()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=['--disable-blink-features=AutomationControlled']
        )
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 800},
            locale='en-US',
        )
        page = await context.new_page()

        # Phase 1: Navigate to signup
        print("[1] Navigating to signup...")
        signup_url = f"{SIGNUP_URL}{referral_code}"
        await page.goto(signup_url, wait_until='domcontentloaded')

        # Click "Sign up" tab
        try:
            signup_tab = page.locator('text="Sign up"').first
            if await signup_tab.is_visible(timeout=5000):
                await signup_tab.click()
                await page.wait_for_load_state('domcontentloaded', timeout=10000)
            else:
                await page.get_by_role('button', name='Sign up').click(timeout=3000)
                await page.wait_for_load_state('domcontentloaded', timeout=10000)
        except Exception as e:
            print(f"  [!] Sign up tab issue: {e}")
        timer.phase("Navigate + signup tab")

        # Phase 2: Fill form
        print("[2] Filling form...")
        try:
            email_field = page.get_by_role('textbox', name='Email')
            await email_field.wait_for(state='visible', timeout=15000)
            await email_field.fill(email)
            await human_delay(150, 350, fast)

            pw_field = page.get_by_role('textbox', name='Enter your new password')
            await pw_field.wait_for(state='visible', timeout=5000)
            await pw_field.fill(password)
            await human_delay(150, 350, fast)

            confirm_field = page.get_by_role('textbox', name='Confirm new password')
            await confirm_field.fill(password)
            await human_delay(150, 350, fast)

            await page.get_by_role('checkbox', name="I've read and agreed").click()
            await human_delay(300, 600, fast)
            print("  Form filled")
        except Exception as e:
            print(f"  [!] Form fill error: {e}")
            await browser.close()
            return None
        timer.phase("Fill form")

        # Phase 3: Submit + reCAPTCHA
        print("[3] Clicking Next + solving reCAPTCHA...")
        try:
            await page.get_by_role('button', name='Next').click(timeout=5000)
        except Exception:
            try:
                await page.locator('button[type="submit"]').click(timeout=3000)
            except Exception:
                pass

        captcha_ok = await solve_recaptcha(page)
        if not captcha_ok:
            print("[X] reCAPTCHA failed!")
            await browser.close()
            return None
        timer.phase("reCAPTCHA solve")

        # Phase 4: OTP
        print("[4] Waiting for OTP page...")
        try:
            await page.locator(
                'input[type="text"], input[type="number"], input[inputmode="numeric"]'
            ).first.wait_for(state='visible', timeout=15000)
        except Exception:
            await asyncio.sleep(3)

        print("[5] Getting OTP...")
        code = await wait_for_otp(page, user, domain)

        if not code:
            print("[X] OTP not received!")
            await asyncio.sleep(30)
            await browser.close()
            return None
        timer.phase("OTP receive")

        # Phase 5: Enter OTP
        print(f"[6] Entering OTP: {code}")
        try:
            otp_inputs = page.locator(
                'input[type="text"], input[type="number"], input[inputmode="numeric"]'
            )
            count = await otp_inputs.count()

            if count >= 6:
                for i, digit in enumerate(code[:6]):
                    await otp_inputs.nth(i).fill(digit)
                    await human_delay(50, 200, fast)
            else:
                await page.locator('input[type="text"]').first.fill(code)

            await asyncio.sleep(1)

            try:
                await page.get_by_role('button', name='Verify').click(timeout=3000)
            except Exception:
                try:
                    await page.get_by_role('button', name='Submit').click(timeout=3000)
                except Exception:
                    pass

            # CRITICAL: domcontentloaded (NOT networkidle)
            try:
                await page.wait_for_load_state('domcontentloaded', timeout=15000)
            except Exception:
                await asyncio.sleep(3)
        except Exception as e:
            print(f"  [!] OTP entry error: {e}")
        timer.phase("OTP entry")

        # Phase 6: Terms popup — CRITICAL
        print("[7] Handling terms popup...")
        await handle_terms_dialog(page, fast)
        # Cookie banner
        try:
            accept = page.locator('button:has-text("Accept All"):visible')
            if await accept.count() > 0:
                await accept.first.click(force=True)
                await asyncio.sleep(0.5)
                print("  Cookies accepted")
        except Exception:
            pass
        timer.phase("Terms dialog")

        # Phase 7: Balance + referral
        print("[8] Navigating to balance...")
        await page.goto(BALANCE_URL, wait_until='domcontentloaded')
        await handle_dialogs(page, fast)

        # Enter referral
        await enter_referral(page, referral_code, fast)
        await handle_dialogs(page, fast)
        timer.phase("Referral entry")

        # Phase 8: Verify balance
        print("[10] Verifying balance...")
        balance = await extract_balance(page)
        print(f"  Balance: {balance}")
        timer.phase("Balance verify")

        # Phase 9: API key
        print("[11] Creating API key...")
        api_key = await create_api_key(page, f"auto_{account_num}", fast)
        timer.phase("API key creation")

        # Phase 10: Save credentials
        print("[12] Saving credentials...")
        creds = {
            "email": email,
            "password": password,
            "balance": balance,
            "referral": referral_code,
            "api_key": api_key,
            "created": time.strftime("%Y-%m-%d %H:%M:%S"),
            "method": "mimo-cli",
        }

        os.makedirs(ACCOUNTS_DIR, exist_ok=True)
        filename = f"auto_{account_num}_full.txt"
        filepath = os.path.join(ACCOUNTS_DIR, filename)
        with open(filepath, "w") as f:
            f.write(f"=== MiMo Account {account_num} ===\n")
            f.write(f"Email: {email}\n")
            f.write(f"Password: {password}\n")
            f.write(f"Balance: {balance}\n")
            f.write(f"Referral: {referral_code}\n")
            f.write(f"API Key: {api_key or 'N/A'}\n")
            f.write(f"Created: {creds['created']}\n")
            f.write(f"Method: mimo-cli\n")

        # Also save as JSON for easy parsing
        json_path = os.path.join(ACCOUNTS_DIR, f"auto_{account_num}_full.json")
        with open(json_path, "w") as f:
            json.dump(creds, f, indent=2)

        print(f"  Saved: {filepath}")

        # Logout
        print("[13] Logging out...")
        try:
            ctx = page.context
            await ctx.clear_cookies()
            await page.goto(LOGOUT_URL)
            await asyncio.sleep(2)
        except Exception:
            pass

        await browser.close()

        print()
        print("=" * 60)
        print(f"  DONE! Account created")
        print(f"  Email: {email}")
        print(f"  Balance: {balance}")
        print(f"  API Key: {'OK' if api_key else 'MISSING'}")
        print(f"  File: {filepath}")
        print(timer.summary())
        print("=" * 60)

        return creds
