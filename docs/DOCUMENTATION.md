# mimo-farmer Documentation

## Table of Contents

- [Overview](#overview)
- [How It Works](#how-it-works)
- [reCAPTCHA v2 Audio Solver](#recaptcha-v2-audio-solver)
- [Email Handling](#email-handling)
- [Terms Dialog](#terms-dialog)
- [API Key Extraction](#api-key-extraction)
- [Risk Control](#risk-control)
- [Configuration](#configuration)
- [CLI Reference](#cli-reference)
- [API Reference](#api-reference)
- [FAQ](#faq)

---

## Overview

mimo-farmer automates the Xiaomi MiMo account creation pipeline. Each account receives:
- **$0.72** sign-up bonus (automatic)
- **$2.00** referral bonus (if referral code works)
- **API key** for MiMo's AI platform

The tool handles all browser automation, CAPTCHA solving, email verification, and credential extraction.

---

## How It Works

### Pipeline Phases

| Phase | Duration | Description |
|-------|----------|-------------|
| 1. Navigate | 4s | Open Xiaomi signup URL via Patchright |
| 2. Fill Form | 1.5s | Enter random email + password |
| 3. reCAPTCHA | 17s | Audio challenge → Google STT |
| 4. OTP Wait | 11s | Poll generator.email for code |
| 5. OTP Entry | 4s | Type 6-digit code |
| 6. Identity Verify | 81s | Second OTP (Xiaomi security) |
| 7. Terms Dialog | 6s | Checkbox + Confirm (React fix) |
| 8. Cookie Clear | <1s | Prevent stale session |
| 9. Balance Page | 7s | Navigate to MiMo platform |
| 10. Referral | 9s | Enter referral code |
| 11. Risk Check | <1s | Detect if flagged |
| 12. Balance Verify | 2s | Confirm $2.72 |
| 13. API Key | 17s | Create + extract full key |
| 14. Save | <1s | Write credentials to file |

**Total: ~160 seconds per account**

### Browser: Patchright

[Patchright](https://github.com/Kaliiiiiiiiii-Vinyzu/patchright) is a fork of Playwright with anti-detection patches. It:
- Removes `navigator.webdriver` flag
- Patches Chrome DevTools Protocol detection
- Randomizes browser fingerprint
- Mimics real user behavior

This is critical because Xiaomi's anti-bot system detects regular Playwright/Selenium.

---

## reCAPTCHA v2 Audio Solver

### How It Works

1. **Frame Detection** — Finds `recaptcha/anchor` frame (up to 15s retry)
2. **Checkbox Click** — Clicks `#recaptcha-anchor` in anchor frame
3. **Auto-pass Check** — If `aria-checked=true`, CAPTCHA solved without challenge
4. **Challenge Detection** — Finds `enterprise/bframe` frame
5. **Audio Switch** — Clicks `#recaptcha-audio-button` to switch to audio challenge
6. **Audio Download** — Fetches MP3 from bframe context (NOT main page — CORS blocks)
7. **Conversion** — ffmpeg converts MP3 → WAV (16kHz mono)
8. **Transcription** — `speech_recognition.recognize_google()` (free web API)
9. **Normalization** — Converts number words ("twenty one" → "21")
10. **Submit** — Types answer + clicks Verify (force=True + JS fallback)

### Why Audio Instead of Image?

| Method | Cost | Accuracy | Speed |
|--------|------|----------|--------|
| Audio + Google STT | Free | ~90% | 15-20s |
| Image + ML model | Free | ~60% | 10s |
| 2captcha/capsolver | $0.003/solve | ~95% | 10s |
| Manual | Free | 100% | Varies |

Audio is the best balance of cost (free) and accuracy.

### Troubleshooting

- **"No reCAPTCHA found"** — Password too long (max 16 chars), or IP flagged
- **"Audio not available"** — Image-only challenge; pauses for manual solve
- **"Verify button timeout"** — Fixed in v2.0.1 with force=True + JS fallback

---

## Email Handling

### generator.email

The tool uses [generator.email](https://generator.email) for temporary email addresses:

1. **Domain Selection** — Only `banri.xyz` works reliably (Xiaomi blocks others)
2. **Email Generation** — Random username + `@banri.xyz`
3. **OTP Polling** — Refreshes inbox every 3-5 seconds
4. **Body Extraction** — Clicks email rows to read body content (codes not visible in table)
5. **Code Parsing** — Regex extracts 6-digit code from email body

### Rate Limiting

Xiaomi rate-limits temp email domains after 2-3 signups. If OTP doesn't arrive:
- Wait 10-15 minutes
- Try a different domain (if available)
- Switch IP

---

## Terms Dialog

### The Problem

Xiaomi's Terms dialog uses React/Ant Design with a checkbox that:
- Ignores `force=True` Playwright clicks (untrusted events)
- Ignores JS `.checked = true` (React state not updated)
- Only responds to native `input[type="checkbox"]` click (trusted event)

### The Solution

```python
# WRONG — label click (untrusted, React ignores)
await page.locator('label.ant-checkbox-wrapper').click(force=True)

# RIGHT — input click (trusted, React recognizes)
await page.locator('input[type="checkbox"]').click()
```

The tool clicks the actual `<input>` element, which sends a trusted browser event that React's synthetic event system recognizes, properly updating internal state and enabling the Confirm button.

---

## API Key Extraction

### The Problem

Xiaomi shows API keys in two places:
1. **Network response** — Returns masked key with `****` asterisks
2. **`input[disabled].value`** — Returns masked key with `...` dots

Neither gives the full 51-character key directly.

### The Solution

The tool uses a 3-tier fallback:

1. **Network Intercept** — Captures POST response from `/api/v1/api-keys/create`
   - Checks for `*` characters in captured key
   - If masked, falls through to next method

2. **Clipboard Copy** — Clicks the Copy button in the success dialog
   - `navigator.clipboard.readText()` returns full unmasked key
   - Validates: starts with `sk-`, length ≥ 40, no asterisks

3. **DOM Scan** — Searches all visible elements for full `sk-` key
   - Checks `code`, `pre`, `span`, `div`, `p`, `td` elements
   - Filters: starts with `sk-`, length ≥ 40, no `*` or `...`

---

## Risk Control

### What Is It?

Xiaomi flags accounts after multiple signups from the same IP. When flagged:
- Referral code binding silently fails
- Balance stays at $0.72 (no $2 referral bonus)
- Error message: "Your account has risk control restrictions"

### Detection

The tool checks for "risk control" text on the balance page after entering the referral code.

### Response

When risk control is detected:
1. Account is still created (with $0.72 balance)
2. Batch stops immediately
3. Message: "Create a NEW referral code and try again"

### Prevention

- **Rotate referral codes** — Don't use same code for 10+ accounts
- **Switch IPs** — Mobile hotspot or residential VPN
- **Space out signups** — Wait 5-10 minutes between accounts

---

## Configuration

### config.py

```python
DEFAULT_REFERRAL_CODE = "FHAZMU"
DEFAULT_PASSWORD = None  # Random per account
SIGNUP_URL = "https://global.account.xiaomi.com/fe/service/register?..."
EMAIL_DOMAIN = "banri.xyz"
OTP_TIMEOUT = 180  # seconds
CAPTCHA_MAX_RETRIES = 3
```

### Environment Variables

None required. All configuration is in `config.py` or via CLI arguments.

---

## CLI Reference

### `mimo create`

Create MiMo accounts.

```
Usage: mimo create [OPTIONS]

Options:
  -r, --referral CODE   Referral code (prompted if not provided)
  -n, --count N         Number of accounts (prompted if not provided)
  -f, --fast            Fast mode — reduced delays
  -p, --parallel N      Parallel browser instances
```

### `mimo accounts`

List all created accounts from `accounts/` directory.

### `mimo export`

Export credentials to file.

```
Usage: mimo export [OPTIONS]

Options:
  -o, --output PATH     Output file path
  --format FORMAT       json (default) or text
```

---

## API Reference

### `create_account()`

```python
async def create_account(
    referral_code: str = DEFAULT_REFERRAL_CODE,
    password: str = DEFAULT_PASSWORD,
    fast: bool = False,
    account_num: int = 0,
) -> dict | None
```

Returns:
```python
{
    "email": "abc123@banri.xyz",
    "password": "MmRai9ILb2!9",
    "balance": "$2.72",
    "referral": "985C86",
    "api_key": "sk-s47bzoi...a2avasrip8",  # 51 chars, full
    "risk_control": False,
    "created": "2026-06-15 03:00:24",
    "method": "cli_auto"
}
```

Returns `None` if creation fails.

### `solve_recaptcha()`

```python
async def solve_recaptcha(page, max_retries: int = 3) -> bool
```

Returns `True` if CAPTCHA solved, `False` otherwise.

### `detect_risk_control()`

```python
async def detect_risk_control(page) -> bool
```

Returns `True` if "risk control" text found on page.

---

## FAQ

**Q: Why banri.xyz only?**
A: Xiaomi blocks most temp email domains. `banri.xyz` is the only domain that consistently receives verification emails.

**Q: Why random passwords?**
A: Using the same password for all accounts is a bot detection signal. Random 12-char passwords (letters + digits + symbols) avoid this.

**Q: Why 12 chars and not 16?**
A: Xiaomi's max is 16 chars. Using 12 leaves headroom and avoids edge cases with special character encoding.

**Q: Can I use this with my own Xiaomi account?**
A: The tool creates NEW accounts. It doesn't modify existing accounts.

**Q: Why does identity verification take so long?**
A: Xiaomi requires a second OTP sent to the same email. The tool waits for this email, which can take 60-90 seconds.

**Q: What happens if reCAPTCHA changes?**
A: The audio solver is based on reCAPTCHA v2's standard audio challenge interface. If Google changes the interface, the solver may need updates.
