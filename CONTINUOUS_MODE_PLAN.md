# CONTINUOUS MODE — IMPLEMENTATION PLAN

**File:** `mimo_farmer/cli.py`

## Overview

Run account creation in a loop until user presses Ctrl+C. After stopping, save all successful credentials and print session summary.

```
mimo create --continuous --referral ABC123
mimo create --continuous --referral ABC123 --fast
mimo create --continuous --referral ABC123 --parallel 3
```

---

## 1. Argparse Flag

**Where:** `build_parser()`, after `--parallel` block (~line 82)

```python
p_create.add_argument(
    "--continuous", "-c",
    action="store_true",
    help="Run continuously until Ctrl+C (no account count needed)",
)
```

Mutually exclusive with `--count`: if `--continuous` is set, skip the count prompt entirely.

---

## 2. cmd_create Changes

**Where:** `cmd_create()`, after referral resolution, before count prompt (~line 131)

```python
if args.continuous:
    return _run_continuous(referral, fast, parallel)
```

This bypasses the count prompt. Count becomes infinite.

---

## 3. _run_continuous Function (NEW)

```python
def _run_continuous(referral: str, fast: bool, parallel: int) -> int:
    """Create accounts non-stop until Ctrl+C or fatal error."""
    from mimo_farmer.creator import create_account

    results = []
    account_num = 0
    consecutive_failures = 0
    start_time = time.time()
    MAX_CONSECUTIVE_FAILURES = 3

    print(f"Continuous mode — press Ctrl+C to stop\n")

    try:
        while True:
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

                # Risk control → hard stop
                if result and result.get('risk_control'):
                    results.append(result)
                    print(f"\n  [!] RISK CONTROL detected!")
                    print(f"  [!] Stopping. Use new referral code.")
                    break

                # Failure → track consecutive
                if result is None:
                    consecutive_failures += 1
                    results.append(None)
                    print(f"\n  [!] Failed ({consecutive_failures}/{MAX_CONSECUTIVE_FAILURES})")
                    if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                        print(f"\n  [!] {MAX_CONSECUTIVE_FAILURES} consecutive failures — stopping.")
                        break
                else:
                    consecutive_failures = 0
                    results.append(result)

                _print_tally(results, start_time)

            except (ConnectionError, TimeoutError, OSError) as e:
                consecutive_failures += 1
                results.append(None)
                print(f"  [!] Network error: {e}")
                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    print(f"\n  [!] {MAX_CONSECUTIVE_FAILURES} consecutive failures — stopping.")
                    break
                backoff = min(30, 5 * (2 ** (consecutive_failures - 1)))
                print(f"  [!] Retrying in {backoff}s...")
                time.sleep(backoff)

    except KeyboardInterrupt:
        print(f"\n\n  [*] Stopped by user (Ctrl+C)")

    _print_final_summary(results, start_time, account_num)
    _save_combined(results, referral)
    return 0
```

---

## 4. _print_tally Helper (NEW)

```python
def _print_tally(results: list, start_time: float) -> None:
    """Print running stats after each attempt."""
    elapsed = time.time() - start_time
    total = len(results)
    success = sum(1 for r in results if r is not None)
    failed = total - success
    rate = success / (elapsed / 3600) if elapsed > 0 else 0

    print(f"\n  ── Tally: {success} OK | {failed} failed | "
          f"{total} total | {elapsed:.0f}s elapsed | "
          f"{rate:.1f}/hr ──")
```

---

## 5. _print_final_summary Helper (NEW)

```python
def _print_final_summary(results: list, start_time: float, attempted: int) -> None:
    """Print session summary on exit."""
    elapsed = time.time() - start_time
    success = sum(1 for r in results if r is not None)
    failed = len(results) - success
    risk = sum(1 for r in results if r and r.get('risk_control'))
    rate = success / (elapsed / 3600) if elapsed > 0 else 0

    print(f"\n{'=' * 60}")
    print(f"  CONTINUOUS MODE — SESSION SUMMARY")
    print(f"{'=' * 60}")
    print(f"  Attempted:    {attempted}")
    print(f"  Successful:   {success}")
    print(f"  Failed:       {failed}")
    if risk:
        print(f"  Risk-blocked: {risk}")
    print(f"  Duration:     {elapsed:.0f}s ({elapsed/60:.1f} min)")
    print(f"  Rate:         {rate:.1f} accounts/hr")
    print(f"{'=' * 60}")
```

---

## 6. Edge Cases

| Scenario | Behavior |
|---|---|
| **Ctrl+C** | Caught by outer try/except. In-flight browser abandoned. All accumulated results saved. Summary printed. |
| **3 consecutive failures** | Stops loop automatically. Saves whatever succeeded. Returns 0 if any success. |
| **Risk control** | Hard stop immediately. Risk-blocked account appended to results. `_save_combined` filters by `balance=='$2.72'` so risk-blocked excluded from combined file. |
| **Network errors** | Caught separately. Exponential backoff: 5s → 10s → 20s → 30s cap. Count toward consecutive failure limit. |
| **Generic Exception** | Caught inside loop. Appends None, increments consecutive failures. Loop continues unless limit hit. |

---

## 7. File Changes Summary

| Function | Action |
|---|---|
| `build_parser()` | **MODIFIED** — add `--continuous` flag |
| `cmd_create()` | **MODIFIED** — add continuous branch before count prompt |
| `_run_continuous()` | **NEW** — main continuous loop (~50 lines) |
| `_print_tally()` | **NEW** — running stats printer |
| `_print_final_summary()` | **NEW** — session summary printer |
| `_run_sequential()` | Unchanged |
| `_run_parallel()` | Unchanged |
| `_save_combined()` | Unchanged (already filters None + non-$2.72) |

---

## 8. Help Text Updates

Add to `build_parser` epilog:
```
  mimo create --continuous -r ABC123 --fast
  mimo create --continuous -r ABC123 --parallel 3
```

Add to module docstring:
```
  mimo create --continuous   Run until Ctrl+C
```
