"""reCAPTCHA v2 Audio Solver — uses free Google SpeechRecognition.

CRITICAL: Audio downloaded from bframe context (NOT main page — CORS blocks).
CRITICAL: Frame detection uses 'bframe' in frame.url (handles enterprise/bframe).
"""

import asyncio
import base64
import os
import random
import subprocess
import time

import speech_recognition as sr

from mimo_farmer.config import AUDIO_DIR, CAPTCHA_MAX_RETRIES


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
