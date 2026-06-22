"""Login with Selenium using existing chromedriver + Chrome profile."""
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

LOGIN_URL = "https://global.account.xiaomi.com/fe/service/login?_locale=en&source=&region=ID&sid=api-platform"
CHROMEDRIVER = r"C:\Users\rafi\.wdm\drivers\chromedriver\win64\149.0.7827.115\chromedriver-win64\chromedriver.exe"

options = Options()
# Use Rafi's existing Chrome profile (cookies, extensions, fingerprint)
options.add_argument(r'--user-data-dir=C:\Users\rafi\AppData\Local\Google\Chrome\User Data')
options.add_argument('--profile-directory=Default')
options.add_experimental_option("excludeSwitches", ["enable-automation"])
options.add_experimental_option('useAutomationExtension', False)

service = Service(CHROMEDRIVER)

print("[1] Launch Chrome with existing profile...")
driver = webdriver.Chrome(service=service, options=options)

try:
    driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
        'source': 'Object.defineProperty(navigator, "webdriver", {get: () => undefined})'
    })

    print("[2] Navigate to login...")
    driver.get(LOGIN_URL)
    time.sleep(3)

    url = driver.current_url
    print(f"[3] URL: {url}")

    if "platform.xiaomimimo.com" in url:
        print("[✓] Already logged in!")
    else:
        print("[4] Fill email...")
        email = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, '//input[contains(@placeholder, "Email") or @type="email"]'))
        )
        email.clear()
        email.send_keys("4cniy0m9q8@rexornge.net")
        time.sleep(0.3)

        print("[5] Fill password...")
        pw = driver.find_element(By.XPATH, '//input[@type="password"]')
        pw.clear()
        pw.send_keys("MmaTUm11MU!9")
        time.sleep(0.3)

        print("[6] Check agreement...")
        try:
            cb = driver.find_element(By.XPATH, '//input[@type="checkbox"]')
            if not cb.is_selected():
                cb.click()
                time.sleep(0.3)
        except Exception:
            pass

        print("[7] Click Sign in...")
        btn = driver.find_element(By.XPATH, '//button[contains(text(), "Sign in") and not(contains(text(), "Google")) and not(contains(text(), "Facebook"))]')
        btn.click()
        time.sleep(8)

    url = driver.current_url
    print(f"[8] URL: {url}")

    if "platform.xiaomimimo.com" in url:
        print("[✓] Login success! Checking balance...")
        driver.get("https://platform.xiaomimimo.com/api/v1/balance")
        time.sleep(2)
        body = driver.find_element(By.TAG_NAME, "body").text
        print(f"[✓] Balance: {body}")
    else:
        body = driver.find_element(By.TAG_NAME, "body").text
        if "10025" in body:
            print("[✗] Error :10025")
        else:
            print(f"[?] {body[:300]}")

finally:
    driver.quit()
