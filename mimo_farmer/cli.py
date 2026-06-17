"""CLI interface for MiMo account creation.

Commands:
  mimo create              Create single account
  mimo create --count 5    Create 5 accounts sequentially
  mimo create --referral CODE  Custom referral code
  mimo create --fast       Reduced delays
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

from mimo_farmer.config import DEFAULT_REFERRAL_CODE, ACCOUNTS_DIR
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
  mimo create --fast            Reduced delays for faster creation
  mimo create --parallel 2      2 parallel browser instances
  mimo create --continuous      Keep creating until risk control
  mimo create --siklus          Cycle mode (1 main + 5 children per cycle)
  mimo create --count 10 --parallel 3 --fast
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
        "--fast", "-f",
        action="store_true",
        help="Fast mode — reduced delays between actions",
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
        help="Cycle mode: create main account then 5 child accounts using main's referral",
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
    from mimo_farmer.creator import create_account

    referral = args.referral
    count = args.count
    fast = args.fast
    parallel = args.parallel
    continuous = args.continuous
    siklus = args.siklus

    # --siklus and --continuous don't mix
    if siklus and continuous:
        print("  [!] --siklus and --continuous cannot be used together.")
        return 1

    # --siklus and --count don't mix
    if siklus and count is not None:
        print("  [!] --siklus ignores --count. Remove --count or pick one.")
        return 1

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
        print(f"SIKLUS MODE | {siklus_count} siklus | Fast: {fast}")
        print(f"Tiap siklus: 1 akun utama + 5 akun anak = 6 akun")
        print(f"Total akun: {siklus_count * 6}")
        print()
        return _run_siklus(siklus_count, fast)

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
        print(f"CONTINUOUS MODE | Referral: {referral} | Fast: {fast}")
        print("Creating accounts until risk control detected (Ctrl+C to stop)\n")
        return _run_continuous(referral, fast)

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
    print(f"Creating {count} account(s) | Referral: {referral} | Fast: {fast} | Parallel: {parallel}")
    print()

    if parallel > 1:
        return _run_parallel(count, referral, fast, parallel)
    else:
        return _run_sequential(count, referral, fast)


def _run_sequential(count: int, referral: str, fast: bool) -> int:
    """Create accounts one at a time."""
    import time as _time
    from mimo_farmer.creator import create_account

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
            result = asyncio.run(create_account(
                referral_code=referral,
                fast=fast,
                account_num=i + 1,
            ))
            results.append(result)

            # Risk control detected → stop batch, suggest new referral code
            if result and result.get('risk_control'):
                print(f"\n  [!] RISK CONTROL detected on account {i + 1}!")
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

        # IP cooldown alert — every 5 successful accounts
        success_count = sum(1 for r in results if r is not None)
        if success_count % 5 == 0 and i + 1 < count:
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


def _run_continuous(referral: str, fast: bool) -> int:
    """Create accounts one by one until risk control is detected."""
    from mimo_farmer.creator import create_account

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
                result = asyncio.run(create_account(
                    referral_code=referral,
                    fast=fast,
                    account_num=account_num,
                ))
            except Exception as e:
                print(f"  [!] Error on account {account_num}: {e}")
                failures += 1
                continue

            # Risk control → STOP
            if result and result.get('risk_control'):
                print(f"\n  [!] RISK CONTROL detected on account #{account_num}!")
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

            # IP cooldown alert — every 5 successful accounts
            if success_count % 5 == 0:
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


def _run_siklus(siklus_count: int, fast: bool) -> int:
    """Cycle mode: create main account then 5 child accounts per siklus.

    Flow per siklus:
    1. Create main account (no referral, skip_referral=True)
    2. Extract main's referral code
    3. Create 5 child accounts using main's referral code
    4. IP rotation after every 5 successful accounts (all modes)
    """
    import time as _time
    from mimo_farmer.creator import create_account

    all_results = []  # Track all results for combined save
    total_success = 0
    total_fail = 0
    CHILDREN_PER_SIKLUS = 5
    last_siklus = 0  # Track last completed siklus for partial summary

    try:
        for s in range(1, siklus_count + 1):
            # Cooldown between siklus cycles (not before first)
            if s > 1:
                cooldown = random.randint(1, 10)
                print(f"\n  ⏳ Cooldown {cooldown}s between siklus cycles...")
                _time.sleep(cooldown)

            print(f"\n{'=' * 60}")
            print(f"  🔄 SIKLUS {s}/{siklus_count}")
            print(f"{'=' * 60}\n")

            # Step 1: Create main account (no referral)
            print(f"  [SIKLUS {s}] Creating MAIN account (no referral)...")
            try:
                main_result = asyncio.run(create_account(
                    referral_code="",
                    fast=fast,
                    account_num=(s - 1) * 6 + 1,
                    skip_referral=True,
                ))
            except Exception as e:
                print(f"  [!] Main account error: {e}")
                total_fail += 1 + CHILDREN_PER_SIKLUS  # main + all children
                continue

            if main_result is None:
                print(f"  [!] Main account failed — skipping this siklus.")
                total_fail += 1 + CHILDREN_PER_SIKLUS
                continue

            # Check main account risk control BEFORE creating children
            if main_result.get('risk_control'):
                print(f"  [!] MAIN account hit risk control — skipping children.")
                total_fail += 1 + CHILDREN_PER_SIKLUS
                continue

            total_success += 1
            all_results.append(main_result)

            main_referral = main_result.get('own_referral')
            main_email = main_result.get('email', 'N/A')
            main_balance = main_result.get('balance', 'N/A')
            # Initialize rolling safe domain from main account
            current_safe_domain = main_email.split('@')[1] if '@' in main_email else None
            print(f"\n  ✅ MAIN account created!")
            print(f"     Email: {main_email}")
            print(f"     Balance: {main_balance}")
            print(f"     Own Referral: {main_referral or 'FAILED TO EXTRACT'}")
            if current_safe_domain:
                print(f"     Domain: {current_safe_domain} (will reuse for children)")

            if not main_referral:
                print(f"  [!] No referral code extracted — cannot create child accounts.")
                print(f"  [!] Skipping children for siklus {s}.")
                total_fail += CHILDREN_PER_SIKLUS
                last_siklus = s
                continue

            # IP rotation check after main account
            if total_success % 5 == 0:
                _prompt_ip_rotation(total_success)

            # Cooldown before children
            cooldown = random.randint(1, 10)
            print(f"\n  ⏳ Cooldown {cooldown}s before creating children...")
            _time.sleep(cooldown)

            # Step 2: Create 5 child accounts using main's referral
            children_success = 0
            child_num_counter = (s - 1) * 6 + 2  # First child number
            MAX_REFERRAL_RETRIES = 2  # Max replacement attempts per slot

            for c in range(1, CHILDREN_PER_SIKLUS + 1):
                child_num = child_num_counter
                child_num_counter += 1
                print(f"\n  [SIKLUS {s}] Child {c}/{CHILDREN_PER_SIKLUS} (account #{child_num})...")

                # Cooldown between children
                if c > 1:
                    cooldown = random.randint(1, 10)
                    print(f"\n  ⏳ Cooldown {cooldown}s between children...")
                    _time.sleep(cooldown)

                slot_done = False
                for retry in range(MAX_REFERRAL_RETRIES + 1):
                    if retry > 0:
                        print(f"\n  [!] Creating replacement account for slot {c} (retry {retry}/{MAX_REFERRAL_RETRIES})...")
                        child_num = child_num_counter
                        child_num_counter += 1
                        cooldown = random.randint(1, 5)
                        _time.sleep(cooldown)

                    try:
                        child_result = asyncio.run(create_account(
                            referral_code=main_referral,
                            fast=fast,
                            account_num=child_num,
                            preferred_domain=current_safe_domain,
                        ))
                    except Exception as e:
                        print(f"  [!] Child {c} error: {e}")
                        break

                    if child_result is None:
                        print(f"  [!] Child {c} failed.")
                        break

                    # Update rolling safe domain
                    child_email = child_result.get('email', '')
                    if '@' in child_email:
                        child_domain = child_email.split('@')[1]
                        if child_domain != current_safe_domain:
                            print(f"  🔄 Domain switched: {current_safe_domain} → {child_domain}")
                            current_safe_domain = child_domain

                    # Check if referral was "not found" — need replacement
                    if child_result.get('referral_failed'):
                        print(f"  [!] Referral code not found — account created but no referral bonus")
                        if retry < MAX_REFERRAL_RETRIES:
                            print(f"  [!] Will create replacement account...")
                            # Still save this account (it exists, just no bonus)
                            total_success += 1
                            all_results.append(child_result)
                            continue
                        else:
                            print(f"  [!] Max retries reached for slot {c}")
                            total_success += 1
                            all_results.append(child_result)
                            slot_done = True
                            break

                    if child_result.get('risk_control'):
                        remaining = CHILDREN_PER_SIKLUS - c
                        print(f"  [!] RISK CONTROL on child {c}!")
                        print(f"  [!] Main referral '{main_referral}' may be blocked.")
                        print(f"  [!] Stopping children for siklus {s}. ({remaining} children skipped)")
                        total_fail += 1 + remaining
                        slot_done = True  # Break outer loop too
                        break

                    # Success
                    total_success += 1
                    children_success += 1
                    all_results.append(child_result)
                    child_email_display = child_result.get('email', 'N/A')
                    child_balance = child_result.get('balance', 'N/A')
                    print(f"  ✅ Child {c} created! Email: {child_email_display} | Balance: {child_balance}")
                    slot_done = True
                    break

                if not slot_done and not child_result.get('risk_control'):
                    total_fail += 1

                # IP rotation check
                if total_success % 5 == 0:
                    _prompt_ip_rotation(total_success)

                # Check if risk_control broke the outer loop
                if child_result and child_result.get('risk_control'):
                    break

            last_siklus = s
            print(f"\n  Siklus {s} done: 1 main + {children_success}/{CHILDREN_PER_SIKLUS} children")

    except KeyboardInterrupt:
        print(f"\n\n  [!] Interrupted by user (Ctrl+C)")
        print(f"  [!] Saving partial results...")

    # Calculate actual counts for summary
    actual_main = sum(1 for r in all_results if r and r.get('own_referral') is not None)
    actual_children = sum(1 for r in all_results if r and r.get('own_referral') is None)
    child_bonus = actual_children * 2

    # Final summary
    print(f"\n{'=' * 60}")
    print(f"  🔄 SIKLUS MODE — FINAL SUMMARY")
    print(f"{'=' * 60}")
    print(f"  Siklus completed: {last_siklus}/{siklus_count}")
    print(f"  Total success:    {total_success}")
    print(f"  Total failed:     {total_fail}")
    print(f"  Main accounts:    {actual_main}")
    print(f"  Child accounts:   {actual_children}")
    print(f"  Referral bonus:   ${child_bonus:.2f} (${2:.2f} × {actual_children} children)")
    print(f"{'=' * 60}")

    # Save combined
    _save_combined(all_results, "siklus")
    return 0 if total_success > 0 else 1


def _prompt_ip_rotation(success_count: int) -> None:
    """Prompt user to change IP after threshold."""
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


def _run_parallel(count: int, referral: str, fast: bool, parallel: int) -> int:
    """Create accounts in parallel batches."""
    from mimo_farmer.creator import create_account

    async def run_batch(batch_size: int, start_num: int):
        tasks = [
            create_account(referral_code=referral, fast=fast, account_num=start_num + i)
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
    """Save all credentials in combined format.

    Format:
    [1]
    Mail: email@banri.xyz
    Pw: papoi123
    Api-Key: sk-xxxxxxxxxx

    [2]
    ...
    """
    from mimo_farmer.config import ACCOUNTS_DIR

    valid = [r for r in results if r is not None and r.get('balance')]
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
        lines.append(f"[{i}]")
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
