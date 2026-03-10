from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import traceback
import sys

options = Options()
options.add_argument("--headless=new")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--window-size=1920,1080")

driver = webdriver.Chrome(options=options)
wait = WebDriverWait(driver, 20)

try:
    driver.get("http://test.treecom.site:30437/")

    # Enter URL
    url_box = wait.until(
        EC.presence_of_element_located((By.ID, "urlInput"))
    )

    url_box.send_keys("https://docs.docker.com/engine/install/rhel/")

    # Click shorten
    shorten_btn = wait.until(
        EC.element_to_be_clickable((By.ID, "shortenBtn"))
    )

    driver.execute_script("arguments[0].click();", shorten_btn)

    # Wait for result section
    wait.until(
        EC.visibility_of_element_located((By.ID, "resultSection"))
    )

    print("Short URL generated successfully")

    # Click 5th star
    stars = wait.until(
        EC.presence_of_all_elements_located((By.CSS_SELECTOR, ".star-btn"))
    )

    stars[4].click()

    # Enter feedback
    feedback = driver.find_element(By.ID, "feedbackInput")
    feedback.send_keys("Great service. URL shortening works perfectly!")

    # Submit feedback
    submit_btn = driver.find_element(By.ID, "submitRatingBtn")
    driver.execute_script("arguments[0].click();", submit_btn)

    print("Feedback submitted successfully")

except Exception as e:
    print("Test failed!")
    print(e)
    traceback.print_exc()
    sys.exit(1)

    # Save screenshot for debugging
    driver.save_screenshot("selenium_debug.png")

finally:
    driver.quit()
