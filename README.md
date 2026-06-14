<p align="center">
  <img src="docs/banner.png" alt="mimo-farmer" width="100%">
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.10+-3776AB.svg?style=for-the-badge&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/version-2.0.0-00ff88.svg?style=for-the-badge" alt="Version">
  <img src="https://img.shields.io/badge/license-MIT-green.svg?style=for-the-badge" alt="License">
  <img src="https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg?style=for-the-badge" alt="Platform">
</p>

<p align="center">
  <b>Automated Xiaomi MiMo account creation with referral bonuses, reCAPTCHA v2 audio bypass, and API key extraction.</b><br>
  <sub>~160 seconds per account | $2.72 referral bonus | 100% automated pipeline</sub>
</p>

---

## Demo

<p align="center">
  <img src="docs/demo.png" alt="mimo-farmer demo" width="100%">
</p>

## Features

| Feature | Description |
|---------|-------------|
| 🎙 **reCAPTCHA v2 Audio Solver** | Free Google SpeechRecognition STT — no paid API needed |
| 📧 **Auto OTP** | generator.email integration with auto-polling and body code extraction |
| 🔐 **Identity Verification** | Handles Xiaomi's double-OTP verification automatically |
| 📋 **Terms Dialog** | Handles React/Ant Design checkbox + Confirm via trusted click events |
| 🎁 **Referral Codes** | Automatic referral code binding via UI flow |
| 🛡 **Risk Control Detection** | Detects flagged accounts, stops batch, suggests new referral code |
| 💰 **Balance Verification** | Confirms $2.72 referral bonus before proceeding |
| 🔑 **API Key Extraction** | Network intercept + clipboard fallback for full unmasked keys |
| 🔀 **Random Passwords** | Unique password per account (anti-bot detection) |
| ⚡ **Fast Mode** | Reduced delays for quicker creation |
| 🔄 **Parallel Mode** | Multiple browser instances simultaneously |
| 📦 **Batch Output** | Combined `[N] Mail/Pw/Api-Key` format for easy copy |

## Pipeline

<p align="center">
  <img src="docs/pipeline.png" alt="mimo-farmer pipeline" width="100%">
</p>

### Step-by-step

1. **Navigate** — Opens Xiaomi signup page via Patchright (anti-detect Playwright)
2. **Fill Form** — Random email (banri.xyz) + random password (12 chars)
3. **reCAPTCHA v2** — Clicks checkbox, detects audio challenge, downloads MP3 from bframe context, converts via ffmpeg, transcribes via Google free STT
4. **OTP** — Polls generator.email inbox for 6-digit verification code
5. **Identity Verification** — Handles Xiaomi's second OTP (Send → wait → enter code)
6. **Terms Dialog** — Clicks `input[type="checkbox"]` (trusted event that React recognizes) + Confirm
7. **Cookie Clear** — Prevents "own invitation code" error from stale sessions
8. **Balance Page** — Navigates to MiMo platform (auto-login via Xiaomi session)
9. **Referral** — Enters referral code via UI input fields
10. **Risk Control** — Detects if account is flagged; stops batch if detected
11. **Balance Verify** — Confirms $2.72 via regex extraction
12. **API Key** — Creates key, captures full 51-char key via network intercept (fallback: clipboard)
13. **Save** — Credentials saved as `.txt` and `.json` in `accounts/`

## Installation

```bash
# Clone the repo
git clone https://github.com/rapoii/mimo-farmer.git
cd mimo-farmer

# Install Python dependencies
pip install -e .

# Install ffmpeg (required for audio conversion)
# Windows:
winget install ffmpeg
# macOS:
brew install ffmpeg
# Linux:
sudo apt install ffmpeg

# Install Patchright browser (anti-detect Chromium)
python -m patchright install chromium
```

### Requirements

- Python 3.10+ (3.12 recommended)
- ffmpeg (system dependency)
- Patchright (auto-installed with pip)

## Usage

### Interactive Mode

```bash
mimo create
# Prompts for referral code and account count
```

### Command-Line Mode

```bash
# Single account
mimo create --referral ABC123 --count 1

# Multiple accounts
mimo create --referral ABC123 --count 5

# Fast mode (reduced delays)
mimo create --referral ABC123 --count 3 --fast

# Parallel browser instances
mimo create --referral ABC123 --count 10 --parallel 3

# All options combined
mimo create --referral ABC123 --count 10 --parallel 3 --fast
```

### Account Management

```bash
# List all created accounts
mimo accounts

# Export credentials to JSON
mimo export

# Export to text format
mimo export --format text

# Custom output path
mimo export --output my_accounts.json
```

### Output Format

```
[1]
Mail: abc123@banri.xyz
Pw: MmRai9ILb2!9
Api-Key: sk-s47bzoi...a2avasrip8 (51 chars)

[2]
Mail: def456@banri.xyz
Pw: MmKp3Xnq7!9
Api-Key: sk-t98abcd...xyz12345 (51 chars)
```

> **Note:** API keys are only saved to local files — they are never transmitted anywhere.

## Configuration

### Default Settings

| Setting | Default | Description |
|---------|---------|-------------|
| Referral Code | `FHAZMU` | Default referral code |
| Email Domain | `banri.xyz` | Only working domain (Xiaomi blocks others) |
| Password | Random 12 chars | `Mm` + 8 random + `!9` (anti-bot) |
| Browser | Patchright | Anti-detect Playwright (Chromium) |

### Working Referral Codes

Referral codes may expire after heavy use. If you get "risk control" errors, create a new code:

```bash
# Check if code is working
mimo create --referral YOURCODE --count 1
```

### Email Domains

Xiaomi blocks most temporary email domains. Currently only `banri.xyz` (via generator.email) works reliably. Other domains may work intermittently.

## Architecture

```
mimo-farmer/
├── mimo_farmer/
│   ├── __init__.py       # Package version
│   ├── __main__.py       # Entry point (python -m mimo_farmer)
│   ├── cli.py            # Argparse CLI (create, accounts, export)
│   ├── creator.py        # Core 14-step account creation pipeline
│   ├── captcha.py        # reCAPTCHA v2 audio solver + fallback
│   ├── email_handler.py  # generator.email OTP polling
│   └── config.py         # Default settings + constants
├── docs/
│   ├── banner.png        # Project banner
│   ├── demo.png          # Terminal demo screenshot
│   └── pipeline.png      # Pipeline diagram
├── accounts/             # Generated credentials (gitignored)
├── README.md
├── LICENSE               # MIT License
├── requirements.txt
└── setup.py
```

### Key Technical Decisions

| Decision | Why |
|----------|-----|
| **Patchright** over Playwright | Anti-detect fingerprint avoids bot detection |
| **Audio challenge** over image | Free Google STT > paid captcha services |
| **Network intercept** for API keys | `input[disabled].value` returns masked key |
| **`input[type="checkbox"]`** click | Trusted event that React recognizes (label click doesn't work) |
| **Cookie clearing** between phases | Prevents "own invitation code" from stale sessions |
| **Random 12-char passwords** | Xiaomi max 16 chars; longer passwords silently rejected |

## Troubleshooting

### reCAPTCHA not loading

If reCAPTCHA iframe doesn't appear after clicking Next:

1. **Password too long** — Xiaomi max 16 chars. Password is auto-generated at 12 chars, but if you override with `--password`, keep it ≤16.
2. **IP flagged** — Wait 30-60 minutes or switch IP (VPN/mobile hotspot).
3. **Patchright detected** — Rare, but can happen. Try again later.

### "Risk control restrictions" error

Xiaomi flags accounts after multiple signups from same IP. Solutions:

1. **Create new referral code** — Old codes get flagged
2. **Switch IP** — Mobile hotspot or residential VPN
3. **Wait** — IP cooldown takes 1-2 hours

### API key shows masked (asterisks)

This means the Xiaomi API returned a masked key in the network response. The tool automatically falls back to clipboard copy button. If both fail, the key will show as masked in the output file — re-run to get a fresh key.

### Identity verification timeout

Xiaomi requires a second OTP for identity verification. The tool waits up to 180 seconds. If it times out:

1. Check if generator.email is accessible
2. The email domain may be rate-limited — wait 10-15 minutes
3. Try a different email domain if available

### Terms dialog checkbox not working

The Terms dialog uses React/Ant Design. The tool clicks the actual `<input type="checkbox">` element (trusted event) instead of the label. If Confirm stays disabled:

1. The dialog may not have fully rendered — the tool retries automatically
2. If persistent, Xiaomi may have changed the dialog structure

## Changelog

### v2.0.1 (2026-06-15)
- **Random passwords** — Each account gets unique 12-char password (anti-bot detection)
- **API key fix** — Detects masked keys from API response, falls back to clipboard + DOM scan
- **Risk control batch stop** — Stops remaining accounts when risk control detected
- **Password length fix** — 12 chars (was 18, exceeded Xiaomi's 16-char max)
- **Verify button fix** — force=True click + JS fallback for reCAPTCHA verify
- **CLI args fix** — `--referral` and `--count` properly override interactive prompts
- **Faster terms dialog** — Reduced sleep times, 6s vs 70-99s previously
- **Debug output** — Frame URL logging when reCAPTCHA not found

### v2.0.0 (2026-06-14)
- Audio challenge detection with manual fallback
- Risk control detection
- Cookie clearing fix
- Terms dialog handling at every page navigation
- Network intercept for API key capture
- Combined batch output format

### v1.0.0 (2026-06-13)
- Initial release

## Legal Disclaimer

This tool is for **educational and research purposes only**. Users are responsible for compliance with Xiaomi's Terms of Service and applicable laws. The authors are not responsible for any misuse.

## License

[MIT](LICENSE)

---

<p align="center">
  <sub>Built with ❤️ and Python</sub>
</p>
