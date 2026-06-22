"""
Quick balance checker using cookies from Chrome.
Usage:
  1. Get cookies from Chrome: F12 → Application → Cookies → platform.xiaomimimo.com
  2. Update COOKIES dict below
  3. python check_balance_cookies.py
"""
import requests
import json
import sys

# === UPDATE THESE COOKIES FROM CHROME ===
# F12 → Application → Cookies → platform.xiaomimimo.com
# Or: F12 → Network → refresh → click any request → copy Cookie header
COOKIES = {
    'userId': '6877935239',
    'serviceToken': 'yVHEDQlNiFT1WavLtPFne7PF87qatzVP4P9m7tzwZdx9+Yh5DSfazTkIfC4usoBE6veEgQ6O5Bl0joatxQuZWAUn6cmcRxZxFUp8DA/PxuJIIL2sTNOQKGm8hnXebCQ8mkohVJyjv6nAqzPx9Xr5AlQN/9roBETU/8RyQeZjf+HpGHYF4Ptu9zhzJFL9WRTJ8+7f8LMQGxPHivy3nXmMYmKBKHzZ8vCwng1B8C01LnnL2RTnBVJ84bhcdrJc6DBEPVE1TWoA5a/QY20WrVxaQxqdZ4pHSr6d+4T7ekFW0y13M3KvkvLwMX3KF8UCEYLajwZ3a25lh0tsl1t+rSpCE4vBf2+hEZvHfDnVpxHvK+4=',
    'api-platform_slh': 'Sq15hloDqtRc+rIl9B72b6s0jUk=',
    'api-platform_ph': 'J6lcQSerHVe81r7JrWTtAQ=='
}

def check_balance(cookies=None):
    if cookies is None:
        cookies = COOKIES
    
    try:
        # Profile
        r1 = requests.get(
            'https://platform.xiaomimimo.com/api/v1/userProfile',
            cookies=cookies, timeout=10
        )
        if r1.status_code == 401:
            print('ERROR: Cookies expired! Refresh from Chrome.')
            return None
        profile = r1.json()['data']

        # Balance
        r2 = requests.get(
            'https://platform.xiaomimimo.com/api/v1/balance',
            cookies=cookies, timeout=10
        )
        balance = r2.json()['data']

        result = {
            'userId': profile['userId'],
            'email': profile.get('email', 'N/A'),
            'balance': balance['balance'],
            'giftBalance': balance['giftBalance'],
            'cashBalance': balance['cashBalance'],
            'currency': balance['currency'],
        }

        print(f'=== MiMo Account ===')
        print(f'User ID:    {result["userId"]}')
        print(f'Email:      {result["email"]}')
        print(f'Balance:    ${result["balance"]} {result["currency"]}')
        print(f'Gift:       ${result["giftBalance"]}')
        print(f'Cash:       ${result["cashBalance"]}')
        return result

    except Exception as e:
        print(f'ERROR: {e}')
        return None


if __name__ == '__main__':
    check_balance()
