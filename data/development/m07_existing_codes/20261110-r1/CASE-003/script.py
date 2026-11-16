from ktl_runtime import business_step

import os
from urllib.parse import urlsplit

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

SCENARIO_ID = "CANON-SCN-63995159407da5ea13debcf6"

LOGIN_URL = "https://rainbowlab.ai.kr/rbem"
DAILY_URL = "https://rainbowlab.ai.kr/mypage/work/daily"

driver = None


def visible_state(browser, selector):
    return any(element.is_displayed() for element in browser.find_elements(By.CSS_SELECTOR, selector))


def wait_for_visibility(browser_wait, selector, expected):
    return browser_wait.until(
        lambda browser: visible_state(browser, selector) is expected
    )


def scroll_target_to_center(browser, browser_wait, selector):
    element = browser_wait.until(
        lambda current: next(
            (
                item
                for item in current.find_elements(By.CSS_SELECTOR, selector)
                if item.is_displayed()
            ),
            False,
        )
    )
    browser.execute_script(
        "arguments[0].scrollIntoView({block:'center',inline:'center',behavior:'instant'});",
        element,
    )
    browser_wait.until(
        lambda current: current.execute_script(
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
    return browser.find_element(By.CSS_SELECTOR, selector)


def focus_and_check(browser, browser_wait, selector):
    element = scroll_target_to_center(browser, browser_wait, selector)
    element.click()
    browser_wait.until(
        lambda current: current.execute_script(
            "return document.activeElement === document.querySelector(arguments[0]);",
            selector,
        )
    )
    focused = browser.execute_script(
        "return document.activeElement === document.querySelector(arguments[0]);",
        selector,
    )
    assert focused, "Login input did not receive focus."
    return element


def wait_for_nonempty(browser_wait, selector, property_name):
    return browser_wait.until(
        lambda browser: browser.execute_script(
            """
            const selector = arguments[0], property = arguments[1];
            const all = [...document.querySelectorAll(selector)];
            const visible = all.filter(el => {
              const s = getComputedStyle(el), r = el.getBoundingClientRect();
              return s.display !== 'none' && s.visibility !== 'hidden' &&
                     r.width > 0 && r.height > 0;
            });
            if (visible.length !== 1) return false;
            const el = visible[0];
            const value = property === 'text' ? el.innerText : el[property];
            return value != null && String(value).trim().length > 0;
            """,
            selector,
            property_name,
        )
    )


def wait_for_equal_text(browser_wait, selector, property_name, other_selector, other_property):
    return browser_wait.until(
        lambda browser: browser.execute_script(
            """
            const selectors = [arguments[0], arguments[2]];
            const properties = [arguments[1], arguments[3]];
            const elements = selectors.map(selector => {
              const all = [...document.querySelectorAll(selector)];
              const visible = all.filter(el => {
                const s = getComputedStyle(el), r = el.getBoundingClientRect();
                return s.display !== 'none' && s.visibility !== 'hidden' &&
                       r.width > 0 && r.height > 0;
              });
              return visible.length === 1 ? visible[0] : null;
            });
            if (!elements[0] || !elements[1] || elements[0] === elements[1]) return false;
            const values = elements.map((el, i) => {
              const value = properties[i] === 'text' ? el.innerText : el[properties[i]];
              return value == null ? '' : String(value).trim();
            });
            return values[0].length > 0 && values[1].length > 0 &&
                   values[0] === values[1];
            """,
            selector,
            property_name,
            other_selector,
            other_property,
        )
    )


try:
    username = os.environ.get("KTL_M04_RBEM_USERNAME")
    password = os.environ.get("KTL_M04_RBEM_PASSWORD")
    assert username, "Required login username environment variable is missing."
    assert password, "Required login password environment variable is missing."

    options = webdriver.ChromeOptions()
    if os.environ.get("KTL_M04_HEADLESS") != "0":
        options.add_argument("--headless=new")
    options.add_argument("--window-size=1440,1100")

    driver = webdriver.Chrome(options=options)
    driver.set_window_size(1440, 1100)
    wait = WebDriverWait(driver, 30)

    # 로그인
    driver.get(LOGIN_URL)
    username_selector = "#loginId"
    password_selector = "#password"
    submit_selector = 'form.login-card button.login-submit[type="submit"]'

    wait.until(lambda browser: browser.find_elements(By.CSS_SELECTOR, username_selector))
    username_input = focus_and_check(driver, wait, username_selector)
    username_input.clear()
    username_input.send_keys(username)
    wait.until(
        lambda browser: browser.execute_script(
            "return document.querySelector(arguments[0]).value === arguments[1];",
            username_selector,
            username,
        )
    )
    username_matches = driver.execute_script(
        "return document.querySelector(arguments[0]).value === arguments[1];",
        username_selector,
        username,
    )
    assert username_matches, "Login username was not entered."

    password_input = focus_and_check(driver, wait, password_selector)
    password_input.clear()
    password_input.send_keys(password)
    wait.until(
        lambda browser: browser.execute_script(
            "return document.querySelector(arguments[0]).value === arguments[1];",
            password_selector,
            password,
        )
    )
    password_matches = driver.execute_script(
        "return document.querySelector(arguments[0]).value === arguments[1];",
        password_selector,
        password,
    )
    assert password_matches, "Login password was not entered."

    submit_button = scroll_target_to_center(driver, wait, submit_selector)
    submit_button.click()
    wait.until(
        lambda browser: (
            urlsplit(browser.current_url).path != "/rbem"
            or not visible_state(browser, submit_selector)
        )
    )
    login_completed = (
        urlsplit(driver.current_url).path != "/rbem"
        or not visible_state(driver, submit_selector)
    )
    assert login_completed, "Login did not complete."

    with business_step(1):
        driver.get(DAILY_URL)
        wait.until(lambda browser: urlsplit(browser.current_url).path == "/mypage/work/daily")
        correct_path = urlsplit(driver.current_url).path == "/mypage/work/daily"
        assert correct_path, "Daily work report page did not open."

        wait_for_visibility(wait, ".work-report-page .work-report-table", True)
        table_visible = visible_state(driver, ".work-report-page .work-report-table")
        assert table_visible, "Daily work report list is not visible."

        wait_for_visibility(wait, ".work-report-table__title button", True)
        title_button_visible = visible_state(driver, ".work-report-table__title button")
        assert title_button_visible, "Daily work report titles are not visible."

    with business_step(2):
        detail_title_cell = (
            "section.mypage-content > div.work-report-page > "
            "table.work-report-table > tbody > tr:nth-of-type(1) > "
            "td.work-report-table__title:nth-of-type(1)"
        )
        title_cell = scroll_target_to_center(driver, wait, detail_title_cell)
        title_cell.click()

        wait_for_visibility(wait, ".work-report-detail-modal__panel", True)
        detail_visible = visible_state(driver, ".work-report-detail-modal__panel")
        assert detail_visible, "Work report detail did not open."

        title_matches = wait_for_equal_text(
            wait,
            ".work-report-detail-modal__meta > dd:nth-of-type(5)",
            "text",
            detail_title_cell + " > button",
            "text",
        )
        assert title_matches, "Work report detail title does not match the selected title."

        content_nonempty = wait_for_nonempty(
            wait,
            ".work-report-detail-modal__meta + .work-report-detail-modal__content",
            "text",
        )
        assert content_nonempty, "Work report detail content is empty."

    with business_step(3):
        wait_for_visibility(wait, ".work-report-detail-modal__panel", True)
        detail_screen_visible = visible_state(driver, ".work-report-detail-modal__panel")
        assert detail_screen_visible, "Work report detail screen is not displayed."

    with business_step(4):
        close_selector = (
            "div.mypage-layout > section.mypage-content > "
            "div.work-report-detail-modal:nth-of-type(2) > "
            "div.work-report-detail-modal__panel > "
            "div.work-report-detail-modal__head:nth-of-type(1) > "
            "button.work-report-detail-modal__close"
        )
        close_button = scroll_target_to_center(driver, wait, close_selector)
        close_button.click()

        wait_for_visibility(wait, ".work-report-detail-modal__panel", False)
        detail_closed = not visible_state(driver, ".work-report-detail-modal__panel")
        assert detail_closed, "Work report detail screen did not close."

        wait_for_visibility(wait, ".work-report-page .work-report-table", True)
        list_restored = visible_state(driver, ".work-report-page .work-report-table")
        assert list_restored, "Work report list was not restored."

    with business_step(5):
        wait_for_visibility(wait, ".work-report-detail-modal__panel", False)
        detail_remains_closed = not visible_state(driver, ".work-report-detail-modal__panel")
        assert detail_remains_closed, "Work report detail screen is still open."

finally:
    if driver is not None:
        driver.quit()