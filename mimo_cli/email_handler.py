"""Email generator and OTP polling via generator.email."""

import asyncio
import random
import re
import string
import time

from mimo_cli.config import EMAIL_DOMAINS, OTP_TIMEOUT_SECONDS, OTP_POLL_INTERVAL_SECONDS


def random_email() -> tuple[str, str, str]:
    """Generate random email address for generator.email.

    Returns:
        (full_email, username, domain)
    """
    user = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
    domain = random.choice(EMAIL_DOMAINS)
    return f"{user}@{domain}", user, domain


async def wait_for_otp(page, user: str, domain: str, timeout: int = OTP_TIMEOUT_SECONDS) -> str | None:
    """Poll generator.email inbox for 6-digit OTP code.

    Opens new tab in same browser context, polls until code found or timeout.

    Args:
        page: Playwright page object (used to open new tab in same context)
        user: Email username part
        domain: Email domain part
        timeout: Max seconds to wait

    Returns:
        6-digit OTP string or None
    """
    print(f"  [otp] Waiting for email to {user}@{domain} (timeout {timeout}s)...")

    email_page = await page.context.new_page()
    inbox_url = f"https://generator.email/{user}@{domain}"
    await email_page.goto(inbox_url, wait_until='domcontentloaded')
    await asyncio.sleep(4)

    start = time.time()
    code = None
    check_count = 0

    while time.time() - start < timeout:
        check_count += 1
        try:
            body = await email_page.evaluate("document.body?.innerText || ''")
            codes = re.findall(r'\b(\d{6})\b', body)

            if codes:
                # Filter out year-like codes starting with '20'
                otp_codes = [c for c in codes if not c.startswith('20')]
                if otp_codes:
                    code = otp_codes[0]
                    print(f"  [otp] Found code: {code} (check #{check_count})")
                    break
                elif codes:
                    code = codes[0]
                    if check_count <= 2:
                        print(f"  [otp] Possible code: {code}")

            if check_count % 5 == 0:
                print(f"  [otp] Still waiting... ({int(time.time() - start)}s)")
        except Exception as e:
            if check_count <= 3:
                print(f"  [otp] Check error: {e}")

        try:
            await email_page.reload(wait_until='domcontentloaded')
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
