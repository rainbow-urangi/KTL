import os
from urllib.parse import urlparse

from ktl_runtime import business_step
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

SCENARIO_ID = "CANON-SCN-b942446b030f547453a43c70"

LOGIN_URL = "https://rainbowlab.ai.kr/rbem"
CARDS_URL = "https://rainbowlab.ai.kr/mypage/cards"
USERNAME_SELECTOR = "#loginId"
PASSWORD_SELECTOR = "#password"
SUBMIT_SELECTOR = 'form.login-card button.login-submit[type="submit"]'


def scroll_and_wait_for_hit(driver, wait, element):
    driver.execute_script(
        "arguments[0].scrollIntoView({block:'center',inline:'center',behavior:'instant'});",
        element,
    )
    hit = wait.until(
        lambda d: d.execute_script(
            """
            const el = arguments[0];
            const r = el.getBoundingClientRect();
            const x = r.left + r.width / 2;
            const y = r.top + r.height / 2;
            if (x < 0 || y < 0 || x >= innerWidth || y >= innerHeight) return false;
            const hit = document.elementFromPoint(x, y);
            return !!hit && (hit === el || el.contains(hit));
            """,
            element,
        )
    )
    assert hit, "Target is centered and receives pointer events"


def visible_text_is_nonempty(driver):
    return driver.execute_script(
        """
        const matches = [...document.querySelectorAll(
          '.business-card-detail-modal__body > section.business-card-detail-modal__section:first-child > .business-card-detail-modal__grid > div:first-child > span'
        )].filter(el => {
          const s = getComputedStyle(el);
          return el.getClientRects().length > 0 &&
                 s.display !== 'none' && s.visibility !== 'hidden';
        });
        return matches.length === 1 &&
               typeof matches[0].innerText === 'string' &&
               matches[0].innerText.trim().length > 0;
        """
    )


def company_names_match(driver):
    return driver.execute_script(
        """
        const visible = selector => [...document.querySelectorAll(selector)].filter(el => {
          const s = getComputedStyle(el);
          return el.getClientRects().length > 0 &&
                 s.display !== 'none' && s.visibility !== 'hidden';
        });
        const detail = visible(
          '.business-card-detail-modal__body > section.business-card-detail-modal__section:first-child > .business-card-detail-modal__grid > div:first-child > span'
        );
        const row = visible(
          '.business-card-page .business-card-table tbody tr:first-child > td:nth-child(3)'
        );
        if (detail.length !== 1 || row.length !== 1 || detail[0] === row[0]) return false;
        const detailText = detail[0].innerText;
        const rowText = row[0].innerText;
        return typeof detailText === 'string' && typeof rowText === 'string' &&
               detailText.trim().length > 0 && rowText.trim().length > 0 &&
               detailText.trim() === rowText.trim();
        """
    )


options = webdriver.ChromeOptions()
if os.environ.get("KTL_M04_HEADLESS") != "0":
    options.add_argument("--headless=new")
options.add_argument("--window-size=1440,1100")

driver = webdriver.Chrome(options=options)
try:
    driver.set_window_size(1440, 1100)
    wait = WebDriverWait(driver, 20)

    username = os.environ.get("KTL_M04_RBEM_USERNAME")
    password = os.environ.get("KTL_M04_RBEM_PASSWORD")
    assert username and password, "Login credentials are configured"

    driver.get(LOGIN_URL)
    username_field = wait.until(
        EC.visibility_of_element_located((By.CSS_SELECTOR, USERNAME_SELECTOR))
    )
    scroll_and_wait_for_hit(driver, wait, username_field)
    username_field.clear()
    username_field.send_keys(username)

    password_field = wait.until(
        EC.visibility_of_element_located((By.CSS_SELECTOR, PASSWORD_SELECTOR))
    )
    scroll_and_wait_for_hit(driver, wait, password_field)
    password_field.clear()
    password_field.send_keys(password)

    submit_button = wait.until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, SUBMIT_SELECTOR))
    )
    scroll_and_wait_for_hit(driver, wait, submit_button)
    submit_button.click()

    with business_step(1):
        driver.get(CARDS_URL)
        path_loaded = wait.until(
            lambda d: urlparse(d.current_url).path == "/mypage/cards"
        )
        assert path_loaded, "Business-card list URL is loaded"
        table_loaded = wait.until(
            EC.visibility_of_element_located(
                (By.CSS_SELECTOR, ".business-card-page .business-card-table")
            )
        )
        assert table_loaded.is_displayed(), "Business-card list is visible"
        add_button_loaded = wait.until(
            EC.visibility_of_element_located(
                (By.CSS_SELECTOR, ".business-card-table__title button")
            )
        )
        assert add_button_loaded.is_displayed(), "Business-card title button is visible"

    with business_step(2):
        row_company = wait.until(
            EC.presence_of_element_located(
                (
                    By.CSS_SELECTOR,
                    "section.mypage-content > div.work-report-page.business-card-page > table.business-card-table > tbody > tr:nth-of-type(1) > td.business-card-table__title:nth-of-type(2)",
                )
            )
        )
        scroll_and_wait_for_hit(driver, wait, row_company)
        row_company.click()

        modal_visible = wait.until(
            EC.visibility_of_element_located(
                (By.CSS_SELECTOR, ".business-card-detail-modal")
            )
        )
        assert modal_visible.is_displayed(), "Business-card detail modal is visible"

        names_match = wait.until(company_names_match)
        assert names_match, "Selected company matches the company in the detail"

        detail_name_nonempty = wait.until(visible_text_is_nonempty)
        assert detail_name_nonempty, "Detail company name is nonempty"

    with business_step(3):
        detail_visible = wait.until(
            EC.visibility_of_element_located(
                (By.CSS_SELECTOR, ".business-card-detail-modal")
            )
        )
        assert detail_visible.is_displayed(), "Business-card detail screen is displayed"

    with business_step(4):
        close_button = wait.until(
            EC.presence_of_element_located(
                (
                    By.CSS_SELECTOR,
                    "div.mypage-layout > section.mypage-content > div.work-report-detail-modal:nth-of-type(2) > div.work-report-detail-modal__panel.business-card-detail-modal > div.work-report-detail-modal__head:nth-of-type(1) > button.work-report-detail-modal__close",
                )
            )
        )
        scroll_and_wait_for_hit(driver, wait, close_button)
        close_button.click()

        modal_closed = wait.until(
            EC.invisibility_of_element_located(
                (By.CSS_SELECTOR, ".business-card-detail-modal")
            )
        )
        assert modal_closed, "Business-card detail screen is closed"
        list_visible = wait.until(
            EC.visibility_of_element_located(
                (By.CSS_SELECTOR, ".business-card-page .business-card-table")
            )
        )
        assert list_visible.is_displayed(), "Original business-card list is visible"

    with business_step(5):
        modal_closed = wait.until(
            EC.invisibility_of_element_located(
                (By.CSS_SELECTOR, ".business-card-detail-modal")
            )
        )
        assert modal_closed, "Business-card detail screen remains closed"
finally:
    driver.quit()