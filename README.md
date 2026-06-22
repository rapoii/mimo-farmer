<p align="center">
  <img src="docs/banner_chatgpt.png" alt="mimo-farmer" width="100%">
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.10+-3776AB.svg?style=for-the-badge&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/version-2.2.0-00ff88.svg?style=for-the-badge" alt="Version">
  <img src="https://img.shields.io/badge/license-MIT-green.svg?style=for-the-badge" alt="License">
  <img src="https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg?style=for-the-badge" alt="Platform">
</p>

<p align="center">
  <b>Automated Xiaomi MiMo account creation with referral bonuses, CDP anti-detect browser, and API key extraction.</b><br>
  <sub>Auto-farm target balance | CDP mode (Chrome DevTools Protocol) | ADB IP rotation | 14-layer anti-detect | reCAPTCHA audio bypass</sub>
</p>

---

## ✨ Features

### 🎯 Core Features

| Feature | Description |
|---------|-------------|
| 🎯 **Auto-Farm Mode** | Create accounts until target balance reached (e.g., $20) |
| 🔄 **Siklus Mode** | Auto-create 1 main + 5 children per cycle — 6 accounts, $14.32 per cycle |
| 🌐 **CDP Mode (Default)** | Chrome DevTools Protocol — uses real Chrome browser, zero automation detect |
| 🎙 **reCAPTCHA v2 Audio Solver** | Free Google STT — no paid API needed |
| 🖊 **Manual Xiaomi CAPTCHA** | Text CAPTCHA shown to user for manual solve |
| 📧 **Auto OTP** | generator.email integration with auto-polling |
| 🔐 **Identity Verification** | Handles Xiaomi's double-OTP verification automatically |
| 📋 **Terms Dialog** | React/Ant Design checkbox fix via trusted click events |
| 🎁 **Referral Codes** | Automatic referral code binding via UI flow |
| 🛡 **Risk Control Detection** | Detects flagged accounts, stops batch |
| 💰 **Balance Verification** | Confirms $2.72 referral bonus |
| 🔑 **API Key Extraction** | Network intercept + clipboard fallback |
| 📦 **Batch Output** | Single `batch_*.txt` file with all credentials |
| ⚡ **Fast Mode** | Reduced delays for quicker creation |
| 🔄 **Parallel Mode** | Multiple browser instances simultaneously |
| ♾️ **Continuous Mode** | Keep creating until risk control detected |

### 🔒 Advanced Anti-Detect (14 Layers)

| # | Layer | Description |
|---|-------|-------------|
| 1 | **CDP Mode** | Real Chrome browser — `navigator.webdriver = false` naturally |
| 2 | **User Agent** | Randomized from pool of 10 real Chrome UAs |
| 3 | **Viewport** | Randomized common resolutions (1920x1080, 1366x768, etc.) |
| 4 | **Timezone** | Auto-detected from locale |
| 5 | **WebGL** | Full parameter spoofing (vendor, renderer, MAX_TEXTURE_SIZE, etc.) |
| 6 | **Canvas Noise** | Seeded deterministic noise (consistent per profile) |
| 7 | **AudioContext** | Deterministic buffer spoofing |
| 8 | **Navigator.connection** | Spoof network info (4g, downlink, rtt) |
| 9 | **Battery API** | Spoof battery level, charging status |
| 10 | **WebRTC** | Block IP leak behind VPN/proxy |
| 11 | **Screen Properties** | Spoof colorDepth, pixelDepth |
| 12 | **Font Fingerprint** | Platform-specific font filtering |
| 13 | **Hardware** | Spoof hardwareConcurrency, deviceMemory |
| 14 | **Human Behavior** | Bezier-curve mouse, variable typing speed |

### 🌐 IP Rotation Methods

| Method | Description | Speed |
|--------|-------------|-------|
| **ADB Airplane** | Toggle airplane mode via Android USB | ~15s |
| **ADB Data** | Toggle mobile data via Android USB | ~8s |
| **Free Proxy** | Auto-rotate from 7 sources (~7,700 proxies) | Variable |
| **Manual VPN** | Prompt user to change IP manually | Manual |

### 🎯 Smart Features

- **Ctrl+C Handler** — Save progress when interrupted
- **IP Check** — Show current IP before start and after rotation
- **Random Delay** — 40-60s between accounts (anti-detection)
- **Parent Bonus Tracking** — Accurately count $2 bonus per child to parent
- **Child Optimization** — Skip extract referral code for child accounts (save 4-5s per account)

## 📋 Pipeline

1. **Anti-Detect Setup** — CDP mode with real Chrome browser or stealth Patchright with 14-layer anti-detect
2. **Navigate** — Opens Xiaomi signup page
3. **Fill Form** — Random email (generator.email) + random password
4. **CAPTCHA Handling**:
   - **reCAPTCHA v2** → Automated audio solver (Google STT, ~90% accuracy)
   - **Xiaomi text CAPTCHA** → Manual solve (user types code in browser)
5. **OTP** — Polls generator.email inbox for 6-digit verification code
6. **Identity Verification** — Handles Xiaomi's second OTP (Send → wait → enter code)
7. **Terms Dialog** — Trusted checkbox click + Confirm
8. **Cookie Clear** — Prevents "own invitation code" error from stale sessions
9. **Balance Page** — Navigates to MiMo platform (auto-login via Xiaomi session)
10. **Referral** — Enters referral code via UI input fields
11. **Risk Control** — Detects if account is flagged; stops batch if detected
12. **Balance Verify** — Confirms $2.72 via regex extraction
13. **API Key** — Creates key, captures full 51-char key via network intercept (fallback: clipboard)
14. **Save** — Credentials saved to single batch file in `accounts/`

### Auto-Farm Mode Flow

```
Target: $20.00

Account 1 (MAIN):
  Email: abc@domain.com
  Referral: (none — main account)
  Balance: $0.72
  Referral Code: AU2CHB
  Total: $0.72 / $20.00

[vpn] Ganti IP kamu sekarang (VPN/mobile hotspot).
Tekan ENTER kalau udah ganti IP...
  ✅ IP changed! Current IP: 114.10.41.203

[delay] Waiting 56s before next account...

Account 2 (CHILD, referral: AU2CHB):
  Email: xyz@domain.com
  Balance: $2.72 (+$2.00 to parent)
  Total: $5.44 / $20.00

... (continue until total >= $20)

✅ AUTO-FARM COMPLETE
Target: $20.00
Achieved: $20.48
Accounts saved: 8
```

### Siklus Mode Flow

```
Siklus 1:
  ├─ Main account (no referral) → own_referral = XJ6YSS
  ├─ Child 1 (referral: XJ6YSS) → $2.72 balance
  ├─ Child 2 (referral: XJ6YSS) → $2.72 balance
  ├─ Child 3 (referral: XJ6YSS) → $2.72 balance
  ├─ Child 4 (referral: XJ6YSS) → $2.72 balance
  └─ Child 5 (referral: XJ6YSS) → $2.72 balance

Total: 6 accounts, $14.32 combined balance
```

### Referral Bonus Structure

```
Parent Account:
  - Signup bonus: $0.72
  - Per child referral: +$2.00
  - 5 children total: $0.72 + (5 × $2.00) = $10.72

Child Account:
  - Signup bonus: $0.72
  - Referral bonus: +$2.00
  - Total per child: $2.72

Combined (1 parent + 5 children):
  - Parent: $10.72
  - Children: 5 × $2.72 = $13.60
  - Grand total: $24.32
```

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

# (Optional) Install ADB for Android IP rotation
# Windows:
winget install adb
# macOS:
brew install android-platform-tools
# Linux:
sudo apt install android-tools-adb
```

### Requirements

- Python 3.10+ (3.12 recommended)
- Google Chrome (for CDP mode)
- ffmpeg (system dependency)
- Patchright (auto-installed with pip)
- (Optional) ADB + Android device with USB tethering (for auto IP rotation)

## Usage

### Auto-Farm Mode (Recommended)

Create accounts until target balance reached. Uses CDP mode by default.

```bash
# Step 1: Launch Chrome with remote debugging
"C:\Program Files\Google\Chrome\Application\chrome.exe" ^
  --remote-debugging-port=9222 ^
  --user-data-dir="C:\Users\YOU\chrome-debug-real"

# Step 2: Run auto-farm (in another terminal)
mimo create --target-balance 20 --captcha manual

# With ADB IP rotation (Android USB tethering)
mimo create --target-balance 20 --captcha manual --ip-rotate adb
mimo create --target-balance 20 --captcha manual --ip-rotate data  # faster

# With auto reCAPTCHA audio solver
mimo create --target-balance 20 --captcha auto --ip-rotate adb

# Disable CDP (use Patchright with random fingerprint per account)
mimo create --target-balance 20 --captcha manual --no-cdp
```

### Siklus Mode

```bash
# 1 siklus = 1 main + 5 children = 6 accounts
mimo create --siklus

# Multiple siklus
mimo create --siklus --count 3  # 3 siklus = 18 accounts

# With CDP mode (default)
mimo create --siklus --cdp-url http://localhost:9222
```

### Single / Multiple Accounts

```bash
mimo create --referral ABC123 --count 1
mimo create --referral ABC123 --count 5
```

### Parallel Mode

```bash
mimo create --referral ABC123 --count 10 --parallel 3
```

### Continuous Mode

```bash
# Keep creating until risk control detected (Ctrl+C to stop)
mimo create --referral ABC123 --continuous
```

### All CLI Options

```
mimo create [OPTIONS]

Options:
  --count, -n N          Number of accounts to create
  --referral, -r CODE    Referral code to use
  --captcha MODE         Captcha mode: 'auto' or 'manual' (default: manual)
  --target-balance, -t   Auto-farm until total balance reaches target (e.g., 20)
  --siklus               Siklus mode: 1 main + 5 children per cycle
  --continuous           Keep creating until risk control
  --parallel, -p N       Number of parallel browser instances
  --proxy                Use free proxy rotation
  --ip-rotate METHOD     ADB IP rotation: 'adb' (airplane ~15s) or 'data' (toggle ~8s)
  --cdp-url URL          CDP URL (default: http://localhost:9222)
  --no-cdp               Disable CDP mode, use Patchright instead
  --fast                 Reduced delays for faster creation
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

Single batch file in `accounts/batch_YYYYMMDD_HHMMSS.txt`:

```
[1] — Main
Mail: 4cniy0m9q8@rexornge.net
Link: https://generator.email/4cniy0m9q8@rexornge.net
Pw: MmaTUm11MU!9
Api-Key: sk-s2nnxo2labcdef1234567890abcdefghijklmnopqrstuvwxyz
Balance: $4.72

[2]
Mail: h7vb2k4@rexornge.net
Link: https://generator.email/h7vb2k4@rexornge.net
Pw: MmKp3Xnq7!9
Api-Key: sk-t98abcd1234567890abcdefghijklmnopqrstuvwxyz
Balance: $2.72

[3]
Mail: xyz@domain.com
Link: https://generator.email/xyz@domain.com
Pw: MmAbc123!9
Api-Key: sk-xyz1234567890abcdefghijklmnopqrstuvwxyz
Balance: $2.72
```

> **Note:** API keys are only saved to local files — they are never transmitted anywhere.

## Configuration

### Default Settings

| Setting | Default | Description |
|---------|---------|-------------|
| Referral Code | `M57JCH` | Default referral code |
| Password | `papoi123` | Default password (overridable) |
| CDP URL | `http://localhost:9222` | Chrome DevTools Protocol endpoint |
| Email Domains | 15+ domains | Auto-scraped from generator.email |
| Browser | CDP (Chrome) | Real Chrome via CDP, or Patchright with --no-cdp |
| OTP Timeout | 180s | Max wait for verification email |
| CAPTCHA | Manual (Xiaomi), Auto (reCAPTCHA) | Text CAPTCHA → user solves; reCAPTCHA → audio STT |
| Inter-account Delay | 40-60s | Random delay between accounts (anti-detection) |

### CDP Mode vs Patchright Mode

| Feature | CDP Mode (Default) | Patchright Mode (--no-cdp) |
|---------|-------------------|---------------------------|
| **Browser** | Real Chrome (via remote debugging) | Patchright Chromium (anti-detect fork) |
| **navigator.webdriver** | `false` (naturally) | `false` (JS patch) |
| **Fingerprint** | Fixed (your Chrome's real fingerprint) | Random per account (14 layers) |
| **reCAPTCHA trust** | Higher (real Chrome) | Medium (stealth patches) |
| **Setup required** | Launch Chrome with --remote-debugging-port | None (auto-launch) |
| **Best for** | Manual captcha mode | Auto captcha mode |

### Working Email Domains

The tool auto-scrapes available domains from generator.email. If a domain gets "not safe" error from Xiaomi, it automatically retries with a new domain/email. This loop continues until a working domain is found.

## Architecture

```
mimo-farmer/
├── mimo_farmer/
│   ├── __init__.py       # Package version
│   ├── __main__.py       # Entry point (python -m mimo_farmer)
│   ├── cli.py            # Argparse CLI — auto-farm, siklus, continuous, parallel
│   ├── creator.py        # Core pipeline: signup, CAPTCHA, OTP, referral, API key
│   ├── captcha.py        # reCAPTCHA v2 audio solver + Xiaomi text CAPTCHA detection
│   ├── email_handler.py  # generator.email OTP polling
│   ├── config.py         # Default settings + constants
│   ├── anti_detect.py    # 14-layer stealth browser config (UA, WebGL, WebRTC, etc.)
│   ├── adb_ip_rotate.py  # ADB IP rotation via Android USB tethering
│   ├── proxy_manager.py  # Free proxy rotation from 7 sources (~7,700 proxies)
│   └── web/              # Web UI (FastAPI + WebSocket)
├── accounts/             # Batch output files (gitignored)
├── docs/
│   ├── DOCUMENTATION.md  # Full technical documentation
│   ├── banner_chatgpt.png
│   ├── demo.png
│   └── pipeline.png
├── CHANGELOG.md
├── README.md
├── LICENSE               # MIT License
├── requirements.txt
├── setup.py
└── run.bat               # Windows quick-run script
```

### Key Technical Decisions

| Decision | Why |
|----------|-----|
| **Patchright** over Playwright | Anti-detect fingerprint avoids bot detection |
| **Manual Xiaomi CAPTCHA** | ddddocr accuracy ~50%, manual is faster than wasted retries |
| **reCAPTCHA audio** over image | Free Google STT > paid captcha services |
| **Network intercept** for API keys | `input[disabled].value` returns masked key |
| **`input[type="checkbox"]`** click | Trusted event that React recognizes (label click doesn't work) |
| **Cookie clearing** between phases | Prevents "own invitation code" from stale sessions |
| **Unlimited email retry** | Some domains get "not safe", keep retrying until accepted |
| **Batch-only output** | Single file per run, no per-account file clutter |

## Troubleshooting

### Xiaomi text CAPTCHA appears

This is normal. The tool will pause and wait for you to manually type the verification code in the browser window. After solving, the tool automatically continues.

### reCAPTCHA not loading

1. **Password too long** — Xiaomi max 16 chars. Keep password ≤16.
2. **IP flagged** — Wait 30-60 minutes or switch IP (VPN/mobile hotspot).
3. **Patchright detected** — Rare. Try again later.

### "Risk control restrictions" error

Xiaomi flags accounts after multiple signups from same IP.

1. **Create new referral code** — Old codes get flagged
2. **Switch IP** — Mobile hotspot or residential VPN
3. **Wait** — IP cooldown takes 1-2 hours
4. **Use `--siklus`** — Built-in cooldown between cycles

### Email "not safe" error

Xiaomi rejects certain temp email domains. The tool automatically retries with a new email/domain. If it keeps failing:
1. generator.email may be rate-limited — wait 10-15 minutes
2. Switch IP
3. Check if generator.email is accessible

### API key shows masked (asterisks)

The tool automatically falls back to clipboard copy button. If both fail, re-run to get a fresh key.

### Identity verification timeout

Xiaomi requires a second OTP. The tool waits up to 180 seconds. If timeout:
1. Check if generator.email is accessible
2. Email domain may be rate-limited — wait 10-15 minutes
3. Switch IP

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for full version history.

## Legal Disclaimer

This tool is for **educational and research purposes only**. Users are responsible for compliance with Xiaomi's Terms of Service and applicable laws. The authors are not responsible for any misuse.

## License

[MIT](LICENSE)

---

<p align="center">
  <sub>Built with ❤️ and Python</sub>
</p>
