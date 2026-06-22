"""Check MiMo balance using cookies from existing Chrome session."""
import requests
import browser_cookie3

BALANCE_API = "https://platform.xiaomimimo.com/api/v1/balance"

print("[1] Extracting cookies from Chrome...")
try:
    cj = browser_cookie3.chrome(domain_name='.xiaomimimo.com')
    print(f"[2] Found {len(cj)} cookies for xiaomimimo.com")
    
    # Show cookies
    for c in cj:
        print(f"    {c.name}: {c.value[:30]}...")
except Exception as e:
    print(f"[✗] Error: {e}")
    # Try with .xiaomi.com too
    try:
        cj = browser_cookie3.chrome(domain_name='.xiaomi.com')
        print(f"[2] Found {len(cj)} cookies for xiaomi.com")
    except Exception as e2:
        print(f"[✗] Error2: {e2}")
        exit(1)

print("[3] Calling balance API...")
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36',
    'Referer': 'https://platform.xiaomimimo.com/console/balance',
}

try:
    r = requests.get(BALANCE_API, cookies=cj, headers=headers, timeout=15)
    print(f"[4] Status: {r.status_code}")
    print(f"[5] Response: {r.text[:500]}")
except Exception as e:
    print(f"[✗] Request error: {e}")
