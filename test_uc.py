"""Login test with undetected-chromedriver."""
import asyncio
import time
import undetected_chromedriver as uc

LOGIN_URL = "https://global.account.xiaomi.com/fe/service/login?_locale=en&source=&region=ID&sid=api-platform"

options = uc.ChromeOptions()
options.add_argument('--no-first-run')
options.add_argument('--no-default-browser-check')

print("[1] Launch undetected Chrome...")
driver = uc.Chrome(options=options, headless=False, use_subprocess=True)

try:
    print("[2] Navigate to login...")
    driver.get(LOGIN_URL)
    time.sleep(3)

    # Accept cookies
    try:
        btn = driver.find_element("xpath", '//button[contains(text(), "Accept cookies")]')
        if btn.is_displayed():
            btn.click()
            time.sleep(0.5)
    except Exception:
        pass

    print("[3] Fill email...")
    email = driver.find_element("xpath", '//input[contains(@placeholder, "Email") or @type="email"]')
    email.send_keys("4cniy0m9q8@rexornge.net")
    time.sleep(0.3)

    print("[4] Fill password...")
    pw = driver.find_element("xpath", '//input[@type="password"]')
    pw.send_keys("MmaTUm11MU!9")
    time.sleep(0.3)

    print("[5] Check agreement...")
    try:
        cb = driver.find_element("xpath", '//input[@type="checkbox"]')
        if not cb.is_selected():
            cb.click()
            time.sleep(0.3)
    except Exception:
        pass

    print("[6] Click Sign in...")
    btn = driver.find_element("xpath", '//button[contains(text(), "Sign in") and not(contains(text(), "Google")) and not(contains(text(), "Facebook"))]')
    btn.click()
    time.sleep(8)

    url = driver.current_url
    print(f"[7] URL: {url}")

    if "platform.xiaomimimo.com" in url:
        print("[✓] Login success!")
        driver.get("https://platform.xiaomimimo.com/api/v1/balance")
        time.sleep(2)
        body = driver.find_element("tag name", "body").text
        print(f"[✓] Balance: {body}")
    else:
        body = driver.find_element("tag name", "body").text
        if "10025" in body:
            print("[✗] Error :10025 — still blocked")
        elif "automated" in body.lower():
            print("[✗] reCAPTCHA automated")
        else:
            print(f"[?] Unknown: {body[:300]}")

        print("[!] Waiting 60s for manual intervention...")
        time.sleep(60)
        url = driver.current_url
        print(f"[8] Final URL: {url}")

finally:
    driver.quit()
