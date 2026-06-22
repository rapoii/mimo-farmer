"""SeleniumBase UC login with local chromedriver."""
import sys
sys.path.insert(0, ".")
from seleniumbase import SB

CHROMEDRIVER = r"C:\Users\rafi\.wdm\drivers\chromedriver\win64\149.0.7827.115\chromedriver-win64\chromedriver.exe"
LOGIN_URL = "https://global.account.xiaomi.com/fe/service/login?_locale=en&source=&region=ID&sid=api-platform"

with SB(uc=True, headless=False, driver_path=CHROMEDRIVER) as sb:
    print("[1] Navigate to login...")
    sb.uc_open_with_reconnect(LOGIN_URL, reconnect_time=6)
    
    url = sb.get_current_url()
    print(f"[2] URL: {url}")
    
    body = sb.get_text("body") if sb.is_element_visible("body") else ""
    
    if "10025" in body:
        print("[✗] Error :10025")
    elif "platform.xiaomimimo.com" in url:
        print("[✓] Already logged in!")
    else:
        print("[3] Fill email...")
        email_sel = 'input[placeholder*="Email"], input[type="email"]'
        sb.type(email_sel, "4cniy0m9q8@rexornge.net")
        
        print("[4] Fill password...")
        sb.type('input[type="password"]', "MmaTUm11MU!9")
        
        print("[5] Check agreement...")
        if sb.is_element_visible('input[type="checkbox"]'):
            sb.click('input[type="checkbox"]')
        
        print("[6] Click Sign in...")
        sb.click('button:has-text("Sign in")')
        
        import time
        time.sleep(8)
        
        url = sb.get_current_url()
        print(f"[7] URL: {url}")
    
    if "platform.xiaomimimo.com" in sb.get_current_url():
        print("[✓] Login success!")
        sb.open("https://platform.xiaomimimo.com/api/v1/balance")
        time.sleep(2)
        body = sb.get_text("body")
        print(f"[✓] Balance: {body}")
    else:
        body = sb.get_text("body") if sb.is_element_visible("body") else ""
        if "10025" in body:
            print("[✗] Error :10025")
        elif "automated" in body.lower():
            print("[✗] reCAPTCHA")
        else:
            print(f"[?] {body[:300]}")
        
        print("[!] Waiting 60s for manual...")
        time.sleep(60)
        print(f"[8] Final URL: {sb.get_current_url()}")
