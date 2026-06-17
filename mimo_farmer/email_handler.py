"""Email generator and OTP polling via generator.email."""

import asyncio
import random
import re
import string
import time

from mimo_farmer.config import EMAIL_DOMAINS, OTP_TIMEOUT_SECONDS, OTP_POLL_INTERVAL_SECONDS


def get_available_domains() -> list[str]:
    """Scrape available email domains from generator.email.

    Falls back to EMAIL_DOMAINS config if scraping fails.
    """
    import subprocess
    try:
        result = subprocess.run(
            ['curl', '-s', 'https://generator.email', '--max-time', '15'],
            capture_output=True, text=True, timeout=20
        )
        html = result.stdout
        # Extract domains from quoted strings in the page
        domains = re.findall(r'"([a-z0-9.-]+\.[a-z]{2,})"', html)
        # Filter: only real email domains (skip CDN/analytics/w3c)
        skip = {'google-analytics.com', 'googlesyndication.com', 'googletagmanager.com',
                'jsdelivr.net', 'w3.org', 'googleapis.com', 'gstatic.com'}
        domains = sorted(set(d for d in domains if d not in skip and '.' in d))
        if domains:
            print(f"  [email] Found {len(domains)} domains from generator.email")
            return domains
    except Exception as e:
        print(f"  [email] Domain fetch failed: {e}")
    return EMAIL_DOMAINS


def random_email(domains: list[str] = None) -> tuple[str, str, str]:
    """Generate random email address for generator.email.

    Args:
        domains: Optional list of domains to pick from.
                 If None, uses EMAIL_DOMAINS config.
    """
    if domains is None:
        domains = EMAIL_DOMAINS
    user = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
    domain = random.choice(domains)
    return f"{user}@{domain}", user, domain


async def _extract_codes_from_page(email_page) -> list[str]:
    """Extract all 6-digit codes visible on the page."""
    codes = set()
    try:
        body = await email_page.evaluate("document.body?.innerText || ''")
        found = re.findall(r'\b(\d{6})\b', body)
        codes.update(found)
    except Exception:
        pass
    return list(codes)


async def _click_email_and_get_code(email_page, skip_codes: set, inbox_url: str) -> str | None:
    """Click on Xiaomi email rows to read body, return new code if found.

    generator.email uses DIV-based layout (NOT <table>):
    - Container: div#email-table
    - Each email: a.list-group-item (clickable link)
    - Clicking loads email body inline (URL stays on inbox page)
    """
    try:
        # CORRECT selector: a.list-group-item (NOT table tr!)
        items = email_page.locator('#email-table a.list-group-item')
        count = await items.count()

        if count == 0:
            # Fallback: try broader selector
            items = email_page.locator('a.list-group-item')
            count = await items.count()

        print(f"  [otp] Found {count} email items in inbox")

        for i in range(count):
            item = items.nth(i)
            try:
                item_text = await item.inner_text()
            except Exception:
                continue

            # Only process Xiaomi emails
            if 'xiaomi' not in item_text.lower():
                continue

            subject = item_text.strip()[:80]
            print(f"  [otp] Clicking email {i}: {subject}")

            try:
                await item.click(timeout=3000)
                await asyncio.sleep(3)

                # Extract codes ONLY from the email body container, not full page
                # Try to scope to the email content area first
                body_text = await email_page.evaluate("""
                    (() => {
                        // Try to get just the email body content (not inbox list)
                        const body = document.querySelector('.email-body, .mail-body, #email-body, .msg-body');
                        if (body) return body.innerText || '';
                        // Fallback: get the main content area (skip navigation/sidebar)
                        const main = document.querySelector('.wrap, .layout, main, .content');
                        if (main) return main.innerText || '';
                        // Last resort: full page
                        return document.body?.innerText || '';
                    })()
                """)
                all_codes = re.findall(r'\b(\d{6})\b', body_text)
                print(f"  [otp] Codes found on page: {all_codes}")

                # Filter: not year prefix, not in skip list
                new_codes = [c for c in all_codes if not c.startswith('20') and c not in skip_codes]
                if new_codes:
                    print(f"  [otp] New code found: {new_codes[0]}")
                    return new_codes[0]

                print(f"  [otp] No new codes in this email")

                # Go back to inbox — MUST reload to reset page state
                await email_page.goto(inbox_url, wait_until='domcontentloaded', timeout=60000)
                await asyncio.sleep(3)

                # Re-fetch email items after navigation (DOM was replaced)
                items = email_page.locator('#email-table a.list-group-item')
                new_count = await items.count()
                if new_count == 0:
                    items = email_page.locator('a.list-group-item')
                    new_count = await items.count()
                # Update outer count for the loop
                count = new_count

            except Exception as e:
                print(f"  [otp] Click error: {e}")
                # Page might have navigated — try to recover
                try:
                    await email_page.goto(inbox_url, wait_until='domcontentloaded', timeout=60000)
                    await asyncio.sleep(3)
                    items = email_page.locator('#email-table a.list-group-item')
                    count = await items.count()
                except Exception:
                    pass
                continue

                # Re-get items after navigation
                items = email_page.locator('#email-table a.list-group-item')
                count = await items.count()
            except Exception as e:
                print(f"  [otp] Click error: {str(e)[:60]}")
                try:
                    await email_page.goto(inbox_url, wait_until='domcontentloaded', timeout=60000)
                    await asyncio.sleep(2)
                except Exception:
                    pass

    except Exception as e:
        print(f"  [otp] Email click scan error: {e}")

    return None


async def wait_for_otp(page, user: str, domain: str, timeout: int = OTP_TIMEOUT_SECONDS, skip_codes: list = None) -> str | None:
    """Poll generator.email inbox for 6-digit OTP code.

    Strategy:
    1. Scan inbox body text for 6-digit codes
    2. If all found codes are in skip_codes, click email rows to read body
    3. Repeat until new code found or timeout
    """
    print(f"  [otp] Waiting for email to {user}@{domain} (timeout {timeout}s)...")

    email_page = await page.context.new_page()
    inbox_url = f"https://generator.email/{user}@{domain}"
    await email_page.goto(inbox_url, wait_until='domcontentloaded', timeout=60000)
    await asyncio.sleep(4)

    start = time.time()
    code = None
    check_count = 0
    if skip_codes is None:
        skip_codes = set()
    else:
        skip_codes = set(skip_codes)

    while time.time() - start < timeout:
        check_count += 1
        try:
            # Step 1: Scan inbox body for codes (might find codes in previews)
            codes = await _extract_codes_from_page(email_page)

            if codes:
                otp_codes = [c for c in codes if not c.startswith('20') and c not in skip_codes]
                if otp_codes:
                    code = otp_codes[0]
                    print(f"  [otp] Found code: {code} (check #{check_count})")
                    break

            # Step 2: Click email rows to read bodies
            # Trigger when: (a) all codes in skip list, OR (b) no codes visible on page
            should_click = False
            if codes and skip_codes and check_count >= 1:
                print(f"  [otp] All codes in skip list, clicking email rows...")
                should_click = True
            elif not codes and check_count >= 1:
                print(f"  [otp] No codes visible on inbox, clicking email rows...")
                should_click = True

            if should_click:
                new_code = await _click_email_and_get_code(email_page, skip_codes, inbox_url)
                if new_code:
                    code = new_code
                    print(f"  [otp] Found code in email body: {code}")
                    break

            if check_count % 5 == 0:
                print(f"  [otp] Still waiting... ({int(time.time() - start)}s)")
        except Exception as e:
            if check_count <= 3:
                print(f"  [otp] Check error: {e}")

        # Refresh inbox
        try:
            await email_page.reload(wait_until='domcontentloaded', timeout=60000)
            await asyncio.sleep(OTP_POLL_INTERVAL_SECONDS)
        except Exception:
            try:
                await email_page.goto(inbox_url, wait_until='domcontentloaded')
                await asyncio.sleep(OTP_POLL_INTERVAL_SECONDS)
            except Exception:
                pass

        await asyncio.sleep(1.5)

    await email_page.close()
    return code
