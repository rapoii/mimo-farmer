"""CAPTCHA Solvers — supports both reCAPTCHA v2 audio AND Xiaomi text CAPTCHA.

DETECTION LOGIC (called from creator.py):
  1. Check if reCAPTCHA anchor frame appeared → solve_recaptcha()
  2. Check if Xiaomi text CAPTCHA popup appeared → solve_text_captcha()
  3. Neither → manual fallback

reCAPTCHA solver:
  CRITICAL: Audio downloaded from bframe context (NOT main page — CORS blocks).
  CRITICAL: Frame detection uses 'bframe' in frame.url (handles enterprise/bframe).

Xiaomi text CAPTCHA solver:
  Uses ddddocr for OCR of distorted text images.
  Popup detection: "Enter verification code" + captcha image near input.
"""

import asyncio
import base64
import os
import random
import subprocess
import time

import speech_recognition as sr

from mimo_farmer.config import AUDIO_DIR, CAPTCHA_MAX_RETRIES


async def detect_xiaomi_captcha(page) -> bool:
    """Check if Xiaomi's custom text CAPTCHA popup is visible.

    Detection signals:
    - Text "Enter verification code" or "verification code" on page
    - A captcha image element near the code input
    - A Submit button in the popup
    """
    try:
        body = await page.evaluate("document.body?.innerText || ''")
        body_lower = body.lower()
        if 'verification code' in body_lower or 'enter code' in body_lower:
            # Verify it's the popup with captcha, not the OTP page
            # Check for captcha image presence
            has_captcha_img = await page.evaluate("""
                (() => {
                    // Look for captcha image near verification popup
                    const imgs = document.querySelectorAll('img');
                    for (const img of imgs) {
                        const src = img.src || '';
                        const w = img.naturalWidth || img.width;
                        // CAPTCHA images are typically small (< 300px wide)
                        // and may be base64 or a captcha endpoint URL
                        if (w > 20 && w < 400 && w > 0) return true;
                        if (src.includes('captcha') || src.includes('verify')) return true;
                    }
                    // Check canvas elements (some CAPTCHAs use canvas)
                    const canvases = document.querySelectorAll('canvas');
                    for (const c of canvases) {
                        if (c.width > 20 && c.width < 400) return true;
                    }
                    return false;
                })()
            """)
            if has_captcha_img:
                return True

            # Fallback: check for "Submit" button + code input in a dialog-like container
            has_submit = await page.evaluate("""
                (() => {
                    const btns = document.querySelectorAll('button');
                    for (const b of btns) {
                        if (b.textContent.trim().toLowerCase() === 'submit') return true;
                    }
                    return false;
                })()
            """)
            has_code_input = await page.evaluate("""
                (() => {
                    const inputs = document.querySelectorAll('input[type="text"], input[type="number"], input:not([type])');
                    for (const inp of inputs) {
                        const ph = (inp.placeholder || '').toLowerCase();
                        if (ph.includes('code') || ph.includes('captcha')) return true;
                    }
                    return false;
                })()
            """)
            if has_submit and has_code_input:
                return True
    except Exception:
        pass
    return False




async def solve_text_captcha(page, max_retries: int = 0) -> bool:
    """Solve Xiaomi's custom text CAPTCHA — manual solve (user types in browser).

    Flow:
    1. Show message to user to solve CAPTCHA in browser
    2. Poll for popup to close (auto-detect when solved)
    3. Timeout after 120s

    Returns True if solved, False otherwise.
    """
    # Skip ddddocr auto-solve — accuracy too low for this CAPTCHA type
    # Go straight to manual solve
    return await _solve_text_captcha_manual(page)
    # Try auto-solve with ddddocr first
    try:
        import ddddocr
        ocr = ddddocr.DdddOcr(show_ad=False)
        print("  [captcha] ddddocr loaded — trying auto-solve...")

        for attempt in range(1, max_retries + 1):
            # Check if popup still there
            if not await detect_xiaomi_captcha(page):
                print("  [captcha] Popup already closed — no CAPTCHA to solve")
                return True

            # Extract CAPTCHA image bytes
            img_bytes = await _extract_captcha_image(page)
            if not img_bytes:
                print(f"  [captcha] Could not extract CAPTCHA image (attempt {attempt})")
                await asyncio.sleep(1)
                continue

            # Preprocess image for better OCR
            try:
                from PIL import Image
                import io

                img = Image.open(io.BytesIO(img_bytes)).convert('RGB')

                # Light preprocessing: grayscale + moderate threshold
                # Don't remove colored lines aggressively — raw OCR works better
                gray = img.convert('L')
                binary = gray.point(lambda x: 0 if x < 130 else 255, '1')

                buf = io.BytesIO()
                binary.save(buf, format='PNG')
                preprocessed_bytes = buf.getvalue()

                result_raw = ocr.classification(img_bytes).strip()
                result_pp = ocr.classification(preprocessed_bytes).strip()

                # Pick best: prefer 4-6 char results
                candidates = [(result_raw, 'raw'), (result_pp, 'preprocessed')]
                def score(r):
                    l = len(r)
                    if l < 2: return -100
                    if 4 <= l <= 6: return 10 + l
                    if l == 3: return 5
                    return l

                best = max(candidates, key=lambda c: score(c[0]))
                result = best[0]
                print(f"  [captcha] OCR — raw:'{result_raw}' pp:'{result_pp}' → {best[1]}:'{result}'")

            except Exception as e:
                result = ocr.classification(img_bytes)
                result = result.strip()
                print(f"  [captcha] Preprocess failed ({e}), using raw: '{result}'")

            if not result or len(result) < 2:
                print(f"  [captcha] OCR returned empty/short: '{result}' (attempt {attempt})")
                # Click reload/refresh if available
                await _click_captcha_reload(page)
                await asyncio.sleep(1)
                continue

            print(f"  [captcha] ddddocr result: '{result}' (attempt {attempt}/{max_retries})")

            # Type result into input field
            typed = await _type_captcha_answer(page, result)
            if not typed:
                print(f"  [captcha] Could not find input field (attempt {attempt})")
                continue

            # Click Submit
            submitted = await _click_captcha_submit(page)
            if not submitted:
                print(f"  [captcha] Could not click Submit (attempt {attempt})")
                continue

            # Wait for page to react
            await asyncio.sleep(3)

            # Check if CAPTCHA popup still showing → definitely wrong
            if await detect_xiaomi_captcha(page):
                print(f"  [captcha] Wrong answer — popup still showing (attempt {attempt})")
                await asyncio.sleep(1)
                continue

            # Popup gone — but is it actually solved? Check if page progressed
            progressed = await page.evaluate("""
                (() => {
                    const body = document.body?.innerText || '';
                    const url = window.location.href;
                    // OTP page indicators
                    if (body.includes('Enter the verification code')) return 'otp';
                    if (body.includes('OTP') && body.includes('input')) return 'otp';
                    if (url.includes('verify') || url.includes('otp')) return 'otp_url';
                    // Still on signup page?
                    if (body.includes('Create an account') || body.includes('Sign up')) return 'still_signup';
                    // Error message?
                    if (body.includes('incorrect') || body.includes('error') || body.includes('invalid')) return 'error';
                    // CAPTCHA error text?
                    if (body.includes('verification code error') || body.includes('wrong code')) return 'wrong_code';
                    return 'unknown';
                })()
            """)
            print(f"  [captcha] Page state after submit: {progressed}")

            if progressed in ('otp', 'otp_url'):
                print(f"  [captcha] ✅ Auto-solved! Reached OTP page ('{result}')")
                return True

            if progressed in ('still_signup', 'error', 'wrong_code'):
                print(f"  [captcha] Wrong answer ({progressed}) — retrying...")
                # Try to get new captcha image for next attempt
                await asyncio.sleep(1)
                continue

            # Unknown state — might be solved, proceed cautiously
            print(f"  [captcha] Unknown state ({progressed}) — assuming solved")
            return True

        print(f"  [captcha] ddddocr failed after {max_retries} attempts — falling back to manual")

    except ImportError:
        print("  [captcha] ddddocr not available — using manual solve")
    except Exception as e:
        print(f"  [captcha] ddddocr error: {e} — falling back to manual")

    # Fallback: manual solve
    return await _solve_text_captcha_manual(page)


async def _extract_captcha_image(page) -> bytes | None:
    """Extract CAPTCHA image bytes from the Xiaomi verification popup.

    Tries multiple strategies:
    1. Find img with captcha/verify src near verification popup
    2. Find small img (20-400px) in a dialog/popup context
    3. Find canvas element with captcha content

    Returns raw image bytes or None.
    """
    try:
        # Strategy 1: Find img with captcha-related attributes
        img_bytes = await page.evaluate("""
            (() => {
                const imgs = document.querySelectorAll('img');
                for (const img of imgs) {
                    const src = img.src || '';
                    const w = img.naturalWidth || img.width;
                    const h = img.naturalHeight || img.height;
                    // CAPTCHA images: small, captcha-related src
                    if (w > 30 && w < 400 && h > 15 && h < 200) {
                        if (src.includes('captcha') || src.includes('verify') || src.includes('data:image')) {
                            return src;
                        }
                    }
                }
                // Strategy 2: Any small image in a dialog/popup
                const dialogs = document.querySelectorAll('dialog, [role="dialog"], .ant-modal, .popup, [class*="captcha"], [class*="verify"]');
                for (const d of dialogs) {
                    const dimgs = d.querySelectorAll('img');
                    for (const img of dimgs) {
                        const w = img.naturalWidth || img.width;
                        if (w > 30 && w < 400) {
                            return img.src;
                        }
                    }
                }
                // Strategy 3: Any base64 image that looks like captcha
                for (const img of imgs) {
                    const src = img.src || '';
                    if (src.startsWith('data:image') && src.length > 500) {
                        const w = img.naturalWidth || img.width;
                        if (w > 30 && w < 400) return src;
                    }
                }
                return null;
            })()
        """)

        if not img_bytes:
            # Fallback: screenshot the captcha image element directly
            for selector in [
                'img[src*="captcha"]',
                'img[src*="verify"]',
                '[class*="captcha"] img',
                '[class*="verify"] img',
                'dialog img',
                '[role="dialog"] img',
            ]:
                try:
                    el = page.locator(selector).first
                    if await el.count() > 0:
                        screenshot_bytes = await el.screenshot()
                        if screenshot_bytes and len(screenshot_bytes) > 100:
                            return screenshot_bytes
                except Exception:
                    continue
            return None

        # Convert data URL or URL to bytes
        if img_bytes.startswith('data:image'):
            import base64
            _, b64data = img_bytes.split(',', 1)
            return base64.b64decode(b64data)
        else:
            # It's a URL — fetch it via page context
            fetched = await page.evaluate("""
                async (url) => {
                    try {
                        const resp = await fetch(url);
                        const blob = await resp.blob();
                        return new Promise(r => {
                            const reader = new FileReader();
                            reader.onloadend = () => r(reader.result);
                            reader.readAsDataURL(blob);
                        });
                    } catch(e) { return null; }
                }
            """, img_bytes)
            if fetched and 'base64,' in fetched:
                import base64
                return base64.b64decode(fetched.split('base64,')[1])
    except Exception as e:
        print(f"  [captcha] Image extraction error: {e}")

    return None


async def _type_captcha_answer(page, text: str) -> bool:
    """Type CAPTCHA answer into the input field."""
    try:
        # Look for input near verification code text
        for selector in [
            'input[placeholder*="code" i]',
            'input[placeholder*="captcha" i]',
            'input[placeholder*="verification" i]',
            'dialog input[type="text"]',
            '[role="dialog"] input[type="text"]',
            '[class*="captcha"] input',
            '[class*="verify"] input',
        ]:
            el = page.locator(selector).first
            if await el.count() > 0:
                await el.fill('')
                await asyncio.sleep(0.2)
                await el.type(text, delay=80)
                return True
    except Exception:
        pass
    return False


async def _click_captcha_submit(page) -> bool:
    """Click Submit button in CAPTCHA popup."""
    try:
        for selector in [
            'button:has-text("Submit")',
            'button:has-text("Confirm")',
            'button:has-text("Verify")',
            'dialog button[type="submit"]',
            '[role="dialog"] button:has-text("Submit")',
        ]:
            el = page.locator(selector).first
            if await el.count() > 0:
                await el.click(timeout=3000)
                return True
    except Exception:
        pass
    return False


async def _click_captcha_reload(page) -> bool:
    """Click reload/refresh button to get new CAPTCHA image."""
    try:
        for selector in [
            'button:has-text("Refresh")',
            'button:has-text("Reload")',
            '[class*="captcha"] button:has-text("refresh" i)',
            'button[aria-label*="refresh" i]',
            'button[aria-label*="reload" i]',
        ]:
            el = page.locator(selector).first
            if await el.count() > 0:
                await el.click(timeout=2000)
                return True
    except Exception:
        pass
    return False


async def _solve_text_captcha_manual(page) -> bool:
    """Fallback: manual CAPTCHA solving by user."""
    print()
    print("  " + "=" * 50)
    print("  [captcha] XIAOMI TEXT CAPTCHA — MANUAL SOLVE")
    print("  [captcha] Please solve the CAPTCHA in the browser window.")
    print("  [captcha] Type the code & click Submit yourself.")
    print("  [captcha]")
    print("  [captcha] Waiting for popup to close...")
    print("  " + "=" * 50)
    print()

    MAX_WAIT = 120
    elapsed = 0
    while elapsed < MAX_WAIT:
        if not await detect_xiaomi_captcha(page):
            print("  [captcha] Popup closed — CAPTCHA solved!")
            return True
        await asyncio.sleep(2)
        elapsed += 2
        if elapsed % 10 == 0:
            print(f"  [captcha] Still waiting... ({elapsed}s / {MAX_WAIT}s)")

    print("  [captcha] Timeout waiting for manual solve")
    return False


# Word-to-digit normalization map
WORD_TO_DIGIT = {
    'zero': '0', 'one': '1', 'two': '2', 'three': '3', 'four': '4',
    'five': '5', 'six': '6', 'seven': '7', 'eight': '8', 'nine': '9',
    'ten': '10', 'eleven': '11', 'twelve': '12', 'thirteen': '13',
    'fourteen': '14', 'fifteen': '15', 'sixteen': '16',
    'seventeen': '17', 'eighteen': '18', 'nineteen': '19', 'twenty': '20',
}


def normalize_captcha_text(text: str) -> str:
    """Convert spoken words to digits, strip filler words."""
    if not text:
        return text
    result = text.lower().strip()
    for word, digit in WORD_TO_DIGIT.items():
        result = result.replace(word, digit)
    for filler in ['please', 'the', 'and', 'uh', 'um', 'er', '.']:
        result = result.replace(filler, '')
    return result.strip().replace('  ', ' ')


async def detect_audio_challenge_available(bframe) -> bool:
    """Check if audio challenge is available in the reCAPTCHA bframe.

    Returns True if audio button exists and no blocking error detected.
    Returns False if only image challenge is available (audio blocked).

    Detection:
    - Checks if #recaptcha-audio-button exists
    - Checks for error messages about "automated" or "Try again later"
      which indicate audio challenge is blocked
    """
    try:
        # Check if audio button exists
        audio_btn = bframe.locator('#recaptcha-audio-button')
        audio_btn_exists = (await audio_btn.count()) > 0

        if not audio_btn_exists:
            print("  [captcha] No audio button found — image challenge only")
            return False

        # Check for blocking error messages
        error_msg = await bframe.evaluate("""
            (() => {
                // Check for error message about automated access
                const errMsgs = document.querySelectorAll(
                    '.rc-doscaptcha-body-text, .rc-audiochallenge-error-message, .rc-doscaptcha-header-text'
                );
                for (const el of errMsgs) {
                    const text = (el.textContent || '').toLowerCase();
                    if (text.includes('automated') || text.includes('try again later')) {
                        return text.trim();
                    }
                }
                return '';
            })()
        """)

        if error_msg:
            print(f"  [captcha] Audio blocked: {error_msg}")
            return False

        print("  [captcha] Audio challenge available")
        return True

    except Exception as e:
        print(f"  [captcha] Audio detection error: {e}")
        return False


async def solve_recaptcha(page, max_retries: int = CAPTCHA_MAX_RETRIES) -> bool:
    """Audio-based reCAPTCHA v2 solver.

    Steps:
    1. Find anchor frame (recaptcha anchor)
    2. Click checkbox — check auto-pass
    3. Find bframe challenge (CRITICAL: uses 'bframe' in frame.url)
    4. Detect if audio challenge is available
    5. If audio available: switch to audio challenge, solve via STT
    6. If audio NOT available: pause for manual image solving

    Returns True if solved, False otherwise.
    """
    os.makedirs(AUDIO_DIR, exist_ok=True)

    print("  [captcha] Waiting for reCAPTCHA to load...")

    # Find anchor frame with retry (up to 15s)
    anchor = None
    for _ in range(15):
        for frame in page.frames:
            if 'anchor' in frame.url and 'recaptcha' in frame.url:
                anchor = frame
                break
        if anchor:
            break
        await asyncio.sleep(1)

    if not anchor:
        print("  [!] No reCAPTCHA anchor frame found after 15s")
        # Debug: show all frame URLs
        for i, frame in enumerate(page.frames):
            url_short = frame.url[:100] if frame.url else "(empty)"
            print(f"    frame[{i}]: {url_short}")
        return False

    # Click checkbox
    print("  [captcha] Clicking checkbox...")
    try:
        await anchor.locator('#recaptcha-anchor').click(timeout=10000)
    except Exception as e:
        if 'detached' in str(e).lower():
            print("  [captcha] Frame detached after click (solved!)")
            return True
        print(f"  [!] Click error: {e}")
        return False
    await asyncio.sleep(2)

    # Check auto-pass
    try:
        checked = await anchor.evaluate(
            "document.getElementById('recaptcha-anchor').getAttribute('aria-checked')"
        )
        if checked == 'true':
            print("  [captcha] Auto-passed!")
            return True
    except Exception:
        print("  [captcha] Frame detached (solved!)")
        return True

    print("  [captcha] Challenge appeared, checking audio availability...")

    # Find challenge frame — CRITICAL: look for 'bframe' in frame.url
    bframe = None
    for frame in page.frames:
        if 'bframe' in frame.url and frame != anchor:
            bframe = frame
            break
    if not bframe:
        print("  [!] No challenge frame")
        return False

    # Detect if audio challenge is available
    audio_available = await detect_audio_challenge_available(bframe)

    if not audio_available:
        # Only image challenge available — need manual solving
        print()
        print("  " + "=" * 50)
        print("  [captcha] AUDIO CHALLENGE NOT AVAILABLE")
        print("  [captcha] Image challenge detected — requires manual solving.")
        print("  [captcha] Please solve the CAPTCHA in the browser window.")
        print("  [captcha] Press ENTER here when done...")
        print("  " + "=" * 50)
        print()
        input()

        # Check if solved after manual intervention
        try:
            checked = await anchor.evaluate(
                "document.getElementById('recaptcha-anchor').getAttribute('aria-checked')"
            )
            if checked == 'true':
                print("  [captcha] Solved manually!")
                return True
        except Exception:
            print("  [captcha] Frame detached after manual solve (solved!)")
            return True

        print("  [!] Manual solve did not complete")
        return False

    # Audio challenge IS available — use automated solver
    await bframe.locator('#recaptcha-audio-button').click()
    await asyncio.sleep(1.5)

    for attempt in range(max_retries):
        # Check if already solved
        try:
            checked = await anchor.evaluate(
                "document.getElementById('recaptcha-anchor').getAttribute('aria-checked')"
            )
            if checked == 'true':
                print(f"  [captcha] Solved on attempt {attempt}!")
                return True
        except Exception:
            print(f"  [captcha] Frame detached (solved!) on attempt {attempt}")
            return True

        # Get audio source URL from bframe context
        audio_url = await bframe.evaluate("document.querySelector('#audio-source')?.src || null")
        if not audio_url:
            err = await bframe.evaluate(
                "document.querySelector('.rc-audiochallenge-error-message')?.textContent?.trim() || ''"
            )
            if 'automated' in err.lower():
                print(f"  [!] Rate limited: {err}")
                return False
            try:
                await bframe.locator('#recaptcha-reload-button').click()
                await asyncio.sleep(1.5)
            except Exception:
                pass
            continue

        # CRITICAL: Download audio from bframe context (NOT main page — CORS blocks)
        audio_b64 = await bframe.evaluate("""
            async (url) => {
                try {
                    const resp = await fetch(url);
                    const blob = await resp.blob();
                    return new Promise(r => {
                        const reader = new FileReader();
                        reader.onloadend = () => r(reader.result);
                        reader.readAsDataURL(blob);
                    });
                } catch(e) { return 'ERROR:' + e.message; }
            }
        """, audio_url)

        if not audio_b64 or audio_b64.startswith('ERROR:'):
            continue

        if "base64," in audio_b64:
            audio_b64 = audio_b64.split("base64,")[1]

        audio_bytes = base64.b64decode(audio_b64)
        mp3_path = os.path.join(AUDIO_DIR, f"captcha_{int(time.time())}.mp3")
        wav_path = mp3_path.replace('.mp3', '.wav')

        with open(mp3_path, "wb") as f:
            f.write(audio_bytes)

        # Convert MP3 → WAV via ffmpeg
        try:
            subprocess.run(
                ['ffmpeg', '-y', '-i', mp3_path, '-ar', '16000', '-ac', '1', '-f', 'wav', wav_path],
                capture_output=True, timeout=10
            )
        except Exception as e:
            print(f"  [!] ffmpeg error: {e}")
            continue

        # Transcribe with free Google STT
        recognizer = sr.Recognizer()
        try:
            with sr.AudioFile(wav_path) as source:
                audio_data = recognizer.record(source)
            text = recognizer.recognize_google(audio_data, language="en-US")
            normalized = normalize_captcha_text(text)
            print(f"  [captcha] STT: '{text}' -> '{normalized}'")
        except Exception as e:
            print(f"  [!] STT failed: {e}")
            try:
                await bframe.locator('#recaptcha-reload-button').click()
                await asyncio.sleep(1.5)
            except Exception:
                pass
            continue

        # Type answer with human-like delays
        response = bframe.locator('#audio-response')
        await response.fill('')
        await asyncio.sleep(random.uniform(0.1, 0.3))
        for char in normalized:
            await response.type(char, delay=random.randint(50, 120))
            await asyncio.sleep(random.uniform(0.02, 0.08))

        await asyncio.sleep(random.uniform(0.3, 0.6))
        verify_btn = bframe.locator('#recaptcha-verify-button')
        try:
            await verify_btn.scroll_into_view_if_needed(timeout=3000)
            await verify_btn.click(force=True, timeout=5000)
        except Exception:
            # Fallback: JS click
            await bframe.evaluate('document.getElementById("recaptcha-verify-button")?.click()')
        await asyncio.sleep(2)

    print(f"  [!] Failed after {max_retries} attempts")
    return False
