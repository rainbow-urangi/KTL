import os
from urllib.parse import urlparse

from ktl_runtime import business_step
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait


SCENARIO_ID = "CANON-SCN-2a5e4ff2afdac7ce10413f2d"

options = webdriver.ChromeOptions()
if os.environ.get("KTL_M04_HEADLESS", "1") != "0":
    options.add_argument("--headless=new")

driver = webdriver.Chrome(options=options)
driver.set_window_size(1440, 1100)


def visible_state(selector):
    return any(element.is_displayed() for element in driver.find_elements(By.CSS_SELECTOR, selector))


def wait_visible(selector, expected):
    state = WebDriverWait(driver, 30).until(
        lambda d: {"state": visible_state(selector)}
        if visible_state(selector) == expected
        else False
    )
    return state["state"]


def wait_text_contains(selector, expected):
    return WebDriverWait(driver, 30).until(
        lambda d: any(
            expected in d.execute_script(
                "return arguments[0].innerText || arguments[0].textContent || '';",
                element,
            )
            for element in d.find_elements(By.CSS_SELECTOR, selector)
            if element.is_displayed()
        )
    )


def scroll_target_to_center(element):
    driver.execute_script(
        "arguments[0].scrollIntoView({block:'center',inline:'center',behavior:'instant'});",
        element,
    )
    WebDriverWait(driver, 15).until(
        lambda d: d.execute_script(
            """
            const e = arguments[0];
            const r = e.getBoundingClientRect();
            const x = r.left + r.width / 2;
            const y = r.top + r.height / 2;
            if (x < 0 || y < 0 || x >= window.innerWidth || y >= window.innerHeight) return false;
            const hit = document.elementFromPoint(x, y);
            return !!hit && (hit === e || e.contains(hit));
            """,
            element,
        )
    )


def find_ready_target(selector):
    element = WebDriverWait(driver, 20).until(
        lambda d: next(
            (
                item
                for item in d.find_elements(By.CSS_SELECTOR, selector)
                if item.is_displayed() and item.is_enabled()
            ),
            False,
        )
    )
    scroll_target_to_center(element)
    return element


try:
    driver.get("https://rainbowlab.ai.kr/rbem")
    WebDriverWait(driver, 30).until(
        lambda d: d.execute_script("return document.readyState") == "complete"
    )

    username_selector = "#loginId"
    password_selector = "#password"
    submit_selector = 'form.login-card button.login-submit[type="submit"]'

    if driver.find_elements(By.CSS_SELECTOR, username_selector):
        username = os.environ.get("KTL_M04_RBEM_USERNAME")
        password = os.environ.get("KTL_M04_RBEM_PASSWORD")
        assert username, "Login username environment variable is required."
        assert password, "Login password environment variable is required."

        username_element = find_ready_target(username_selector)
        username_element.click()
        assert driver.execute_script("return document.activeElement === arguments[0];", username_element), "Username field did not receive focus."
        username_element.clear()
        username_element.send_keys(username)

        password_element = find_ready_target(password_selector)
        password_element.click()
        assert driver.execute_script("return document.activeElement === arguments[0];", password_element), "Password field did not receive focus."
        password_element.clear()
        password_element.send_keys(password)

        submit_element = find_ready_target(submit_selector)
        submit_element.click()
        WebDriverWait(driver, 30).until(
            lambda d: not any(
                element.is_displayed()
                for element in d.find_elements(By.CSS_SELECTOR, username_selector)
            )
        )

    with business_step(1):
        driver.get("https://rainbowlab.ai.kr/mypage/work/daily")
        url_ok = WebDriverWait(driver, 30).until(
            lambda d: urlparse(d.current_url).path == "/mypage/work/daily"
        )
        table_visible = wait_visible(".work-report-page .work-report-table", True)
        register_visible = wait_visible(".work-report-table__title button", True)
        assert url_ok, "Daily work report URL did not load."
        assert table_visible, "Daily work report list did not load."
        assert register_visible, "Daily work report register control is not visible."

    with business_step(2):
        register_selector = (
            "div.mypage-layout > section.mypage-content > "
            "div.work-report-page > div.work-report-page__bottom:nth-of-type(2) > "
            "div.work-report-page__footer:nth-of-type(2) > "
            "button.work-report-page__register"
        )
        register_button = find_ready_target(register_selector)
        register_button.click()
        modal_visible = wait_visible(".work-report-form-modal", True)
        date_matches = wait_text_contains(
            ".work-report-form-modal__date-button", "2026.11.10 (화)"
        )
        assert modal_visible, "Daily report registration screen did not open."
        assert date_matches, "Daily report date did not match the expected date."

    with business_step(3):
        form_visible = wait_visible(".work-report-form-modal", True)
        assert form_visible, "Daily report form is not visible."

    with business_step(4):
        title_selector = "#daily-report-create-title-input"
        title_value = "KTL-7C91-CU04-TITLE-P2-GPT-20261110-R1"
        title_input = find_ready_target(title_selector)
        title_input.click()
        assert driver.execute_script(
            "return document.activeElement === arguments[0];", title_input
        ), "Title input did not receive focus."
        title_input.clear()
        title_input.send_keys(title_value)
        title_value_ready = WebDriverWait(driver, 20).until(
            lambda d: title_input.get_property("value") == title_value
        )
        assert title_value_ready, "Title input value did not match the expected value."

    with business_step(5):
        content_selector = "#daily-report-create-content-input"
        content_value = "KTL-7C91-CU04 new report content-P2-GPT-20261110-R1"
        content_input = find_ready_target(content_selector)
        content_input.click()
        assert driver.execute_script(
            "return document.activeElement === arguments[0];", content_input
        ), "Content input did not receive focus."
        content_input.clear()
        content_input.send_keys(content_value)
        content_value_ready = WebDriverWait(driver, 20).until(
            lambda d: content_input.get_property("value") == content_value
        )
        assert content_value_ready, "Content input value did not match the expected value."

    with business_step(6):
        submit_selector = (
            "div.mypage-layout > section.mypage-content > "
            "div.work-report-form-modal:nth-of-type(2) > "
            "div.work-report-form-modal__panel > "
            "div.work-report-form-modal__footer:nth-of-type(4) > "
            "button.work-report-form-modal__submit"
        )
        submit_button = find_ready_target(submit_selector)
        submit_button.click()
        form_closed = wait_visible(".work-report-form-modal", False)
        message_visible = wait_visible(".work-report-message-modal__panel", True)
        saved_text = wait_text_contains(
            ".work-report-message-modal__panel", "저장되었습니다."
        )
        assert form_closed, "Daily report form did not close after saving."
        assert message_visible, "Save result screen is not visible."
        assert saved_text, "Save result message did not match the expected text."

    with business_step(7):
        message_visible = wait_visible(".work-report-message-modal__panel", True)
        assert message_visible, "Save result screen is not visible."

    with business_step(8):
        form_closed = wait_visible(".work-report-form-modal", False)
        assert form_closed, "Daily report form remains visible."

    with business_step(9):
        driver.get("https://rainbowlab.ai.kr/mypage/work/daily")
        url_ok = WebDriverWait(driver, 30).until(
            lambda d: urlparse(d.current_url).path == "/mypage/work/daily"
        )
        table_visible = wait_visible(".work-report-page .work-report-table", True)
        register_visible = wait_visible(".work-report-table__title button", True)
        title_present = wait_text_contains(
            ".work-report-page .work-report-table",
            "KTL-7C91-CU04-TITLE-P2-GPT-20261110-R1",
        )
        assert url_ok, "Daily work report URL did not load after saving."
        assert table_visible, "Daily work report list did not load after saving."
        assert register_visible, "Daily work report register control is not visible."
        assert title_present, "Saved report was not found in the refreshed list."
finally:
    driver.quit()