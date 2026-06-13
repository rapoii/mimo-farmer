# mimo-farmer

[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-1.0.0-orange.svg)]()

Automated Xiaomi MiMo account creation CLI tool with referral bonuses.

> **Proven working (2026-06-13)** — full pipeline: signup form, reCAPTCHA v2 audio bypass, OTP via temp email, terms dialog, referral code, balance verification, API key creation.

## Features

- **reCAPTCHA v2 audio solver** — free Google SpeechRecognition, no API key needed
- **Temp email OTP** — generator.email integration with auto-polling
- **Referral codes** — automatic 6-char code entry via OTP input fields
- **API key creation** — auto-extracts from disabled input fields
- **Balance verification** — confirms $2.72 referral bonus
- **Fast mode** — reduced delays for quicker account creation
- **Parallel mode** — multiple browser instances simultaneously
- **Account management** — list, export credentials

## Requirements

- Python 3.10+
- [ffmpeg](https://ffmpeg.org/) (system dependency for audio conversion)
- [Patchright](https://github.com/Kaliiiiiiiiii-Vinyzu/patchright) (anti-detect Playwright)

## Installation

```bash
# Clone the repo
git clone https://github.com/rapoii/mimo-farmer.git
cd mimo-farmer

# Install
pip install -e .

# Or install dependencies directly
pip install -r requirements.txt

# Install ffmpeg (if not installed)
# Windows: choco install ffmpeg  OR  scoop install ffmpeg
# macOS:   brew install ffmpeg
# Linux:   sudo apt install ffmpeg
```

## Usage

### Create single account

```bash
mimo-farmer create
```

### Create multiple accounts

```bash
mimo-farmer create --count 5
```

### Custom referral code

```bash
mimo-farmer create --referral ABC123
```

### Fast mode (reduced delays)

```bash
mimo-farmer create --fast
```

### Parallel browser instances

```bash
mimo-farmer create --parallel 2
```

### Combine options

```bash
mimo-farmer create --count 10 --parallel 3 --fast --referral MYCODE
```

### List created accounts

```bash
mimo accounts
```

Output:
```
Email                               Balance      Referral   API Key  Created
------------------------------------------------------------------------------------------
abc123@snpmail.fun                  $2.72        6KAARG     OK       2026-06-13 12:00:00
```

### Export credentials

```bash
mimo export                           # JSON format (default)
mimo export --format text             # Text format
mimo export --output my_accounts.json # Custom output path
```

## How It Works

1. **Browser launch** — Patchright (anti-detect Playwright) opens Chromium
2. **Signup form** — fills email, password, agreement checkbox
3. **reCAPTCHA v2** — audio challenge → download audio from bframe context → ffmpeg → Google free STT
4. **OTP** — polls generator.email for 6-digit code
5. **Terms dialog** — handles ant-modal checkbox + Confirm button
6. **Referral** — enters 6-char code via individual OTP input fields
7. **Balance** — verifies $2.72 referral bonus via regex
8. **API key** — creates and extracts from disabled input field
9. **Save** — credentials saved as .txt and .json in `accounts/`

## Project Structure

```
mimo-farmer/
├── README.md              # This file
├── LICENSE                # MIT License
├── .gitignore
├── requirements.txt       # Python dependencies
├── setup.py              # Package setup
├── mimo_cli/
│   ├── __init__.py       # Package init + version
│   ├── __main__.py       # Entry point (python -m mimo_cli)
│   ├── cli.py            # Argparse CLI (create, accounts, export)
│   ├── creator.py        # Core account creation pipeline
│   ├── captcha.py        # reCAPTCHA v2 audio solver
│   ├── email_handler.py  # generator.email OTP polling
│   └── config.py         # Default settings
└── accounts/             # Generated credentials (gitignored)
```

## License

[MIT](LICENSE)
