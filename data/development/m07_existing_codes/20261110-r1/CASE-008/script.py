import os
from urllib.parse import urlparse

from ktl_runtime import business_step
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException

SCENARIO_ID = "CANON-SCN-fa1497e3f859b1ebc8ebf81a"

MONTHLY_URL = "https://rainbowlab.ai.kr/mypage/work/monthly"
TITLE_VALUE = "KTL-7C91-CU08-TITLE-P2-GPT-20261110-R1"
CONTENT_VALUE = "KTL-7C91-CU08 new report content-P2-GPT-20261110-R1"

def visible_state(driver, selector):
    return bool(driver.execute_script(
        """
        const el = document.querySelector(arguments[0]);
        if (!el) return false;
        const style = getComputedStyle(el);
        return style.display !== 'none' &&
               style.visibility !== 'hidden' &&
               style.visibility !== 'collapse' &&
               el.getClientRects().length > 0;
        """,
        selector,
    ))

def wait_visible_state(driver, selector, expected, timeout=20):
    WebDriverWait(driver, timeout).until(
        lambda d: visible_state(d, selector) == expected
    )
    actual = visible_state(driver, selector)
    assert actual == expected, "Unexpected element visibility"

def wait_text_contains(driver, selector, expected_text, timeout=20):
    WebDriverWait(driver, timeout).until(
        lambda d: d.execute_script(
            """
            const el = document.querySelector(arguments[0]);
            return !!el && (el.innerText || el.textContent || '').includes(arguments[1]);
            """,
            selector,
            expected_text,
        )
    )
    actual = driver.execute_script(
        """
        const el = document.querySelector(arguments[0]);
        return !!el && (el.innerText || el.textContent || '').includes(arguments[1]);
        """,
        selector,
        expected_text,
    )
    assert actual, "Expected text was not present"

def wait_path(driver, expected_path, timeout=20):
    WebDriverWait(driver, timeout).until(
        lambda d: urlparse(d.current_url).path == expected_path
    )
    actual = urlparse(driver.current_url).path
    assert actual == expected_path, "Unexpected page path"

def scroll_and_wait_hit(driver, selector, timeout=20):
    element = WebDriverWait(driver, timeout).until(
        lambda d: next(
            (el for el in d.find_elements(By.CSS_SELECTOR, selector) if el.is_displayed()),
            False,
        )
    )
    driver.execute_script(
        "arguments[0].scrollIntoView({block:'center',inline:'center',behavior:'instant'});",
        element,
    )
    WebDriverWait(driver, timeout).until(
        lambda d: d.execute_script(
            """
            const el = document.querySelector(arguments[0]);
            if (!el) return false;
            const r = el.getBoundingClientRect();
            const x = r.left + r.width / 2;
            const y = r.top + r.height / 2;
            if (x < 0 || y < 0 || x >= innerWidth || y >= innerHeight) return false;
            const hit = document.elementFromPoint(x, y);
            return !!hit && (hit === el || el.contains(hit));
            """,
            selector,
        )
    )
    return driver.find_element(By.CSS_SELECTOR, selector)

def wait_focus(driver, element, timeout=10):
    WebDriverWait(driver, timeout).until(
        lambda d: d.execute_script(
            "return document.activeElement === arguments[0] || arguments[0].contains(document.activeElement);",
            element,
        )
    )
    actual = driver.execute_script(
        "return document.activeElement === arguments[0] || arguments[0].contains(document.activeElement);",
        element,
    )
    assert actual, "Target did not receive focus"

def wait_input_value(driver, selector, expected_value, timeout=20):
    WebDriverWait(driver, timeout).until(
        lambda d: d.execute_script(
            "const el=document.querySelector(arguments[0]); return !!el && el.value === arguments[1];",
            selector,
            expected_value,
        )
    )
    actual = driver.execute_script(
        "const el=document.querySelector(arguments[0]); return !!el && el.value === arguments[1];",
        selector,
        expected_value,
    )
    assert actual, "Input value did not match"

options = webdriver.ChromeOptions()
if os.environ.get("KTL_M04_HEADLESS", "1") != "0":
    options.add_argument("--headless=new")
options.add_argument("--window-size=1440,1100")

driver = None
try:
    driver = webdriver.Chrome(options=options)
    driver.set_window_size(1440, 1100)
    wait = WebDriverWait(driver, 20)

    driver.get("https://rainbowlab.ai.kr/rbem")
    try:
        wait.until(
            lambda d: any(
                el.is_displayed()
                for el in d.find_elements(By.CSS_SELECTOR, "#loginId")
            )
        )
        username = os.environ.get("KTL_M04_RBEM_USERNAME")
        password = os.environ.get("KTL_M04_RBEM_PASSWORD")
        assert username and password, "Login environment variables are required"

        login_id = scroll_and_wait_hit(driver, "#loginId")
        login_id.click()
        login_id.clear()
        login_id.send_keys(username)

        password_input = scroll_and_wait_hit(driver, "#password")
        password_input.click()
        password_input.clear()
        password_input.send_keys(password)

        submit = scroll_and_wait_hit(
            driver, 'form.login-card button.login-submit[type="submit"]'
        )
        submit.click()
    except TimeoutException:
        pass

    driver.get(MONTHLY_URL)

    with business_step(1):
        wait_path(driver, "/mypage/work/monthly")
        wait_visible_state(driver, ".work-report-page .work-report-table", True)
        wait_visible_state(driver, ".work-report-table__title button", True)
        assert urlparse(driver.current_url).path == "/mypage/work/monthly", "Monthly work page did not load"
        assert visible_state(driver, ".work-report-page .work-report-table"), "Work report list did not load"
        assert visible_state(driver, ".work-report-table__title button"), "Work report title control did not load"

    with business_step(2):
        selector = "div.mypage-layout > section.mypage-content > div.work-report-page > div.work-report-page__bottom:nth-of-type(2) > div.work-report-page__footer:nth-of-type(2) > button.work-report-page__register"
        target = scroll_and_wait_hit(driver, selector)
        target.click()
        wait_visible_state(driver, ".work-report-form-modal", True)
        wait_text_contains(driver, ".work-report-form-modal__date-button", "2026.11.10 (화)")
        assert visible_state(driver, ".work-report-form-modal"), "Report registration screen did not open"
        assert driver.execute_script(
            "const el=document.querySelector('.work-report-form-modal__date-button'); return !!el && (el.innerText || el.textContent || '').includes('2026.11.10 (화)');"
        ), "Initial report date was unexpected"

    with business_step(3):
        wait_visible_state(driver, ".work-report-form-modal", True)
        assert visible_state(driver, ".work-report-form-modal"), "Report form screen is not visible"

    with business_step(4):
        selector = "section.mypage-content > div.work-report-form-modal:nth-of-type(2) > div.work-report-form-modal__panel > div.work-report-form-modal__meta:nth-of-type(2) > div.work-report-form-modal__date > button.work-report-form-modal__date-button"
        target = scroll_and_wait_hit(driver, selector)
        target.click()
        wait_visible_state(driver, ".work-report-form-modal__date-picker", True)
        assert visible_state(driver, ".work-report-form-modal__date-picker"), "Report date calendar did not open"

    with business_step(5):
        wait_visible_state(driver, ".work-report-form-modal__date-picker", True)
        assert visible_state(driver, ".work-report-form-modal__date-picker"), "Report date calendar is not visible"

    with business_step(6):
        selector = '.work-date-calendar__day[aria-label="2026-11-09"]'
        target = scroll_and_wait_hit(driver, selector)
        target.click()
        wait_visible_state(driver, ".work-report-form-modal__date-picker", False)
        wait_visible_state(driver, ".work-report-form-modal", True)
        wait_text_contains(driver, ".work-report-form-modal__date-button", "2026.11.09 (월)")
        assert not visible_state(driver, ".work-report-form-modal__date-picker"), "Date calendar did not close"
        assert visible_state(driver, ".work-report-form-modal"), "Report form closed unexpectedly"
        assert driver.execute_script(
            "const el=document.querySelector('.work-report-form-modal__date-button'); return !!el && (el.innerText || el.textContent || '').includes('2026.11.09 (월)');"
        ), "Selected report date was not applied"

    with business_step(7):
        wait_visible_state(driver, ".work-report-form-modal__date-picker", False)
        assert not visible_state(driver, ".work-report-form-modal__date-picker"), "Date calendar remained open"

    with business_step(8):
        selector = "#daily-report-create-title-input"
        target = scroll_and_wait_hit(driver, selector)
        target.click()
        target.clear()
        target.send_keys(TITLE_VALUE)
        wait_input_value(driver, selector, TITLE_VALUE)
        wait_focus(driver, target)
        assert driver.execute_script(
            "const el=document.querySelector(arguments[0]); return !!el && el.value === arguments[1];",
            selector,
            TITLE_VALUE,
        ), "Report title input did not retain the requested value"

    with business_step(9):
        selector = "#daily-report-create-content-input"
        target = scroll_and_wait_hit(driver, selector)
        target.click()
        target.clear()
        target.send_keys(CONTENT_VALUE)
        wait_input_value(driver, selector, CONTENT_VALUE)
        wait_focus(driver, target)
        assert driver.execute_script(
            "const el=document.querySelector(arguments[0]); return !!el && el.value === arguments[1];",
            selector,
            CONTENT_VALUE,
        ), "Report content input did not retain the requested value"

    with business_step(10):
        selector = "div.mypage-layout > section.mypage-content > div.work-report-form-modal:nth-of-type(2) > div.work-report-form-modal__panel > div.work-report-form-modal__footer:nth-of-type(4) > button.work-report-form-modal__submit"
        target = scroll_and_wait_hit(driver, selector)
        WebDriverWait(driver, 20).until(lambda d: target.is_enabled())
        target.click()
        wait_visible_state(driver, ".work-report-form-modal", False)
        wait_visible_state(driver, ".work-report-message-modal__panel", True)
        wait_text_contains(driver, ".work-report-message-modal__panel", "저장되었습니다.")
        assert not visible_state(driver, ".work-report-form-modal"), "Report form remained open after save"
        assert visible_state(driver, ".work-report-message-modal__panel"), "Save result was not displayed"
        assert driver.execute_script(
            "const el=document.querySelector('.work-report-message-modal__panel'); return !!el && (el.innerText || el.textContent || '').includes('저장되었습니다.');"
        ), "Save confirmation was not displayed"

    with business_step(11):
        wait_visible_state(driver, ".work-report-message-modal__panel", True)
        assert visible_state(driver, ".work-report-message-modal__panel"), "Save result screen is not visible"

    with business_step(12):
        wait_visible_state(driver, ".work-report-form-modal", False)
        assert not visible_state(driver, ".work-report-form-modal"), "Report form is still visible"

    with business_step(13):
        driver.get(MONTHLY_URL)
        wait_path(driver, "/mypage/work/monthly")
        wait_visible_state(driver, ".work-report-page .work-report-table", True)
        wait_visible_state(driver, ".work-report-table__title button", True)
        wait_text_contains(
            driver,
            ".work-report-page .work-report-table",
            TITLE_VALUE,
        )
        assert urlparse(driver.current_url).path == "/mypage/work/monthly", "Monthly work page did not reload"
        assert visible_state(driver, ".work-report-page .work-report-table"), "Work report list did not reload"
        assert visible_state(driver, ".work-report-table__title button"), "Work report title control did not reload"
        assert driver.execute_script(
            "const el=document.querySelector('.work-report-page .work-report-table'); return !!el && (el.innerText || el.textContent || '').includes(arguments[0]);",
            TITLE_VALUE,
        ), "Saved report was not present after reload"
finally:
    if driver is not None:
        driver.quit()