"""CLI interface for MiMo account creation.

Commands:
  mimo create              Create single account
  mimo create --count 5    Create 5 accounts sequentially
  mimo create --referral CODE  Custom referral code
  mimo create --captcha auto|manual  Set captcha mode
  mimo create --parallel 2 Parallel browser instances
  mimo create --continuous Keep creating until risk control
  mimo accounts            List created accounts
  mimo export              Export all credentials to single file
  mimo web                 Start localhost Web UI
"""

import argparse
import asyncio
import json
import os
import random
import sys
import time

from mimo_farmer.config import DEFAULT_REFERRAL_CODE, ACCOUNTS_DIR, CAPTCHA_MODE_DEFAULT, TARGET_BALANCE_DEFAULT
from mimo_farmer import __version__


def build_parser() -> argparse.ArgumentParser:
    """Build argument parser with subcommands."""
    parser = argparse.ArgumentParser(
        prog="mimo",
        description="MiMo CLI — Automated Xiaomi MiMo account creation with referral bonuses",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
examples:
  mimo create                   Create single account
  mimo create --count 5         Create 5 accounts sequentially
  mimo create --referral ABC123 Custom referral code
  mimo create --captcha auto     Auto captcha solving (default)
  mimo create --captcha manual   Manual captcha solving
  mimo create --parallel 2      2 parallel browser instances
  mimo create --continuous      Keep creating until risk control
  mimo create --siklus          Hub mode (1 parent + 5 children = 6 per cycle)
  mimo create --count 10 --parallel 3 --captcha manual
  mimo accounts                 List all created accounts
  mimo export                   Export all credentials to file
  mimo export --output creds.json
  mimo web                      Start Web UI on 127.0.0.1:8080
  mimo web --port 9090          Start Web UI on custom port
""",
    )
    parser.add_argument(
        "-V", "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    sub = parser.add_subparsers(dest="command", help="command to run")

    # create
    p_create = sub.add_parser(
        "create",
        help="Create MiMo accounts",
        description="Create one or more MiMo accounts with automated browser pipeline",
    )
    p_create.add_argument(
        "--count", "-n",
        type=int,
        default=None,
        metavar="N",
        help="Number of accounts to create (prompted if not provided)",
    )
    p_create.add_argument(
        "--referral", "-r",
        type=str,
        default=None,
        metavar="CODE",
        help="Referral code to use (prompted if not provided)",
    )
    p_create.add_argument(
        "--captcha",
        choices=["auto", "manual"],
        default=CAPTCHA_MODE_DEFAULT,
        metavar="MODE",
        help="Captcha mode: 'auto' = reCAPTCHA audio STT, 'manual' = all manual (default: from config)",
    )
    p_create.add_argument(
        "--proxy",
        action="store_true",
        help="Use free proxy rotation (multiple sources) instead of manual VPN",
    )
    p_create.add_argument(
        "--ip-rotate",
        choices=["adb", "data"],
        default=None,
        metavar="METHOD",
        help="Auto IP rotation via Android USB tethering: 'adb' = airplane mode (~15s), 'data' = mobile data toggle (~8s)",
    )
    p_create.add_argument(
        "--cdp-url",
        default="http://localhost:9222",
        metavar="URL",
        help="Connect to existing Chrome via CDP (e.g. http://localhost:9222). Real Chrome = no automation detect. (default: http://localhost:9222)",
    )
    p_create.add_argument(
        "--no-cdp",
        action="store_true",
        help="Disable CDP mode — use Patchright browser instead (random fingerprint per account)",
    )
    p_create.add_argument(
        "--parallel", "-p",
        type=int,
        default=1,
        metavar="N",
        help="Number of parallel browser instances (default: 1)",
    )
    p_create.add_argument(
        "--continuous", "--auto", "-c",
        action="store_true",
        help="Keep creating accounts until risk control is detected (no --count needed)",
    )
    p_create.add_argument(
        "--siklus", "-s",
        action="store_true",
        help="Hub mode: 1 parent + 5 children per siklus = 6 accounts",
    )
    p_create.add_argument(
        "--target-balance", "-t",
        type=float,
        default=None,
        metavar="USD",
        help="Auto-farm mode: create main+children until total bonus balance reaches target (e.g. --target-balance 50)",
    )

    # accounts
    sub.add_parser(
        "accounts",
        help="List created accounts",
        description="Show all previously created accounts from the accounts/ directory",
    )

    # export
    p_export = sub.add_parser(
        "export",
        help="Export credentials to file",
        description="Export all account credentials into a single JSON or text file",
    )
    p_export.add_argument(
        "--output", "-o",
        type=str,
        default=None,
        metavar="PATH",
        help="Output file path (default: accounts/export_<timestamp>.json)",
    )
    p_export.add_argument(
        "--format",
        choices=["json", "text"],
        default="json",
        help="Output format (default: json)",
    )

    p_web = sub.add_parser(
        "web",
        help="Start Web UI",
        description="Start the localhost FastAPI Web UI",
    )
    p_web.add_argument(
        "--host",
        default="127.0.0.1",
        help="Bind host (default: 127.0.0.1)",
    )
    p_web.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Bind port (default: 8080)",
    )
    p_web.add_argument(
        "--reload",
        action="store_true",
        help="Enable uvicorn reload mode",
    )

    return parser


def cmd_create(args) -> int:
    """Handle `mimo create` command."""
    from mimo_farmer.creator import create_account, create_account_with_retry

    referral = args.referral
    count = args.count
    captcha_mode = args.captcha
    parallel = args.parallel
    continuous = args.continuous
    siklus = args.siklus
    target_balance = getattr(args, 'target_balance', None)

    # --target-balance conflicts with other modes
    if target_balance is not None:
        if siklus:
            print("  [!] --target-balance and --siklus cannot be used together.")
            return 1
        if continuous:
            print("  [!] --target-balance and --continuous cannot be used together.")
            return 1
        if count is not None:
            print("  [!] --target-balance and --count cannot be used together.")
            return 1
        if referral:
            print("  [!] --target-balance and --referral cannot be used together.")
            return 1
        ip_rotate = getattr(args, 'ip_rotate', None)
        cdp_url = getattr(args, 'cdp_url', None)
        no_cdp = getattr(args, 'no_cdp', False)
        if no_cdp:
            cdp_url = None  # Use Patchright instead
        print(f"\nMiMo CLI v{__version__}")
        return _run_target_balance(target_balance, captcha_mode, ip_rotate, cdp_url=cdp_url)

    # --siklus and --continuous don't mix
    if siklus and continuous:
        print("  [!] --siklus and --continuous cannot be used together.")
        return 1

    # --siklus with --count: use count as siklus count (no interactive prompt)
    # --siklus and --parallel don't mix
    if siklus and parallel > 1:
        print("  [!] --siklus and --parallel cannot be used together.")
        return 1

    # --siklus with --referral is meaningless (referral auto-generated from main)
    if siklus and referral:
        print("  [!] --referral diabaikan di siklus mode (referral diambil dari akun utama)")
        referral = None

    # Siklus mode: no referral needed (auto-generated from main account)
    if siklus:
        if count is not None:
            siklus_count = count
        else:
            siklus_count = 1
            while True:
                user_input = input("Mau berapa siklus? (1 siklus = 1 akun utama + 5 anak): ").strip()
                try:
                    siklus_count = int(user_input)
                    if siklus_count > 0:
                        break
                    print("  [!] Minimal 1 siklus!")
                except ValueError:
                    print("  [!] Masukkan angka yang valid!")

        print(f"\nMiMo CLI v{__version__}")
        print(f"SIKLUS MODE | {siklus_count} siklus | Captcha: {captcha_mode}")
        print(f"Tiap siklus: 5 pasang (main + child) = 10 akun")
        print(f"Total akun: {siklus_count * 10}")
        
        cdp_url = getattr(args, 'cdp_url', 'http://localhost:9222')
        no_cdp = getattr(args, 'no_cdp', False)
        if no_cdp:
            cdp_url = None
        print(f"CDP Mode: {'Enabled' if cdp_url else 'Disabled (Patchright)'}")
        print()
        return _run_siklus(siklus_count, captcha_mode, use_proxy=getattr(args, 'proxy', False), ip_rotate=getattr(args, 'ip_rotate', None), cdp_url=cdp_url)

    # --continuous and --parallel don't mix
    if continuous and parallel > 1:
        print("  [!] --continuous and --parallel cannot be used together.")
        print("  [!] Continuous mode runs sequentially until risk control.")
        return 1

    # --continuous and --count don't mix
    if continuous and count is not None:
        print("  [!] --continuous ignores --count. Remove --count or pick one.")
        return 1

    # Interactive prompts — only if args not provided via CLI
    if not referral:
        while True:
            referral = input("Kode referral: ").strip().upper()
            if referral:
                break
            print("  [!] Kode referral wajib diisi!")

    # Continuous mode: no count needed
    if continuous:
        print(f"\nMiMo CLI v{__version__}")
        print(f"CONTINUOUS MODE | Referral: {referral} | Captcha: {captcha_mode}")
        print("Creating accounts until risk control detected (Ctrl+C to stop)\n")
        return _run_continuous(referral, captcha_mode)

    if not count or count < 1:
        while True:
            user_input = input("Mau bikin berapa akun? ").strip()
            try:
                count = int(user_input)
                if count > 0:
                    break
                print("  [!] Minimal 1 akun!")
            except ValueError:
                print("  [!] Masukkan angka yang valid!")

    print(f"\nMiMo CLI v{__version__}")
    print(f"Creating {count} account(s) | Referral: {referral} | Captcha: {captcha_mode} | Parallel: {parallel}")
    print()

    if parallel > 1:
        return _run_parallel(count, referral, captcha_mode, parallel)
    else:
        return _run_sequential(count, referral, captcha_mode)


def _run_sequential(count: int, referral: str, captcha_mode: str) -> int:
    """Create accounts one at a time."""
    import time as _time
    from mimo_farmer.creator import create_account, create_account_with_retry

    results = []
    for i in range(count):
        # Random cooldown between accounts (anti-detection)
        if i > 0:
            cooldown = random.randint(1, 10)
            print(f"\n  ⏳ Cooldown {cooldown}s between accounts (anti-detection)...")
            _time.sleep(cooldown)

        if count > 1:
            print(f"\n{'#' * 60}")
            print(f"  Account {i + 1}/{count}")
            print(f"{'#' * 60}\n")

        try:
            result = asyncio.run(create_account_with_retry(
                referral_code=referral,
                captcha_mode=captcha_mode,
                account_num=i + 1,
            ))
            results.append(result)

            # Risk control detected → stop batch, suggest new referral code
            if result and (result.get('risk_control') or result.get('ip_blocked')):
                reason = "risk control" if result.get('risk_control') else "IP blocked (automated queries)"
                print(f"\n  [!] {reason.upper()} detected on account {i + 1}!")
                if result.get('ip_blocked'):
                    print(f"  [!] Ganti IP (VPN/residential proxy) dulu.")
                else:
                    print(f"  [!] Referral code '{referral}' is blocked or IP is flagged.")
                    print(f"  [!] Create a NEW referral code and try again.")
                break

            if result is None:
                print(f"\n  [!] Account {i + 1} failed — stopping batch.")
                break
        except Exception as e:
            print(f"  [!] Error: {e}")
            results.append(None)
            break

        # IP cooldown alert — every 4 successful accounts
        success_count = sum(1 for r in results if r is not None)
        if success_count > 0 and success_count % 4 == 0 and i + 1 < count:
            print(f"\n{'!' * 60}")
            print(f"  ⚠️  IP COOLDOWN ALERT")
            print(f"  Kamu udah bikin {success_count} akun berturut-turut.")
            print(f"  Risk control makin tinggi tiap 5 akun.")
            print(f"{'!' * 60}")
            try:
                choice = input("\n  Ganti IP dulu? [y/N]: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                choice = 'n'

            if choice == 'y':
                print("\n  ⏳ Ganti IP kamu sekarang (VPN/mobile hotspot).")
                try:
                    input("  Tekan ENTER kalau udah ganti IP...")
                except (EOFError, KeyboardInterrupt):
                    pass
                print("  ✅ IP changed! Lanjut nuyul...\n")
            else:
                print("  ⏭️  Lanjut tanpa ganti IP (risk control makin tinggi)\n")

    success = sum(1 for r in results if r is not None)
    _save_combined(results, referral)
    print(f"\n{'=' * 60}")
    print(f"  Summary: {success}/{count} accounts created")
    print(f"{'=' * 60}")
    return 0 if success > 0 else 1


def _run_continuous(referral: str, captcha_mode: str) -> int:
    """Create accounts one by one until risk control is detected."""
    from mimo_farmer.creator import create_account, create_account_with_retry

    results = []
    failures = 0
    account_num = 0
    last_success = None

    try:
        while True:
            # Random cooldown between accounts (anti-detection)
            if account_num > 0:
                cooldown = random.randint(1, 10)
                print(f"\n  ⏳ Cooldown {cooldown}s between accounts (anti-detection)...")
                time.sleep(cooldown)

            account_num += 1
            print(f"\n{'#' * 60}")
            print(f"  Account #{account_num}")
            print(f"{'#' * 60}\n")

            try:
                result = asyncio.run(create_account_with_retry(
                    referral_code=referral,
                    captcha_mode=captcha_mode,
                    account_num=account_num,
                ))
            except Exception as e:
                print(f"  [!] Error on account {account_num}: {e}")
                failures += 1
                continue

            # Risk control or IP block → STOP
            if result and (result.get('risk_control') or result.get('ip_blocked')):
                reason = "risk control" if result.get('risk_control') else "IP blocked (automated queries)"
                print(f"\n  [!] {reason.upper()} detected on account #{account_num}!")
                if result.get('ip_blocked'):
                    print(f"  [!] Ganti IP (VPN/residential proxy) dulu.")
                else:
                    print(f"  [!] Referral code '{referral}' is blocked or IP is flagged.")
                    print(f"  [!] Stopping continuous mode.")
                failures += 1
                break

            # Account creation failed (not risk control)
            if result is None:
                failures += 1
                print(f"\n  [!] Account #{account_num} failed — skipping.")
                continue

            # Success
            results.append(result)
            last_success = result
            balance = result.get('balance', 'N/A')
            email = result.get('email', 'N/A')
            success_count = len(results)
            print(f"\n  ✓ Account #{account_num} created (balance: {balance})")
            print(f"    Email: {email}")
            print(f"    Running tally: {success_count} accounts created, {failures} failed")

            # IP cooldown alert — every 4 successful accounts
            if success_count > 0 and success_count % 4 == 0:
                print(f"\n{'!' * 60}")
                print(f"  ⚠️  IP COOLDOWN ALERT")
                print(f"  Kamu udah bikin {success_count} akun berturut-turut.")
                print(f"  Risk control makin tinggi tiap 5 akun.")
                print(f"{'!' * 60}")
                try:
                    choice = input("\n  Ganti IP dulu? [y/N]: ").strip().lower()
                except (EOFError, KeyboardInterrupt):
                    choice = 'n'

                if choice == 'y':
                    print("\n  ⏳ Ganti IP kamu sekarang (VPN/mobile hotspot).")
                    try:
                        input("  Tekan ENTER kalau udah ganti IP...")
                    except (EOFError, KeyboardInterrupt):
                        pass
                    print("  ✅ IP changed! Lanjut nuyul...\n")
                else:
                    print("  ⏭️  Lanjut tanpa ganti IP (risk control makin tinggi)\n")

    except KeyboardInterrupt:
        print(f"\n\n  [!] Interrupted by user (Ctrl+C)")

    # Final summary
    success_count = len(results)
    print(f"\n{'=' * 60}")
    print(f"  CONTINUOUS MODE — FINAL SUMMARY")
    print(f"{'=' * 60}")
    print(f"  Total created:    {success_count}")
    print(f"  Total failed:     {failures}")
    print(f"  Total attempts:   {account_num}")
    if last_success:
        print(f"  Last success:     {last_success.get('email', 'N/A')} (balance: {last_success.get('balance', 'N/A')})")
    print(f"{'=' * 60}")

    if success_count > 0:
        _save_combined(results, referral)
        return 0
    return 1


def _run_siklus(siklus_count: int, captcha_mode: str, use_proxy: bool = False, ip_rotate: str = None, cdp_url: str = "http://localhost:9222") -> int:
    """Hub mode: 1 parent + 5 children per siklus.

    Flow per siklus (6 accounts):
      Parent (no ref) → ganti IP
      Child 1 (ref: Parent) → ganti IP
      Child 2 (ref: Parent) → ganti IP
      Child 3 (ref: Parent) → ganti IP
      Child 4 (ref: Parent) → ganti IP
      Child 5 (ref: Parent)

    IP rotation: EVERY account (parent → child also).
    Domain: random per account (no reuse).
    """
    import time as _time
    from mimo_farmer.creator import create_account_with_retry

    all_results = []
    total_success = 0
    total_fail = 0
    CHILDREN_PER_SIKLUS = 5
    ACCOUNTS_PER_SIKLUS = 1 + CHILDREN_PER_SIKLUS  # 6
    last_siklus = 0

    # Proxy setup
    proxy_pool = []
    proxy_index = 0
    if use_proxy:
        from mimo_farmer.proxy_manager import fetch_all_proxies, check_proxy
        print("  [proxy] Fetching proxies from 7 sources...")
        proxy_pool = fetch_all_proxies()
        print(f"  [proxy] Found {len(proxy_pool)} proxies")
        if not proxy_pool:
            print("  [proxy] No proxies found — falling back to manual VPN")
            use_proxy = False

    def get_next_proxy() -> dict | None:
        nonlocal proxy_index
        if not use_proxy or not proxy_pool:
            return None
        # Try up to 20 proxies (HTTP check to Xiaomi takes ~8s each)
        for i in range(min(20, len(proxy_pool))):
            if proxy_index >= len(proxy_pool):
                proxy_index = 0
                random.shuffle(proxy_pool)
            proxy = proxy_pool[proxy_index]
            proxy_index += 1
            if check_proxy(proxy):
                print(f"  [proxy] Using: {proxy}")
                return {"server": f"http://{proxy}"}
        print("  [proxy] All proxies failed — falling back to manual VPN")
        return None

    # ADB IP rotation setup
    adb_rotator = None
    if ip_rotate:
        from mimo_farmer.adb_ip_rotate import _find_adb, check_device, rotate_ip as adb_rotate
        adb_path = _find_adb()
        if not adb_path:
            print("  [adb] ADB not found — falling back to manual VPN")
            ip_rotate = None
        elif not check_device(adb_path):
            print("  [adb] No device connected — falling back to manual VPN")
            ip_rotate = None
        else:
            from mimo_farmer.adb_ip_rotate import get_device_info, get_current_ip
            info = get_device_info(adb_path)
            ip = get_current_ip()
            print(f"  [adb] Device: {info.get('model', '?')} (Android {info.get('android', '?')})")
            print(f"  [adb] Current IP: {ip}")
            print(f"  [adb] Method: {'airplane mode (~15s)' if ip_rotate == 'adb' else 'data toggle (~8s)'}")
            adb_rotator = adb_path

    def rotate_ip():
        """Rotate IP: ADB (auto), proxy (auto), or manual VPN."""
        if adb_rotator:
            method = "airplane" if ip_rotate == "adb" else "data"
            print(f"  [adb] Rotating IP via {'airplane mode' if method == 'airplane' else 'data toggle'}...")
            result = adb_rotate(method=method, adb=adb_rotator)
            if result.get("success"):
                changed = "✓ CHANGED" if result.get("changed") else "✗ same"
                print(f"  [adb] {result.get('ip_before', '?')} → {result.get('ip_after', '?')} ({changed})")
            else:
                print(f"  [adb] Rotation failed: {result.get('error')}")
        elif use_proxy and proxy_pool:
            print("  [proxy] Rotating to next proxy...")
            # Next account will get new proxy via get_next_proxy()
        else:
            _prompt_ip_rotation(total_success)

    try:
        for s in range(1, siklus_count + 1):
            if s > 1:
                cooldown = random.randint(1, 10)
                print(f"\n  ⏳ Cooldown {cooldown}s between siklus cycles...")
                _time.sleep(cooldown)

            print(f"\n{'=' * 60}")
            print(f"  🔄 SIKLUS {s}/{siklus_count} (1 parent + {CHILDREN_PER_SIKLUS} children = {ACCOUNTS_PER_SIKLUS} accounts)")
            print(f"{'=' * 60}\n")

            account_counter = (s - 1) * ACCOUNTS_PER_SIKLUS + 1

            # ── Step 1: Create parent (no referral) ──
            parent_num = account_counter
            account_counter += 1
            print(f"  [Parent #{parent_num}] Creating (no referral)...")

            parent_result = None
            PARENT_MAX_RETRIES = 3
            for attempt in range(PARENT_MAX_RETRIES):
                if attempt > 0:
                    print(f"  [!] Retrying parent #{parent_num} (attempt {attempt + 1}/{PARENT_MAX_RETRIES})...")
                    _time.sleep(random.randint(2, 5))

                try:
                    parent_result = asyncio.run(create_account_with_retry(
                        referral_code="",
                        captcha_mode=captcha_mode,
                        account_num=parent_num,
                        skip_referral=True,
                        proxy_config=get_next_proxy(),
                    ))
                except Exception as e:
                    print(f"  [!] Parent #{parent_num} error: {e}")
                    parent_result = None

                if parent_result is not None:
                    break
                print(f"  [!] Parent #{parent_num} — OTP not received, retrying...")

            if parent_result is None:
                print(f"  [!] Parent #{parent_num} failed after {PARENT_MAX_RETRIES} attempts — skipping siklus.")
                total_fail += 1
                continue

            # Check failures
            if parent_result.get('ip_blocked'):
                print(f"  [!] Parent #{parent_num}: IP blocked — ganti IP dulu.")
                rotate_ip()
                continue  # Retry siklus with new IP

            if (parent_result.get('risk_control')
                    or parent_result.get('unsafe_email') or parent_result.get('domain_flagged')
                    or not parent_result.get('api_key')):
                reason = "risk control" if parent_result.get('risk_control') else \
                         "unsafe email" if parent_result.get('unsafe_email') else \
                         "domain flagged" if parent_result.get('domain_flagged') else "API key missing"
                print(f"  [!] Parent #{parent_num} failed: {reason} — skipping siklus.")
                total_fail += 1
                continue

            # Parent success
            total_success += 1
            parent_result['_is_main'] = True
            all_results.append(parent_result)

            parent_referral = parent_result.get('own_referral')
            parent_email = parent_result.get('email', 'N/A')
            parent_balance = parent_result.get('balance', 'N/A')
            print(f"  ✅ Parent #{parent_num}: {parent_email} | Balance: {parent_balance} | Ref: {parent_referral or 'FAILED'}")

            if not parent_referral:
                print(f"  [!] No referral extracted — skipping children for siklus {s}.")
                total_fail += CHILDREN_PER_SIKLUS
                continue

            # Jeda sebelum ganti IP + child pertama
            jeda = random.randint(40, 60)
            print(f"  ⏳ Jeda {jeda}s sebelum ganti IP...")
            _time.sleep(jeda)

            # ── Step 2: IP rotation before first child ──
            rotate_ip()

            # ── Step 3: Create 5 children ──
            for child_i in range(1, CHILDREN_PER_SIKLUS + 1):
                child_num = account_counter
                account_counter += 1
                print(f"\n  [Child {child_i}/{CHILDREN_PER_SIKLUS} #{child_num}] Creating (ref: {parent_referral})...")

                child_result = None
                CHILD_MAX_RETRIES = 3
                for attempt in range(CHILD_MAX_RETRIES):
                    if attempt > 0:
                        print(f"  [!] Retrying child #{child_num} (attempt {attempt + 1}/{CHILD_MAX_RETRIES})...")
                        _time.sleep(random.randint(2, 5))

                    try:
                        child_result = asyncio.run(create_account_with_retry(
                            referral_code=parent_referral,
                            captcha_mode=captcha_mode,
                            account_num=child_num,
                            proxy_config=get_next_proxy(),
                        ))
                    except Exception as e:
                        print(f"  [!] Child #{child_num} error: {e}")
                        child_result = None

                    if child_result is not None:
                        break
                    print(f"  [!] Child #{child_num} — OTP not received, retrying...")

                if child_result is None:
                    print(f"  [!] Child #{child_num} failed after {CHILD_MAX_RETRIES} attempts.")
                    total_fail += 1
                    # Still rotate IP before next child
                    if child_i < CHILDREN_PER_SIKLUS:
                        rotate_ip()
                    continue

                # IP blocked → prompt IP change → retry same child
                if child_result.get('ip_blocked'):
                    print(f"  [!] Child #{child_num}: IP blocked — ganti IP, retry.")
                    rotate_ip()
                    account_counter -= 1  # Reuse same account number
                    # Retry this child once with new IP
                    try:
                        child_result = asyncio.run(create_account_with_retry(
                            referral_code=parent_referral,
                            captcha_mode=captcha_mode,
                            account_num=child_num,
                            proxy_config=get_next_proxy(),
                        ))
                    except Exception:
                        child_result = None

                    if child_result is None or not child_result.get('api_key'):
                        print(f"  [!] Child #{child_num} still failed after IP change — skip.")
                        total_fail += 1
                        if child_i < CHILDREN_PER_SIKLUS:
                            rotate_ip()
                        continue

                # Referral not found → skip child
                if child_result.get('referral_failed'):
                    print(f"  [!] Child #{child_num}: referral not found — skip.")
                    total_fail += 1
                    if child_i < CHILDREN_PER_SIKLUS:
                        rotate_ip()
                    continue

                # Risk control → stop siklus
                if child_result.get('risk_control'):
                    print(f"  [!] RISK CONTROL on child #{child_num} — stopping siklus.")
                    total_fail += 1
                    break

                # Other failures
                if (child_result.get('unsafe_email') or child_result.get('domain_flagged')
                        or not child_result.get('api_key')):
                    reason = "unsafe email" if child_result.get('unsafe_email') else \
                             "domain flagged" if child_result.get('domain_flagged') else "API key missing"
                    print(f"  [!] Child #{child_num} failed: {reason}.")
                    total_fail += 1
                    if child_i < CHILDREN_PER_SIKLUS:
                        rotate_ip()
                    continue

                # Success!
                total_success += 1
                all_results.append(child_result)
                child_email = child_result.get('email', 'N/A')
                child_balance = child_result.get('balance', 'N/A')
                print(f"  ✅ Child #{child_num}: {child_email} | Balance: {child_balance}")

                # IP rotation after each child (except last)
                if child_i < CHILDREN_PER_SIKLUS:
                    jeda = random.randint(40, 60)
                    print(f"  ⏳ Jeda {jeda}s sebelum ganti IP...")
                    _time.sleep(jeda)
                    rotate_ip()

            last_siklus = s
            parent_count = sum(1 for r in all_results if r and r.get('_is_main'))
            child_count = sum(1 for r in all_results if r and not r.get('_is_main'))
            print(f"\n  Siklus {s} done: {parent_count} parent + {child_count} children ({total_success} total)")

    except KeyboardInterrupt:
        print(f"\n\n  [!] Interrupted by user (Ctrl+C)")
        print(f"  [!] Saving partial results...")

    # Summary
    actual_main = sum(1 for r in all_results if r and r.get('_is_main'))
    actual_children = sum(1 for r in all_results if r and not r.get('_is_main'))
    child_bonus = actual_children * 2

    print(f"\n{'=' * 60}")
    print(f"  🔄 SIKLUS MODE — FINAL SUMMARY")
    print(f"{'=' * 60}")
    print(f"  Siklus completed: {last_siklus}/{siklus_count}")
    print(f"  Total success:    {total_success}")
    print(f"  Total failed:     {total_fail}")
    print(f"  Parent accounts:  {actual_main}")
    print(f"  Child accounts:   {actual_children}")
    print(f"  Referral bonus:   ${child_bonus:.2f} (${2:.2f} × {actual_children} children)")
    print(f"{'=' * 60}")

    # Save combined
    _save_combined(all_results, "siklus")
    return 0 if total_success > 0 else 1


def _run_target_balance(target: float, captcha_mode: str, ip_rotate: str, cdp_url: str = None) -> int:
    """Auto-farm: main + children until total bonus >= target.

    Flow:
    1. Create main account → check bonus → extract referral
    2. Create children with main's referral
    3. If child risk_control → new main
    4. If child not_found → retry child
    5. If child bonus $0 → blacklist domain, retry
    6. IP rotate between every account
    7. Stop when total_bonus >= target
    """
    from mimo_farmer.creator import create_account_with_retry
    from mimo_farmer.config import DOMAINS_BLOCKLIST

    total_bonus = 0.0
    saved_accounts = []
    current_main_referral = None
    current_main_email = None
    consecutive_not_found = 0
    max_not_found = 3  # After 3 not_found, create new main
    account_num = 0

    # ADB IP rotation setup (mirrors _run_siklus pattern)
    adb_rotator = None
    if ip_rotate:
        from mimo_farmer.adb_ip_rotate import _find_adb, check_device, rotate_ip as adb_rotate
        adb_path = _find_adb()
        if not adb_path:
            print("  [adb] ADB not found — falling back to manual VPN")
            ip_rotate = None
        elif not check_device(adb_path):
            print("  [adb] No device connected — falling back to manual VPN")
            ip_rotate = None
        else:
            from mimo_farmer.adb_ip_rotate import get_device_info, get_current_ip
            info = get_device_info(adb_path)
            ip = get_current_ip()
            print(f"  [adb] Device: {info.get('model', '?')} (Android {info.get('android', '?')})")
            print(f"  [adb] Current IP: {ip}")
            print(f"  [adb] Method: {'airplane mode (~15s)' if ip_rotate == 'adb' else 'data toggle (~8s)'}")
            adb_rotator = adb_path

    def rotate_ip():
        """Rotate IP: ADB (auto) or manual VPN."""
        if adb_rotator:
            method = "airplane" if ip_rotate == "adb" else "data"
            print(f"  [adb] Rotating IP via {'airplane mode' if method == 'airplane' else 'data toggle'}...")
            result = adb_rotate(method=method, adb=adb_rotator)
            if result.get("success"):
                changed = "✓ CHANGED" if result.get("changed") else "✗ same"
                print(f"  [adb] {result.get('ip_before', '?')} → {result.get('ip_after', '?')} ({changed})")
            else:
                print(f"  [adb] Rotation failed: {result.get('error')}")
        else:
            print("  [vpn] Ganti IP kamu sekarang (VPN/mobile hotspot).")
            try:
                input("  Tekan ENTER kalau udah ganti IP...")
            except (EOFError, KeyboardInterrupt):
                raise KeyboardInterrupt
            from mimo_farmer.adb_ip_rotate import get_current_ip
            new_ip = get_current_ip()
            if new_ip:
                print(f"  ✅ IP changed! Current IP: {new_ip}")
            else:
                print(f"  ✅ IP changed! Lanjut...")

    print(f"\n{'=' * 60}")
    print(f"  AUTO-FARM MODE | Target: ${target:.2f}")
    print(f"  Captcha: {captcha_mode}")
    print(f"{'=' * 60}")

    # Show current IP before starting
    from mimo_farmer.adb_ip_rotate import get_current_ip
    start_ip = get_current_ip()
    if start_ip:
        print(f"  🌐 Current IP: {start_ip}")
    else:
        print(f"  🌐 Current IP: (could not detect)")
    print()

    import random

    try:
        while total_bonus < target:
            account_num += 1
            is_main = current_main_referral is None

            # IP rotation prompt
            if account_num > 1:
                rotate_ip()

            # Determine referral
            if is_main:
                referral = None
                print(f"\n  [{account_num}] MAIN ACCOUNT (no referral)")
            else:
                referral = current_main_referral
                print(f"\n  [{account_num}] CHILD ACCOUNT (referral: {referral})")

            # Random delay between accounts (skip before first account)
            if account_num > 1:
                delay = random.randint(40, 60)
                print(f"  [delay] Waiting {delay}s before next account...")
                import time; time.sleep(delay)

            # Create account
            try:
                result = asyncio.run(create_account_with_retry(
                    referral_code=referral or DEFAULT_REFERRAL_CODE,
                    captcha_mode=captcha_mode,
                    account_num=account_num,
                    skip_referral=is_main,
                    cdp_url=cdp_url,
                ))
            except Exception as e:
                print(f"  [!] Error: {e}")
                continue

            if result is None:
                print(f"  [!] Account creation failed")
                continue

            # Check risk_control
            if result.get('risk_control'):
                print(f"  [!] RISK CONTROL detected")
                if not is_main:
                    print(f"  [!] Creating new main account...")
                    current_main_referral = None
                    consecutive_not_found = 0
                continue

            # Check referral not found (children only)
            if not is_main and result.get('referral_failed'):
                consecutive_not_found += 1
                print(f"  [!] Referral NOT FOUND ({consecutive_not_found}/{max_not_found})")
                if consecutive_not_found >= max_not_found:
                    print(f"  [!] Too many not_found — creating new main...")
                    current_main_referral = None
                    consecutive_not_found = 0
                continue

            # Check domain flagged (bonus $0)
            if result.get('domain_flagged'):
                domain = result.get('domain', '')
                if domain and domain not in DOMAINS_BLOCKLIST:
                    DOMAINS_BLOCKLIST.append(domain)
                    print(f"  [!] Domain '{domain}' blacklisted (bonus $0)")
                continue

            # Check gift balance
            gift = result.get('gift_balance', 0.0)
            if gift <= 0:
                print(f"  [!] Bonus $0 — skipping account")
                continue

            # Success — save account
            consecutive_not_found = 0
            total_bonus += gift
            saved_accounts.append(result)

            if is_main:
                current_main_referral = result.get('own_referral')
                current_main_email = result.get('email')
                print(f"  ✅ MAIN saved | Bonus: ${gift:.2f} | Referral: {current_main_referral}")
            else:
                # Child gets $2.72, but parent ALSO gets $2.00 referral bonus
                parent_bonus = 2.00 if result.get('referral') == current_main_referral else 0.0
                if parent_bonus > 0:
                    total_bonus += parent_bonus
                print(f"  ✅ CHILD saved | Bonus: ${gift:.2f} (+${parent_bonus:.2f} to parent)")

            print(f"  📊 Total bonus: ${total_bonus:.2f} / ${target:.2f}")

    except KeyboardInterrupt:
        print(f"\n\n  ⚠️  Ctrl+C detected! Saving {len(saved_accounts)} account(s) created so far...")

    # Save all accounts to batch file
    if saved_accounts:
        _save_combined(saved_accounts, "autofarm")

    print(f"\n{'=' * 60}")
    print(f"  AUTO-FARM COMPLETE")
    print(f"  Target: ${target:.2f}")
    print(f"  Achieved: ${total_bonus:.2f}")
    print(f"  Accounts saved: {len(saved_accounts)}")
    print(f"{'=' * 60}")

    return 0


def _prompt_ip_rotation(success_count: int) -> None:
    """Prompt user to change IP after threshold."""
    print(f"\n{'!' * 60}")
    print(f"  ⚠️  IP COOLDOWN ALERT")
    print(f"  Kamu udah bikin {success_count} akun berturut-turut.")
    print(f"  Risk control makin tinggi tiap 5 akun.")
    print(f"{'!' * 60}")
    try:
        choice = input("\n  Ganti IP dulu? [Y/n]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        choice = 'y'

    if choice == 'y':
        print("\n  ⏳ Ganti IP kamu sekarang (VPN/mobile hotspot).")
        try:
            input("  Tekan ENTER kalau udah ganti IP...")
        except (EOFError, KeyboardInterrupt):
            pass
        print("  ✅ IP changed! Lanjut nuyul...\n")
    else:
        print("  ⏭️  Lanjut tanpa ganti IP (risk control makin tinggi)\n")


def _run_parallel(count: int, referral: str, captcha_mode: str, parallel: int) -> int:
    """Create accounts in parallel batches."""
    from mimo_farmer.creator import create_account, create_account_with_retry

    async def run_batch(batch_size: int, start_num: int):
        tasks = [
            create_account_with_retry(referral_code=referral, captcha_mode=captcha_mode, account_num=start_num + i)
            for i in range(batch_size)
        ]
        return await asyncio.gather(*tasks, return_exceptions=True)

    results = []
    remaining = count
    batch_num = 0
    account_counter = 0

    while remaining > 0:
        batch_size = min(parallel, remaining)
        batch_num += 1
        account_counter += batch_size
        print(f"\n{'#' * 60}")
        print(f"  Batch {batch_num}: {batch_size} parallel account(s)")
        print(f"{'#' * 60}\n")

        try:
            batch_results = asyncio.run(run_batch(batch_size, account_counter - batch_size + 1))
            risk_detected = False
            for r in batch_results:
                if isinstance(r, Exception):
                    print(f"  [!] Error: {r}")
                    results.append(None)
                else:
                    results.append(r)
                    if r and r.get('risk_control'):
                        risk_detected = True
            if risk_detected:
                print(f"\n  [!] RISK CONTROL detected in batch {batch_num}!")
                print(f"  [!] Referral code '{referral}' is blocked or IP is flagged.")
                print(f"  [!] Create a NEW referral code and try again.")
                break
        except Exception as e:
            print(f"  [!] Batch error: {e}")
            results.extend([None] * batch_size)

        remaining -= batch_size

    success = sum(1 for r in results if r is not None)
    _save_combined(results, referral)
    print(f"\n{'=' * 60}")
    print(f"  Summary: {success}/{count} accounts created")
    print(f"{'=' * 60}")
    return 0 if success > 0 else 1


def _save_combined(results: list, referral: str) -> None:
    """Save all credentials in combined format with email links.

    Format:
    [1] — Main
    Mail: email@domain.com
    Link: https://generator.email/email@domain.com
    Pw: password
    Api-Key: sk-xxxxxxxxxx

    [2]
    Mail: email2@domain.com
    Link: https://generator.email/email2@domain.com
    Pw: password
    Api-Key: sk-xxxxxxxxxx
    """
    from mimo_farmer.config import ACCOUNTS_DIR

    valid = [r for r in results if r is not None and r.get('balance') and r.get('api_key') and not r.get('_promoted')]
    if not valid:
        return

    os.makedirs(ACCOUNTS_DIR, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    combined_path = os.path.join(ACCOUNTS_DIR, f"batch_{ts}.txt")

    lines = []
    for i, creds in enumerate(valid, 1):
        api_key = creds.get('api_key', 'N/A')
        # Validate: warn if key is masked
        if api_key and ('*' in api_key or '...' in api_key):
            print(f"  [!] Account {i}: API key is MASKED ({api_key[:15]}...) — re-run to get full key")
        
        # Check if this is a main account (has own_referral, no referral used)
        is_main = bool(creds.get('own_referral')) and not creds.get('referral')
        header = f"[{i}] — Main" if is_main else f"[{i}]"
        
        lines.append(header)
        lines.append(f"Mail: {creds['email']}")
        lines.append(f"Link: https://generator.email/{creds['email']}")
        lines.append(f"Pw: {creds['password']}")
        lines.append(f"Api-Key: {api_key}")
        lines.append("")

    with open(combined_path, "w") as f:
        f.write("\n".join(lines))

    print(f"\n  Combined credentials saved: {combined_path}")


def cmd_accounts(args) -> int:
    """Handle `mimo accounts` command."""
    if not os.path.isdir(ACCOUNTS_DIR):
        print("No accounts directory found. Run `mimo create` first.")
        return 1

    json_files = sorted([
        f for f in os.listdir(ACCOUNTS_DIR)
        if f.endswith('.json') and not f.startswith('export_')
    ])

    if not json_files:
        print("No accounts found.")
        return 0

    print(f"{'Email':<35} {'Balance':<12} {'Referral':<10} {'API Key':<8} {'Created'}")
    print("-" * 90)

    for filename in json_files:
        filepath = os.path.join(ACCOUNTS_DIR, filename)
        try:
            with open(filepath, 'r') as f:
                acct = json.load(f)
            email = acct.get('email', 'N/A')
            balance = acct.get('balance', 'N/A')
            referral = acct.get('referral', 'N/A')
            api_key = 'OK' if acct.get('api_key') else 'NO'
            created = acct.get('created', 'N/A')
            print(f"{email:<35} {balance:<12} {referral:<10} {api_key:<8} {created}")
        except (json.JSONDecodeError, KeyError):
            print(f"  [!] Could not parse {filename}")

    print(f"\nTotal: {len(json_files)} account(s)")
    return 0


def cmd_export(args) -> int:
    """Handle `mimo export` command."""
    if not os.path.isdir(ACCOUNTS_DIR):
        print("No accounts directory found. Run `mimo create` first.")
        return 1

    json_files = sorted([
        f for f in os.listdir(ACCOUNTS_DIR)
        if f.endswith('.json') and not f.startswith('export_')
    ])

    if not json_files:
        print("No accounts to export.")
        return 0

    accounts = []
    for filename in json_files:
        filepath = os.path.join(ACCOUNTS_DIR, filename)
        try:
            with open(filepath, 'r') as f:
                accounts.append(json.load(f))
        except (json.JSONDecodeError, KeyError):
            pass

    if not accounts:
        print("No valid accounts to export.")
        return 1

    # Determine output path
    output = args.output
    fmt = getattr(args, 'format', 'json')

    if output is None:
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        ext = 'json' if fmt == 'json' else 'txt'
        output = os.path.join(ACCOUNTS_DIR, f"export_{timestamp}.{ext}")

    if fmt == 'json':
        with open(output, 'w') as f:
            json.dump(accounts, f, indent=2)
    else:
        with open(output, 'w') as f:
            for i, acct in enumerate(accounts, 1):
                f.write(f"=== Account {i} ===\n")
                for key, value in acct.items():
                    f.write(f"{key}: {value}\n")
                f.write("\n")

    print(f"Exported {len(accounts)} account(s) to {output}")
    return 0


def cmd_web(args) -> int:
    """Handle `mimo web` command."""
    from mimo_farmer.web.server import run

    print(f"Starting mimo-farmer Web UI at http://{args.host}:{args.port}")
    run(host=args.host, port=args.port, reload=args.reload)
    return 0


def main() -> int:
    """Main CLI entry point."""
    parser = build_parser()
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return 0

    handlers = {
        "create": cmd_create,
        "accounts": cmd_accounts,
        "export": cmd_export,
        "web": cmd_web,
    }

    handler = handlers.get(args.command)
    if handler:
        return handler(args)

    parser.print_help()
    return 1
