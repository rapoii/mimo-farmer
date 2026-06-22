# Plan: Auto-Farm Mode (--target-balance)

## Overview
Fully automatic account farming: create main + children, track bonus balance, stop at target.

## New CLI Flag
```
mimo create --target-balance 50
```
- Fully automatic, no input needed
- Uses default referral for first main, then auto-generates from main accounts
- IP rotation required between every account

## Flow

### Phase 1: Create Main Account
1. Pick random email domain (not blacklisted/unsafe)
2. Generate email + password
3. Rotate IP (ADB or prompt)
4. Run signup pipeline
5. Check bonus balance (giftBalance)
   - If $0 → blacklist domain, retry with new domain
   - If $0.72+ → save main, extract referral code
6. Track bonus: `total_bonus += giftBalance`

### Phase 2: Create Children (loop)
1. Pick random email domain (not blacklisted)
2. Generate email + password
3. Rotate IP
4. Run signup pipeline with main's referral
5. Check result:
   - **Risk control** → don't save → go to Phase 1 (new main)
   - **Not found** → don't save → retry child with new email (same main)
   - **Not found persists** → risk control → new main
   - **Success** → check bonus balance
     - If $0 → blacklist domain, retry child
     - If $0.72+ → save, add to total
6. Check `total_bonus >= target` → stop

### Phase 3: Cleanup
- Save all valid accounts to batch file
- Print summary: total accounts, total bonus, domains blacklisted

## Files Changed

### config.py
- Add `TARGET_BALANCE_DEFAULT = 10`

### cli.py
- Add `--target-balance` arg
- Add `_run_target_balance(target, ip_rotate)` function
- Import domain blacklist from config

### creator.py
- `create_account()` already returns balance info
- Need to add `giftBalance` to return dict
- Ensure risk_control / not_found flags are set properly

### Domain Blacklist
- Load from config.DOMAINS_BLOCKLIST
- Auto-add domains where giftBalance == 0
- Save blacklist to file for persistence across runs

## IP Rotation
- Required between EVERY account (main→child, child→child, child→main)
- Use ADB if available, otherwise prompt user
- `--ip-rotate adb|data` flag supported

## Success Criteria
1. `mimo create --target-balance 50` runs fully automatic
2. Stops when total bonus >= $50
3. No risk control / not found accounts saved
4. Domains with $0 bonus auto-blacklisted
5. IP rotates between every account
