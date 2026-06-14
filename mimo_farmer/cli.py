"""CLI interface for MiMo account creation.

Commands:
  mimo create              Create single account
  mimo create --count 5    Create 5 accounts sequentially
  mimo create --referral CODE  Custom referral code
  mimo create --fast       Reduced delays
  mimo create --parallel 2 Parallel browser instances
  mimo accounts            List created accounts
  mimo export              Export all credentials to single file
"""

import argparse
import asyncio
import json
import os
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
  mimo create --count 10 --parallel 3 --fast
  mimo accounts                 List all created accounts
  mimo export                   Export all credentials to file
  mimo export --output creds.json
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
        default=1,
        metavar="N",
        help="Number of accounts to create (default: 1)",
    )
    p_create.add_argument(
        "--referral", "-r",
        type=str,
        default=DEFAULT_REFERRAL_CODE,
        metavar="CODE",
        help=f"Referral code to use (default: {DEFAULT_REFERRAL_CODE})",
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

    return parser


def cmd_create(args) -> int:
    """Handle `mimo create` command."""
    from mimo_farmer.creator import create_account

    referral = args.referral
    count = args.count
    fast = args.fast
    parallel = args.parallel

    # Interactive prompts — WAJIB diisi
    while True:
        referral = input("Kode referral: ").strip().upper()
        if referral:
            break
        print("  [!] Kode referral wajib diisi!")

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
    from mimo_farmer.creator import create_account

    results = []
    for i in range(count):
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
            if result is None:
                print(f"\n  [!] Account {i + 1} failed — stopping batch.")
                break
        except Exception as e:
            print(f"  [!] Error: {e}")
            results.append(None)
            break

    success = sum(1 for r in results if r is not None)
    _save_combined(results, referral)
    print(f"\n{'=' * 60}")
    print(f"  Summary: {success}/{count} accounts created")
    print(f"{'=' * 60}")
    return 0 if success > 0 else 1


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
            for r in batch_results:
                if isinstance(r, Exception):
                    print(f"  [!] Error: {r}")
                    results.append(None)
                else:
                    results.append(r)
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

    valid = [r for r in results if r is not None and r.get('balance') == '$2.72']
    if not valid:
        return

    os.makedirs(ACCOUNTS_DIR, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    combined_path = os.path.join(ACCOUNTS_DIR, f"batch_{ts}.txt")

    lines = []
    for i, creds in enumerate(valid, 1):
        lines.append(f"[{i}]")
        lines.append(f"Mail: {creds['email']}")
        lines.append(f"Pw: {creds['password']}")
        lines.append(f"Api-Key: {creds.get('api_key', 'N/A')}")
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
        f for f in os.listdir(ACCOUNTS_DIR) if f.endswith('.json')
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
        f for f in os.listdir(ACCOUNTS_DIR) if f.endswith('.json')
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
    }

    handler = handlers.get(args.command)
    if handler:
        return handler(args)

    parser.print_help()
    return 1
