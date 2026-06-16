"""Default configuration for MiMo CLI."""

import os

# Referral
DEFAULT_REFERRAL_CODE = "FHAZMU"
DEFAULT_PASSWORD = "papoi123"

# URLs
SIGNUP_URL = "https://global.account.xiaomi.com/fe/service/register?_locale=en&source=&region=ID&sid=api-platform"
BALANCE_URL = "https://platform.xiaomimimo.com/console/balance"
API_KEYS_URL = "https://platform.xiaomimimo.com/console/api-keys"
LOGOUT_URL = "https://account.xiaomi.com/pass/logout"

# Paths
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ACCOUNTS_DIR = os.path.join(PROJECT_ROOT, "accounts")
AUDIO_DIR = os.path.join(PROJECT_ROOT, ".audio_cache")

# Timing
FAST_MODE_MULTIPLIER = 0.4
HUMAN_DELAY_MIN_MS = 150
HUMAN_DELAY_MAX_MS = 600
FAST_DELAY_MIN_MS = 50
FAST_DELAY_MAX_MS = 200

# OTP
OTP_TIMEOUT_SECONDS = 180
OTP_POLL_INTERVAL_SECONDS = 1.5

# reCAPTCHA
CAPTCHA_MAX_RETRIES = 5

# Email domains for generator.email
# Fallback if dynamic scraping fails
EMAIL_DOMAINS = ["banri.xyz"]
