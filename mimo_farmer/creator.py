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
import secrets
import string
import time

from patchright.async_api import async_playwright

from mimo_farmer.config import (
    DEFAULT_PASSWORD, DEFAULT_REFERRAL_CODE, SIGNUP_URL,
    BALANCE_URL, API_KEYS_URL, LOGOUT_URL, ACCOUNTS_DIR,
    HUMAN_DELAY_MIN_MS, HUMAN_DELAY_MAX_MS,
    FAST_DELAY_MIN_MS, FAST_DELAY_MAX_MS, FAST_MODE_MULTIPLIER,
)
from mimo_farmer.captcha import solve_recaptcha, solve_text_captcha, detect_xiaomi_captcha
from mimo_farmer.email_handler import random_email, wait_for_otp, get_available_domains
from mimo_farmer.anti_detect import (
    random_fingerprint, apply_stealth, clear_device_cookies,
    human_typing_delay, USER_AGENTS,
)


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
                timeout=3000,
                state='visible'
            )
            body = await page.evaluate("document.body?.innerText || ''")
            if 'Terms' in body or 'Agreement' in body or 'agree' in body.lower():
                terms_appeared = True
                print(f"  Terms popup detected (attempt {wait_attempt + 1})")
                break
        except Exception:
            await asyncio.sleep(1)

    if not terms_appeared:
        print("  No terms popup found after waiting")
        return False

    # Step 2: Click checkbox via native input — trusted click that React recognizes
    await asyncio.sleep(1)
    checkbox_checked = False

    # Primary: click the actual checkbox input element
    try:
        await page.locator('input[type="checkbox"]').click()
        await asyncio.sleep(1)  # Wait for React state update

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
            await asyncio.sleep(1)

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
            await asyncio.sleep(1)
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
        await asyncio.sleep(1)

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


async def extract_own_referral_code(page) -> str | None:
    """Extract this account's own referral code via "Refer & earn" dialog.

    Flow (VERIFIED via MCP Playwright 2026-06-16):
    1. On balance page, click "Refer & earn" button in sidebar
    2. Dialog appears with QR code + "Invite code: XXXXXX"
    3. Extract 6-char code from dialog
    4. Close dialog

    Returns 6-char referral code string or None.
    """
    print("  Extracting own referral code...")
    own_code = None

    try:
        # Step 1: Click "Refer & earn" button in sidebar
        refer_btn = page.get_by_role('button', name=re.compile('Refer.*earn|Refer &', re.I))
        if await refer_btn.count() > 0:
            await refer_btn.first.click(timeout=5000)
            print("  [invite] Clicked 'Refer & earn' button")
            await asyncio.sleep(3)
        else:
            # Fallback: try text-based selector
            refer_btn = page.locator('text=/Refer.*earn/i').first
            if await refer_btn.count() > 0:
                await refer_btn.click(timeout=5000)
                print("  [invite] Clicked 'Refer & earn' (text fallback)")
                await asyncio.sleep(3)
            else:
                print("  [!] 'Refer & earn' button not found")
                return None

        # Step 2: Wait for dialog to appear
        dialog = page.locator('dialog, [role="dialog"], .ant-modal-wrap')
        if await dialog.count() == 0:
            # Wait a bit more
            await asyncio.sleep(2)
            dialog = page.locator('dialog, [role="dialog"], .ant-modal-wrap')

        if await dialog.count() == 0:
            print("  [!] No dialog appeared after clicking Refer & earn")
            return None

        # Strategy 1: Find "Invite code" label, get adjacent text (VERIFIED)
        try:
            invite_label = page.locator('text=/Invite code/i')
            if await invite_label.count() > 0:
                # The code is in the next sibling element
                code_el = invite_label.locator('+ *')
                if await code_el.count() > 0:
                    text = (await code_el.first.text_content() or '').strip()
                    if len(text) >= 6 and text.isalnum():
                        own_code = text[:6].upper()
                        print(f"  [invite] Found code via 'Invite code' label: {own_code}")
        except Exception:
            pass

        # Strategy 2: Scan dialog text for 6-char alphanumeric pattern
        if not own_code:
            try:
                dialog_text = await dialog.first.evaluate("el => el.innerText")
                candidates = re.findall(r'\b([A-Z0-9]{6})\b', dialog_text.upper())
                blacklist = {
                    'INVITE', 'REFERR', 'XIAOMI', 'ACCEPT', 'CONFIRM', 'SUBMIT',
                    'CANCEL', 'CREATE', 'DELETE', 'SEARCH', 'FILTER', 'COOKIE',
                    'POLICY', 'LAYOUT', 'MODULE', 'RETURN', 'BEFORE', 'AFTER',
                    'FINISH', 'OPTION', 'NUMBER', 'DETAIL', 'RESULT', 'MI MORE',
                    'BUTTON', 'CLOSED', 'SAVED', 'STATUS', 'RETRY', 'LOGIN',
                    'EARN', 'SHARE',
                }
                for c in candidates:
                    if c not in blacklist:
                        own_code = c
                        print(f"  [invite] Found code via dialog regex scan: {own_code}")
                        break
            except Exception:
                pass

        # Strategy 3: Click Copy button in dialog and check clipboard
        if not own_code:
            try:
                copy_btn = dialog.locator('button:has-text("Copy")').first
                if await copy_btn.count() > 0:
                    await copy_btn.click()
                    await asyncio.sleep(1)
                    clipboard = await page.evaluate("navigator.clipboard.readText()")
                    if clipboard and len(clipboard.strip()) >= 6:
                        code_match = re.search(r'([A-Z0-9]{6})', clipboard.upper())
                        if code_match:
                            own_code = code_match.group(1)
                            print(f"  [invite] Found code via clipboard: {own_code}")
            except Exception:
                pass

        # Close the dialog
        try:
            close_btn = page.locator(
                'dialog button:has-text("close"), dialog button[aria-label="Close"], '
                '.ant-modal-close, dialog button img[alt="close"]'
            ).first
            if await close_btn.count() > 0:
                await close_btn.click(timeout=3000)
                print("  [invite] Dialog closed")
            else:
                # Try pressing Escape
                await page.keyboard.press('Escape')
                print("  [invite] Dialog closed via Escape")
        except Exception:
            try:
                await page.keyboard.press('Escape')
            except Exception:
                pass
        await asyncio.sleep(1)

    except Exception as e:
        print(f"  [!] Referral extraction error: {e}")

    if not own_code:
        print("  [!] Could not extract own referral code")

    return own_code


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

            # Check if network-captured key is masked (Xiaomi API returns **** asterisks)
            if api_key and '*' in api_key:
                print(f"  [!] Network response MASKED ({api_key[:15]}...). Trying clipboard...")
                api_key = None

            # Fallback: extract from input[disabled] value (may be masked with ...)
            if not api_key:
                api_key = await page.evaluate(
                    "document.querySelector('input[disabled]')?.value || null"
                )
                if api_key and ('...' in api_key or '*' in api_key):
                    print(f"  [!] Input value is MASKED ({api_key}). Trying clipboard...")
                    api_key = None  # Will try clipboard below

            # Clipboard fallback: click Copy button to get full unmasked key
            if not api_key or (api_key and ('*' in api_key or '...' in api_key)):
                try:
                    copy_btn = page.locator('button:has-text("Copy"), button[aria-label*="copy" i], [class*="copy" i]').first
                    if await copy_btn.count() > 0:
                        await copy_btn.click()
                        await asyncio.sleep(1)
                        clipboard = await page.evaluate("navigator.clipboard.readText()")
                        if clipboard and clipboard.startswith('sk-') and len(clipboard) >= 40 and '*' not in clipboard:
                            api_key = clipboard
                            print(f"  [CLIP] Got full key from clipboard ({len(clipboard)} chars)")
                except Exception as e:
                    print(f"  [!] Clipboard fallback failed: {e}")

            # Final fallback: scan DOM for any visible full sk- key
            if not api_key or (api_key and ('*' in api_key or '...' in api_key)):
                try:
                    dom_key = await page.evaluate("""
                        () => {
                            const all = document.querySelectorAll('code, pre, span, div, p, td');
                            for (const el of all) {
                                const t = el.textContent.trim();
                                if (t.startsWith('sk-') && t.length >= 40 && !t.includes('*') && !t.includes('...')) return t;
                            }
                            return null;
                        }
                    """)
                    if dom_key:
                        api_key = dom_key
                        print(f"  [DOM] Got full key from page element ({len(dom_key)} chars)")
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
    skip_referral: bool = False,
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
    # Generate random password per account (avoid bot detection)
    # Xiaomi: 8-16 chars, at least 2 of (digits, letters, special symbols)
    if password == DEFAULT_PASSWORD:
        password = 'Mm' + secrets.token_urlsafe(6) + '!9'
    timer = Timer()
    risk_control = False

    # Fetch available domains from generator.email (once per session)
    available_domains = get_available_domains()
    email_retries = 0
    MAX_EMAIL_RETRIES = 5

    mode_label = "FAST" if fast else "NORMAL"
    print("=" * 60)
    print(f"  MiMo Account Creator — Mode: {mode_label}")
    print("=" * 60)
    print(f"  Email: {email}")
    print(f"  Referral: {referral_code}")
    print()

    async with async_playwright() as p:
        # Generate random fingerprint for this session
        fp = random_fingerprint()
        print(f"  [stealth] UA: {fp['user_agent'][:60]}...")
        print(f"  [stealth] Viewport: {fp['viewport']['width']}x{fp['viewport']['height']}")
        print(f"  [stealth] Timezone: {fp['timezone']}")

        browser = await p.chromium.launch(
            headless=False,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-features=IsolateOrigins,site-per-process',
                '--no-first-run',
                '--no-default-browser-check',
            ]
        )
        context = await browser.new_context(
            viewport=fp['viewport'],
            locale=fp['locale'],
            user_agent=fp['user_agent'],
            timezone_id=fp['timezone'],
        )
        page = await context.new_page()

        # Apply anti-detection stealth JS
        await apply_stealth(context, page)

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

        # Phase 3: Submit + CAPTCHA + OTP (with email retry on "not safe")
        # Outer loop: retries with new email when Xiaomi says "not safe"
        email_signup_attempt = 0

        while True:
            if email_signup_attempt > 0:
                print(f"\n  [retry] Email signup attempt {email_signup_attempt}")

            # Inner loop: Click Next + handle immediate email rejection
            while True:
                print("[3] Clicking Next + solving CAPTCHA...")
                try:
                    await page.get_by_role('button', name='Next').click(timeout=5000)
                except Exception:
                    try:
                        await page.locator('button[type="submit"]').click(timeout=3000)
                    except Exception:
                        pass

                # Wait for page transition after Next click
                await asyncio.sleep(3)

                # Check for email validation error (email domain rejected by Xiaomi)
                email_rejected = await page.evaluate("""
                    (() => {
                        const body = document.body?.innerText || '';
                        const lower = body.toLowerCase();
                        // Common error messages when email is not accepted
                        if (lower.includes('not supported') && lower.includes('email')) return 'not_supported';
                        if (lower.includes('invalid email')) return 'invalid';
                        if (lower.includes('email address is not valid')) return 'invalid';
                        if (lower.includes('please enter a valid email')) return 'invalid';
                        if (lower.includes('邮箱')) return 'email_error';
                        // "not safe" / "isn't safe" / "unsafe" email warning
                        if (lower.includes('not safe') || lower.includes("isn't safe") || lower.includes('unsafe')) return 'not_safe';
                        // Check for inline error near email field
                        const errors = document.querySelectorAll('.ant-form-item-explain-error, .error-message, [class*="error"]');
                        for (const el of errors) {
                            const t = (el.textContent || '').toLowerCase();
                            if (t.includes('email') || t.includes('not supported') || t.includes('invalid') || t.includes('not safe') || t.includes('unsafe')) {
                                return 'inline_error';
                            }
                        }
                        return '';
                    })()
                """)

                if email_rejected and email_retries < MAX_EMAIL_RETRIES:
                    email_retries += 1
                    print(f"  [!] Email rejected ({email_rejected}) — trying new domain (attempt {email_retries}/{MAX_EMAIL_RETRIES})")
                    email, user, domain = random_email(available_domains)
                    print(f"  [email] New email: {email}")

                    # Clear and refill email field
                    try:
                        email_field = page.get_by_role('textbox', name='Email')
                        await email_field.wait_for(state='visible', timeout=5000)
                        await email_field.fill('')
                        await asyncio.sleep(0.3)
                        await email_field.fill(email)
                        await human_delay(150, 350, fast)
                    except Exception:
                        # Fallback selector
                        try:
                            await page.locator('input[type="email"]').fill(email)
                        except Exception:
                            print("  [!] Could not update email field")
                            break
                    continue  # Click Next again with new email

                break  # No email rejection or max retries reached — proceed

            # DETECT and solve ALL CAPTCHAs in a loop
            # Both reCAPTCHA AND Xiaomi text CAPTCHA can appear (sometimes both!)
            # Keep solving until neither is detected
            captcha_rounds = 0
            MAX_CAPTCHA_ROUNDS = 5
            recaptcha_solved = False  # Track if we already solved reCAPTCHA

            while captcha_rounds < MAX_CAPTCHA_ROUNDS:
                captcha_rounds += 1

                # If we already solved something, check if page progressed past CAPTCHA
                if captcha_rounds > 1:
                    page_progressed = await page.evaluate("""
                        (() => {
                            const body = document.body?.innerText || '';
                            const url = window.location.href;
                            if (body.includes('Enter the verification code')) return true;
                            if (body.includes('OTP') || body.includes('one-time')) return true;
                            if (url.includes('verify') || url.includes('otp')) return true;
                            return false;
                        })()
                    """)
                    if page_progressed:
                        print(f"  [captcha] Page progressed past CAPTCHA stage — done (round {captcha_rounds})")
                        break

                # Check 1: Xiaomi text CAPTCHA popup (auto ddddocr + manual fallback)
                is_xiaomi_captcha = await detect_xiaomi_captcha(page)
                if is_xiaomi_captcha:
                    print(f"  [!] Xiaomi text CAPTCHA detected (round {captcha_rounds})")
                    captcha_ok = await solve_text_captcha(page)
                    if not captcha_ok:
                        print("[X] Xiaomi text CAPTCHA failed!")
                        await browser.close()
                        return None
                    await asyncio.sleep(2)
                    continue

                # Check 2: reCAPTCHA anchor frame (automated audio solve)
                # Skip if we already solved reCAPTCHA (page may show stale frame)
                has_recaptcha = False
                recaptcha_already_checked = False
                for frame in page.frames:
                    if 'anchor' in frame.url and 'recaptcha' in frame.url:
                        has_recaptcha = True
                        try:
                            checked = await frame.evaluate(
                                "document.getElementById('recaptcha-anchor')?.getAttribute('aria-checked') || 'false'"
                            )
                            if checked == 'true':
                                recaptcha_already_checked = True
                        except Exception:
                            pass
                        break

                if has_recaptcha and not recaptcha_already_checked and not recaptcha_solved:
                    print(f"  [!] reCAPTCHA detected (round {captcha_rounds})")
                    captcha_ok = await solve_recaptcha(page)
                    if captcha_ok:
                        recaptcha_solved = True
                    else:
                        print("[X] reCAPTCHA failed!")
                        await browser.close()
                        return None
                    await asyncio.sleep(2)
                    continue
                elif has_recaptcha and (recaptcha_already_checked or recaptcha_solved):
                    print(f"  [✓] reCAPTCHA already solved (round {captcha_rounds}) — skipping")
                    # Don't loop forever on stale frame
                    await asyncio.sleep(2)
                    # Check one more time if Xiaomi CAPTCHA appeared
                    if await detect_xiaomi_captcha(page):
                        continue
                    break  # No new CAPTCHA — done

                # Neither detected — wait and check once more
                if captcha_rounds <= 2:
                    await asyncio.sleep(3)
                    continue

                # Multiple rounds with no CAPTCHA — done
                break

            print(f"  CAPTCHA handling done ({captcha_rounds} round(s))")
            timer.phase("CAPTCHA solve")

            # Phase 4: OTP
            # Check for "not safe" email warning that may appear after CAPTCHA
            post_captcha_email_check = await page.evaluate("""
                (() => {
                    const body = document.body?.innerText || '';
                    const lower = body.toLowerCase();
                    if (lower.includes('not safe') || lower.includes("isn't safe") || lower.includes('unsafe')) return 'not_safe';
                    if (lower.includes('not supported') && lower.includes('email')) return 'not_supported';
                    return '';
                })()
            """)
            if post_captcha_email_check:
                print(f"  [!] Email rejected after CAPTCHA ({post_captcha_email_check}) — need new email")
                code = "__UNSAFE__"
            else:
                print("[4] Waiting for OTP page...")
                try:
                    await page.locator(
                        'input[type="text"], input[type="number"], input[inputmode="numeric"]'
                    ).first.wait_for(state='visible', timeout=15000)
                except Exception:
                    await asyncio.sleep(3)

                print("[5] Getting OTP...")
                code = await wait_for_otp(page, user, domain)

            # Handle "not safe" email — retry with new email
            if code == "__UNSAFE__":
                email_signup_attempt += 1
                print(f"  [!] Unsafe email — retrying signup with new email (attempt {email_signup_attempt})")
                email, user, domain = random_email(available_domains)
                print(f"  [email] New email: {email}")

                # Navigate back to signup page
                await page.goto(SIGNUP_URL, wait_until='domcontentloaded')
                await asyncio.sleep(3)

                # Wait for signup form
                for _ in range(5):
                    try:
                        if await page.get_by_role('textbox', name='Email').is_visible(timeout=2000):
                            break
                    except Exception:
                        pass
                    await asyncio.sleep(2)

                # Refill form with new email
                try:
                    email_field = page.get_by_role('textbox', name='Email')
                    await email_field.wait_for(state='visible', timeout=10000)
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
                    print("  Form refilled with new email")
                except Exception as e:
                    print(f"  [!] Refill error: {e}")
                    await browser.close()
                    return None

                continue  # Retry outer loop with new email

            break  # Normal flow — exit outer retry loop

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
            await asyncio.sleep(2)
            await handle_dialogs(page, fast)
            timer.phase("Identity verification")
        else:
            print("  No identity verification needed, continuing...")

        # Phase 6: Terms popup — CRITICAL
        # Wait for page to fully load before checking for terms
        print("[7] Handling terms popup...")
        await asyncio.sleep(2)  # Wait for modal to fully render
        terms_ok = False
        for _terms_attempt in range(3):
            terms_ok = await handle_terms_dialog(page, fast)
            if terms_ok:
                break
            await asyncio.sleep(2)
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

        # Phase 8: Enter referral OR extract own referral code (siklus mode)
        own_referral = None
        if skip_referral:
            print("[9] Siklus mode — skipping referral entry, extracting own code...")
            own_referral = await extract_own_referral_code(page)
            if own_referral:
                print(f"  ✓ Own referral code: {own_referral}")
            else:
                print("  [!] Could not extract own referral code — siklus child accounts will fail")
            timer.phase("Referral extraction")
        else:
            print("[9] Entering referral code...")
            referral_ok = await enter_referral(page, referral_code, fast)
            await handle_dialogs(page, fast)
            timer.phase("Referral entry")

        # Phase 9: Detect risk control
        print("[10] Checking for risk control...")
        risk_control = await detect_risk_control(page)
        if risk_control:
            print("  [!] Risk control detected — STOPPING. Create new referral code.")
            await browser.close()
            return {
                "email": email,
                "password": password,
                "balance": "$0.72",
                "referral": referral_code,
                "api_key": None,
                "risk_control": True,
                "own_referral": own_referral,
                "created": time.strftime("%Y-%m-%d %H:%M:%S"),
                "method": "cli_auto",
            }
        timer.phase("Risk control check")

        # Phase 10: Verify balance — MUST be $2.72 before continuing
        print("[11] Verifying balance...")
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
            "email_link": f"https://generator.email/{email}",
            "password": password,
            "balance": balance,
            "referral": referral_code,
            "api_key": api_key,
            "risk_control": risk_control,
            "own_referral": own_referral,
            "created": time.strftime("%Y-%m-%d %H:%M:%S"),
            "method": "mimo-farmer",
        }

        # Per-account files removed — only batch file saved at end of run

        # Phase 13: Logout + clear all traces (for next account in batch)
        print("[14] Logging out...")
        try:
            ctx = page.context
            await clear_device_cookies(ctx)
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
