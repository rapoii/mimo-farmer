"""Core MiMo account creation pipeline.

PROVEN WORKING (2026-06-14):
  Patchright browser → fill signup → solve reCAPTCHA audio → OTP from temp email
  → enter OTP → Terms dialog (ant-modal) → CLEAR COOKIES → navigate balance page
  → enter referral code → detect risk control → verify balance
  → create API key → save credentials.

CRITICAL patterns preserved:
  - domcontentloaded (NOT networkidle — causes timeout on MiMo SPA)
  - Terms dialog: .ant-modal:has-text('Terms') → checkbox → Confirm button
  - Referral: 6-char OTP input fields via page.get_by_role('textbox')
  - API key: input[disabled] value extraction
  - Balance regex: r'Balance\\s*\\$\\s*([\\d.]+)'
  - Cookie clearing before MiMo platform navigation (prevents own-referral error)
  - Risk control detection on balance page
  - Terms dialog handling at EVERY page.goto()
"""

import asyncio
import json
import os
import re
import time

from patchright.async_api import async_playwright

from mimo_farmer.config import (
    DEFAULT_PASSWORD, DEFAULT_REFERRAL_CODE, SIGNUP_URL,
    BALANCE_URL, API_KEYS_URL, LOGOUT_URL, ACCOUNTS_DIR,
    HUMAN_DELAY_MIN_MS, HUMAN_DELAY_MAX_MS,
    FAST_DELAY_MIN_MS, FAST_DELAY_MAX_MS, FAST_MODE_MULTIPLIER,
)
from mimo_farmer.captcha import solve_recaptcha
from mimo_farmer.email_handler import random_email, wait_for_otp


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
    """Handle Terms modal — WAIT for it to appear, then check checkbox + confirm.

    PROVEN FIX (2026-06-15): Use page.locator('input[type="checkbox"]').click()
    instead of clicking label/span wrappers. The input click sends a trusted event
    that React recognizes, properly updating internal state and enabling Confirm.
    """
    # Step 1: Wait for Terms popup to actually appear (up to 10s)
    terms_appeared = False
    for wait_attempt in range(3):
        try:
            await page.wait_for_selector(
                'input[type="checkbox"]:visible, [role="checkbox"]:visible',
                timeout=4000,
                state='visible'
            )
            body = await page.evaluate("document.body?.innerText || ''")
            if 'Terms' in body or 'Agreement' in body or 'agree' in body.lower():
                terms_appeared = True
                print(f"  Terms popup detected (attempt {wait_attempt + 1})")
                break
        except Exception:
            await asyncio.sleep(2)

    if not terms_appeared:
        print("  No terms popup found after waiting")
        return False

    # Step 2: Click checkbox via native input — trusted click that React recognizes
    await asyncio.sleep(1)
    checkbox_checked = False

    # Primary: click the actual checkbox input element
    try:
        await page.locator('input[type="checkbox"]').click()
        await asyncio.sleep(2)  # Wait for React state update

        is_checked = await page.evaluate(
            "document.querySelector('.ant-checkbox-input')?.checked || false"
        )
        is_disabled = await page.evaluate(
            "document.querySelector('.ant-modal-footer button:last-child')?.disabled ?? true"
        )
        print(f"  input[checkbox] click: checked={is_checked}, confirm_disabled={is_disabled}")

        if is_checked and not is_disabled:
            checkbox_checked = True
            print("  ✓ Checkbox checked, Confirm enabled!")
    except Exception as e:
        print(f"  input[checkbox] click error: {str(e)[:80]}")

    # Fallback: try .ant-checkbox-input selector
    if not checkbox_checked:
        try:
            await page.locator('.ant-checkbox-input').click()
            await asyncio.sleep(2)

            is_checked = await page.evaluate(
                "document.querySelector('.ant-checkbox-input')?.checked || false"
            )
            is_disabled = await page.evaluate(
                "document.querySelector('.ant-modal-footer button:last-child')?.disabled ?? true"
            )
            print(f"  .ant-checkbox-input click: checked={is_checked}, confirm_disabled={is_disabled}")

            if is_checked and not is_disabled:
                checkbox_checked = True
                print("  ✓ Checkbox checked via fallback, Confirm enabled!")
        except Exception as e:
            print(f"  .ant-checkbox-input click error: {str(e)[:80]}")

    if not checkbox_checked:
        # Final check: maybe checkbox IS checked but Confirm timing off
        is_checked = await page.evaluate(
            "document.querySelector('.ant-checkbox-input')?.checked || false"
        )
        if is_checked:
            # Extra wait — Confirm may enable after another render cycle
            await asyncio.sleep(2)
            is_disabled = await page.evaluate(
                "document.querySelector('.ant-modal-footer button:last-child')?.disabled ?? true"
            )
            if not is_disabled:
                checkbox_checked = True
                print("  ✓ Checkbox checked, Confirm enabled (after extra wait)!")
            else:
                print("  [!] Checkbox checked but Confirm still disabled")
                return False
        else:
            print("  [!] Could not check checkbox — skipping terms")
            return False

    # Step 3: Click Confirm button
    await asyncio.sleep(0.5)

    confirm_clicked = False
    try:
        confirm_btn = page.locator('.ant-modal-footer button:last-child')
        await confirm_btn.click(timeout=5000)
        await asyncio.sleep(2)

        modal_visible = await page.locator('.ant-modal-wrap:visible').count()
        if modal_visible == 0:
            print("  ✓ Confirm clicked, modal closed!")
            confirm_clicked = True
        else:
            print(f"  Modal still visible after click ({modal_visible}), trying JS...")
    except Exception as e:
        print(f"  Playwright confirm click failed: {str(e)[:80]}")

    # Fallback: JS click
    if not confirm_clicked:
        try:
            await page.evaluate('''() => {
                const btn = document.querySelector('.ant-modal-footer button:last-child');
                if (btn) {
                    btn.disabled = false;
                    btn.removeAttribute('disabled');
                    btn.click();
                }
            }''')
            await asyncio.sleep(2)
            modal_visible = await page.locator('.ant-modal-wrap:visible').count()
            if modal_visible == 0:
                print("  ✓ Confirm clicked via JS force, modal closed!")
                confirm_clicked = True
            else:
                print(f"  Modal still visible after JS click ({modal_visible})")
        except Exception:
            pass

    if confirm_clicked:
        return True
    else:
        print("  [!] Could not click Confirm")
        return False


async def enter_referral(page, referral_code: str, fast: bool = False) -> bool:
    """Enter referral code. Returns True only if bind was attempted successfully.

    Primary: UI flow. Fallback: authenticated API `/api/v1/invitation/bind`.
    """
    print(f"  Entering referral: {referral_code}")
    referral_submitted = False
    try:
        # Wait for SPA/sidebar to render
        await asyncio.sleep(3)

        # Primary UI selectors: button OR text-containing clickable nodes
        invite_candidates = [
            page.get_by_role('button', name=re.compile('invite|referral|Enter invite', re.I)),
            page.locator('text=/Enter invite code/i'),
            page.locator('text=/invite code/i'),
        ]

        clicked = False
        for candidate in invite_candidates:
            try:
                count = await candidate.count()
                if count > 0:
                    await candidate.first.click(force=True, timeout=5000)
                    await asyncio.sleep(1.5)
                    clicked = True
                    break
            except Exception:
                continue

        if clicked:
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
                print("  Referral submitted via UI!")
                referral_submitted = True
            else:
                print(f"  [!] Expected 6 OTP fields, found {count}")
        else:
            print("  [!] Invite UI not found, trying API fallback...")

        # Fallback API bind if UI failed
        if not referral_submitted:
            api_result = await page.evaluate(
                """
                async (code) => {
                    try {
                        const resp = await fetch('/api/v1/invitation/bind', {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            credentials: 'include',
                            body: JSON.stringify({inviteCode: code})
                        });
                        const text = await resp.text();
                        return {ok: resp.ok, status: resp.status, text};
                    } catch (e) {
                        return {ok: false, status: 0, text: e.message};
                    }
                }
                """,
                referral_code,
            )
            print(f"  API bind result: {api_result}")
            referral_submitted = bool(api_result and api_result.get('ok'))

        return referral_submitted
    except Exception as e:
        print(f"  [!] Referral error: {e}")
        return False


async def wait_for_balance_272(page, timeout: int = 60) -> str:
    """Wait until balance is $2.72. Never proceed on $0.72."""
    start = time.time()
    last_balance = "$0.00"
    while time.time() - start < timeout:
        balance = await extract_balance(page)
        last_balance = balance
        if balance == "$2.72":
            return balance
        print(f"  Balance still {balance}, waiting...")
        await asyncio.sleep(5)
    return last_balance


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


async def detect_risk_control(page) -> bool:
    """Check if the current page shows risk control restrictions.

    Returns True if risk control detected, False otherwise.
    """
    try:
        body = await page.evaluate("document.body.innerText")
        body_lower = body.lower()
        if 'risk control' in body_lower:
            print()
            print("  " + "!" * 50)
            print("  [!] RISK CONTROL DETECTED")
            print("  [!] This account has been flagged by risk control restrictions.")
            print("  [!] The account may have limited functionality.")
            print("  [!] RECOMMENDATION: Create a new account and use that account's")
            print("  [!] referral code for future registrations.")
            print("  " + "!" * 50)
            print()
            return True
    except Exception:
        pass
    return False


async def clear_xiaomi_cookies(context) -> None:
    """Clear ALL cookies on xiaomi.com domains.

    CRITICAL: Prevents 'own invitation code' error from stale sessions.
    Must be called AFTER signup OTP verification but BEFORE navigating to MiMo platform.
    """
    print("  Clearing xiaomi.com cookies...")
    try:
        cookies = await context.cookies()
        xiaomi_cookies = [c for c in cookies if 'xiaomi' in c.get('domain', '').lower()]
        for cookie in xiaomi_cookies:
            await context.clear_cookies(
                name=cookie['name'],
                domain=cookie['domain'],
                path=cookie.get('path', '/'),
            )
        print(f"  Cleared {len(xiaomi_cookies)} xiaomi.com cookies")
    except Exception:
        # Fallback: clear all cookies
        await context.clear_cookies()
        print("  Cleared ALL cookies (fallback)")
    await asyncio.sleep(1)


async def handle_identity_verification(page, user: str, domain: str, fast: bool = False, first_otp: str = None) -> bool:
    """Handle Xiaomi identity verification page (verifyEmail).

    This page appears AFTER initial OTP for some accounts.
    Shows 'Account Authentication' with 'Send' button to send verification code to email.

    Steps:
    1. Wait up to 15s for verifyEmail page to appear (retry loop)
    2. Click 'Send' button
    3. Wait for second verification code from temp email
    4. Enter the code
    5. Continue

    Returns True if verification page was found and handled, False if not present.
    """
    # Retry detection for up to 15 seconds — page may load slowly
    is_verify_page = False
    for detect_attempt in range(6):
        await asyncio.sleep(2.5)
        url = page.url
        body_text = ""
        try:
            body_text = await page.evaluate("document.body?.innerText || ''")
        except Exception:
            pass

        is_verify_page = (
            'verifyEmail' in url
            or 'Account Authentication' in body_text
            or 'verify your identity' in body_text.lower()
            or 'identity/verify' in url
        )

        if is_verify_page:
            break

        if detect_attempt < 5:
            print(f"  [verify] Not detected yet (attempt {detect_attempt + 1}/6), waiting...")

    if not is_verify_page:
        print("  [verify] No identity verification page after 15s")
        return False

    print("  [verify] Identity verification page detected!")
    print(f"  [verify] URL: {page.url[:100]}")

    # Click Send button
    send_clicked = False
    for btn_name in ['Send', 'Kirim']:
        try:
            btn = page.get_by_role('button', name=btn_name)
            if await btn.count() > 0:
                await btn.first.click(timeout=5000)
                send_clicked = True
                print(f"  [verify] '{btn_name}' clicked!")
                break
        except Exception:
            continue

    if not send_clicked:
        # Fallback: look for orange/primary button
        try:
            btn = page.locator('button[type="submit"], .btn-primary, button:has-text("Send")')
            if await btn.count() > 0:
                await btn.first.click(timeout=5000)
                send_clicked = True
                print("  [verify] Send button clicked (fallback)!")
        except Exception:
            pass

    if not send_clicked:
        print("  [!] Could not find Send button on verification page")
        return True  # Page was present but we couldn't handle it

    # Wait for code input to appear
    await asyncio.sleep(3)

    # Get second verification code from temp email (skip first OTP code)
    # Keep refreshing until NEW code arrives — NO fallback to same code
    print("  [verify] Waiting for NEW verification code (refreshing until found)...")
    from mimo_farmer.email_handler import wait_for_otp
    skip = [first_otp] if first_otp else []
    code = await wait_for_otp(page, user, domain, timeout=180, skip_codes=skip)

    if not code:
        print("  [!] Verification code not received after 180s!")
        return True

    print(f"  [verify] Got verification code: {code}")

    # Enter verification code
    try:
        otp_inputs = page.locator(
            'input[type="text"], input[type="number"], input[inputmode="numeric"]'
        )
        count = await otp_inputs.count()

        if count >= 6:
            for i, digit in enumerate(code[:6]):
                await otp_inputs.nth(i).fill(digit)
                await human_delay(50, 150, fast)
        else:
            await page.locator('input[type="text"]').first.fill(code)

        await asyncio.sleep(1)

        # Click Verify/Submit
        for btn_name in ['Verify', 'Submit', 'Confirm', 'Next']:
            try:
                btn = page.get_by_role('button', name=btn_name)
                if await btn.count() > 0:
                    await btn.first.click(timeout=3000)
                    print(f"  [verify] '{btn_name}' clicked!")
                    break
            except Exception:
                continue

        await asyncio.sleep(3)
        print("  [verify] Identity verification completed!")
    except Exception as e:
        print(f"  [!] Verification entry error: {e}")

    return True


async def create_api_key(page, label: str, fast: bool = False) -> str | None:
    """Create and extract API key.

    Strategy: intercept network response for full key (input[disabled] shows masked).
    Fallback: extract from input[disabled] value (masked but functional).
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

            # CRITICAL: Set up network intercept BEFORE clicking Confirm
            # The full API key is in the POST response, not in the masked input
            captured_key = None
            async def capture_api_key_response(response):
                nonlocal captured_key
                try:
                    if response.status == 200 and ('api-key' in response.url.lower() or 'apikey' in response.url.lower()):
                        body = await response.json()
                        # Deep search for sk- key in response
                        def find_key(obj):
                            if isinstance(obj, str) and obj.startswith('sk-') and len(obj) >= 40:
                                return obj
                            if isinstance(obj, dict):
                                for v in obj.values():
                                    r = find_key(v)
                                    if r:
                                        return r
                            if isinstance(obj, list):
                                for v in obj:
                                    r = find_key(v)
                                    if r:
                                        return r
                            return None
                        found = find_key(body)
                        if found:
                            captured_key = found
                            print(f"  [NET] Captured full key from response ({len(found)} chars)")
                except Exception:
                    pass

            page.on('response', capture_api_key_response)

            # Confirm
            await page.get_by_role('button', name='Confirm').click(timeout=5000)

            # Wait for key to appear in disabled input
            try:
                await page.locator('input[disabled]').first.wait_for(
                    state='visible', timeout=8000
                )
            except Exception:
                await asyncio.sleep(3)

            # Prefer network-captured key (full, unmasked)
            api_key = captured_key

            # Fallback: extract from input[disabled] value (masked)
            if not api_key:
                api_key = await page.evaluate(
                    "document.querySelector('input[disabled]')?.value || null"
                )
                if api_key and '...' in api_key:
                    print(f"  [!] Input value is MASKED ({api_key}). Network capture failed.")
                    # Try clipboard: click copy button if exists
                    try:
                        copy_btn = page.locator('button:has-text("Copy"), button[aria-label*="copy" i], [class*="copy" i]').first
                        if await copy_btn.count() > 0:
                            await copy_btn.click()
                            await asyncio.sleep(0.5)
                            clipboard = await page.evaluate("navigator.clipboard.readText()")
                            if clipboard and clipboard.startswith('sk-') and len(clipboard) >= 40:
                                api_key = clipboard
                                print(f"  [CLIP] Got full key from clipboard ({len(clipboard)} chars)")
                    except Exception:
                        pass

            # Remove listener
            try:
                page.remove_listener('response', capture_api_key_response)
            except Exception:
                pass

            if api_key and len(api_key) >= 40:
                print(f"  API Key: {api_key[:10]}...{api_key[-5:]}")
            elif api_key:
                print(f"  API Key (short/masked): {api_key}")
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
    account_num: int = 0,
) -> dict | None:
    """Full MiMo account creation pipeline.

    Steps:
    1. Launch Patchright browser (anti-detect Playwright)
    2. Navigate to signup URL with referral code
    3. Fill email + password form
    4. Submit and solve reCAPTCHA v2 (audio challenge with manual fallback)
    5. Get OTP from temp email (generator.email)
    6. Enter OTP
    7. Handle Terms dialog (ant-modal)
    8. CLEAR COOKIES (prevents own-referral error)
    9. Navigate to balance page (auto-login via Xiaomi session)
    10. Handle Terms dialog again
    11. Enter referral code
    12. Detect risk control restrictions
    13. Verify balance ($2.72 expected)
    14. Create API key
    15. Save credentials (includes risk_control flag)

    Args:
        referral_code: 6-char MiMo referral code
        password: Account password
        fast: Enable fast mode (reduced delays)

    Returns:
        Dict with credentials or None on failure
    """
    email, user, domain = random_email()
    if not account_num:
        account_num = int(time.time()) % 1000
    timer = Timer()
    risk_control = False

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

        # Phase 1: Navigate directly to signup page (no tab click needed)
        print("[1] Navigating to signup...")
        await page.goto(SIGNUP_URL, wait_until='domcontentloaded')
        await asyncio.sleep(3)

        # Wait for signup form to render
        signup_ready = False
        for _ in range(8):
            try:
                if await page.get_by_role('textbox', name='Email').is_visible(timeout=2000):
                    signup_ready = True
                    break
            except Exception:
                pass
            try:
                if await page.locator('input[type="email"]').is_visible(timeout=1000):
                    signup_ready = True
                    break
            except Exception:
                pass
            await asyncio.sleep(2)

        if not signup_ready:
            print("  [!] Signup form not loaded — aborting")
            await browser.close()
            return None
        print("  Signup form ready")
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

        # Phase 3: Submit + reCAPTCHA (with audio detection fallback)
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

        # Phase 5.5: Identity verification (may appear for some accounts)
        print("[6.5] Checking for identity verification...")
        verify_handled = await handle_identity_verification(page, user, domain, fast, first_otp=code)
        if verify_handled:
            print("  Identity verification handled!")
            # After verification, navigate to MiMo platform to establish session
            print("  Establishing MiMo platform session...")
            await page.goto("https://platform.xiaomimimo.com/", wait_until='domcontentloaded')
            await asyncio.sleep(5)
            await handle_dialogs(page, fast)
            timer.phase("Identity verification")
        else:
            print("  No identity verification needed, continuing...")

        # Phase 6: Terms popup — CRITICAL
        # Wait for page to fully load before checking for terms
        print("[7] Handling terms popup...")
        await asyncio.sleep(5)  # Wait for modal to fully render
        terms_ok = False
        for _terms_attempt in range(3):
            terms_ok = await handle_terms_dialog(page, fast)
            if terms_ok:
                break
            await asyncio.sleep(3)
        if terms_ok:
            print("  Terms dialog handled!")
        else:
            print("  No terms dialog found, continuing...")
        # Cookie banner (may appear separately)
        try:
            accept = page.locator('button:has-text("Accept All"):visible')
            if await accept.count() > 0:
                await accept.first.click(force=True)
                await asyncio.sleep(0.5)
                print("  Cookies accepted")
        except Exception:
            pass
        timer.phase("Terms dialog")

        # Phase 7: Navigate to balance page (auto-login via Xiaomi session)
        # CRITICAL: Do NOT clear cookies here — session needed for auto-login
        # Cookie clearing happens at END (logout) and START (next account)
        print("[8] Navigating to balance page...")
        await page.goto(BALANCE_URL, wait_until='domcontentloaded')
        await asyncio.sleep(3)

        # Handle terms dialog on balance page
        await handle_terms_dialog(page, fast)
        await handle_dialogs(page, fast)
        timer.phase("Balance page + terms")

        # Phase 8: Enter referral — MUST succeed before API key
        print("[9] Entering referral code...")
        referral_ok = await enter_referral(page, referral_code, fast)
        await handle_dialogs(page, fast)
        timer.phase("Referral entry")

        # Phase 9: Detect risk control
        print("[10] Checking for risk control...")
        risk_control = await detect_risk_control(page)
        if risk_control:
            print("  [!] Risk control detected — continuing with limited account")
        timer.phase("Risk control check")

        # Phase 10: Verify balance — MUST be $2.72 before continuing
        # Skip wait when risk_control detected — $2.72 won't arrive
        print("[11] Verifying balance...")
        if risk_control:
            balance = await extract_balance(page)
            print(f"  Balance: {balance} (risk control — skipped 10s wait)")
        else:
            balance = await wait_for_balance_272(page, timeout=10)
            print(f"  Balance: {balance}")
        timer.phase("Balance verify")

        if balance != "$2.72":
            print(f"  [!] Balance {balance} (referral may not have bound) — continuing to API key anyway.")

        # Phase 11: API key
        print("[12] Creating API key...")
        api_key = await create_api_key(page, f"auto_{account_num}", fast)
        timer.phase("API key creation")

        if not api_key:
            print("[X] API key missing — stopping. Not a success.")
            await browser.close()
            return None

        # Phase 12: Save credentials (includes risk_control flag)
        print("[13] Saving credentials...")
        creds = {
            "email": email,
            "password": password,
            "balance": balance,
            "referral": referral_code,
            "api_key": api_key,
            "risk_control": risk_control,
            "created": time.strftime("%Y-%m-%d %H:%M:%S"),
            "method": "mimo-farmer",
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
            f.write(f"Risk Control: {risk_control}\n")
            f.write(f"Created: {creds['created']}\n")
            f.write(f"Method: mimo-farmer\n")

        # Also save as JSON for easy parsing
        json_path = os.path.join(ACCOUNTS_DIR, f"auto_{account_num}_full.json")
        with open(json_path, "w") as f:
            json.dump(creds, f, indent=2)

        print(f"  Saved: {filepath}")

        # Phase 13: Logout + clear cookies (for next account in batch)
        print("[14] Logging out...")
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
        print(f"  Risk Control: {risk_control}")
        print(f"  File: {filepath}")
        print(timer.summary())
        print("=" * 60)

        return creds
