import os
from urllib.parse import urlparse

from ktl_runtime import business_step
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


SCENARIO_ID = "CANON-SCN-cf8da6b07b13a3147dc0d4e8"

LOGIN_URL = "https://rainbowlab.ai.kr/rbem"
SCHEDULE_URL = "https://rainbowlab.ai.kr/mypage/schedule"
LOGIN_ID_SELECTOR = "#loginId"
PASSWORD_SELECTOR = "#password"
LOGIN_SUBMIT_SELECTOR = 'form.login-card button.login-submit[type="submit"]'


def scroll_and_wait_for_center(driver, selector, timeout=20):
    locator = (By.CSS_SELECTOR, selector)
    element = WebDriverWait(driver, timeout).until(
        EC.visibility_of_element_located(locator)
    )
    driver.execute_script(
        'arguments[0].scrollIntoView({block:"center",inline:"center",behavior:"instant"});',
        element,
    )

    def center_is_hit(browser):
        return browser.execute_script(
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

    WebDriverWait(driver, timeout).until(center_is_hit)
    return driver.find_element(*locator)


def visible_text_equals_target(driver, target_selector, target_property,
                               other_selector, other_property):
    return driver.execute_script(
        """
        function visibleElements(selector) {
            return Array.from(document.querySelectorAll(selector)).filter(el => {
                const style = getComputedStyle(el);
                return el.getClientRects().length > 0 &&
                    style.display !== "none" &&
                    style.visibility !== "hidden" &&
                    style.visibility !== "collapse";
            });
        }
        function propertyString(el, property) {
            if (property === "text") return el.innerText;
            return el[property];
        }
        const targets = visibleElements(arguments[0]);
        const others = visibleElements(arguments[2]);
        if (targets.length !== 1 || others.length !== 1) return false;
        const target = targets[0];
        const other = others[0];
        if (target === other) return false;
        const targetValue = propertyString(target, arguments[1]);
        const otherValue = propertyString(other, arguments[3]);
        if (typeof targetValue !== "string" || typeof otherValue !== "string") return false;
        const trimmedTarget = targetValue.trim();
        const trimmedOther = otherValue.trim();
        return trimmedTarget.length > 0 &&
            trimmedOther.length > 0 &&
            trimmedTarget === trimmedOther;
        """,
        target_selector,
        target_property,
        other_selector,
        other_property,
    )


def visible_nonempty_property(driver, selector, property):
    return driver.execute_script(
        """
        const matches = Array.from(document.querySelectorAll(arguments[0])).filter(el => {
            const style = getComputedStyle(el);
            return el.getClientRects().length > 0 &&
                style.display !== "none" &&
                style.visibility !== "hidden" &&
                style.visibility !== "collapse";
        });
        if (matches.length !== 1) return false;
        const el = matches[0];
        const value = arguments[1] === "text" ? el.innerText : el[arguments[1]];
        return typeof value === "string" && value.trim().length > 0;
        """,
        selector,
        property,
    )


options = webdriver.ChromeOptions()
if os.getenv("KTL_M04_HEADLESS", "1") != "0":
    options.add_argument("--headless=new")
options.add_argument("--window-size=1440,1100")

driver = webdriver.Chrome(options=options)
driver.set_window_size(1440, 1100)

try:
    # 로그인 상태를 확인한다.
    driver.get(LOGIN_URL)

    def login_ready(browser):
        username_matches = browser.find_elements(By.CSS_SELECTOR, LOGIN_ID_SELECTOR)
        if any(element.is_displayed() for element in username_matches):
            return True
        return urlparse(browser.current_url).path != urlparse(LOGIN_URL).path

    WebDriverWait(driver, 30).until(login_ready)
    username_matches = driver.find_elements(By.CSS_SELECTOR, LOGIN_ID_SELECTOR)
    if any(element.is_displayed() for element in username_matches):
        username = os.getenv("KTL_M04_RBEM_USERNAME")
        password = os.getenv("KTL_M04_RBEM_PASSWORD")
        assert username, "로그인 사용자 환경 변수가 필요합니다."
        assert password, "로그인 비밀번호 환경 변수가 필요합니다."

        username_input = scroll_and_wait_for_center(driver, LOGIN_ID_SELECTOR)
        username_input.click()
        assert driver.execute_script(
            "return document.activeElement === arguments[0];", username_input
        ), "사용자 입력란에 포커스되지 않았습니다."
        username_input.clear()
        assert username_input.get_attribute("value") == "", "사용자 입력란이 비워지지 않았습니다."
        username_input.send_keys(username)
        assert username_input.get_attribute("value") == username, "사용자 입력란 값이 다릅니다."

        password_input = scroll_and_wait_for_center(driver, PASSWORD_SELECTOR)
        password_input.click()
        assert driver.execute_script(
            "return document.activeElement === arguments[0];", password_input
        ), "비밀번호 입력란에 포커스되지 않았습니다."
        password_input.clear()
        assert password_input.get_attribute("value") == "", "비밀번호 입력란이 비워지지 않았습니다."
        password_input.send_keys(password)
        assert password_input.get_attribute("value") == password, "비밀번호 입력란 값이 다릅니다."

        submit_button = scroll_and_wait_for_center(driver, LOGIN_SUBMIT_SELECTOR)
        submit_button.click()
        WebDriverWait(driver, 30).until(
            lambda browser: (
                urlparse(browser.current_url).path != urlparse(LOGIN_URL).path
                or not any(
                    element.is_displayed()
                    for element in browser.find_elements(
                        By.CSS_SELECTOR, LOGIN_ID_SELECTOR
                    )
                )
            )
        )

    with business_step(1):
        driver.get(SCHEDULE_URL)

        path_loaded = WebDriverWait(driver, 30).until(
            lambda browser: urlparse(browser.current_url).path == "/mypage/schedule"
        )
        assert path_loaded, "일정 조회 화면으로 이동하지 못했습니다."

        calendar = WebDriverWait(driver, 30).until(
            EC.visibility_of_element_located(
                (By.CSS_SELECTOR, ".schedule-page .monthly-calendar")
            )
        )
        assert calendar.is_displayed(), "월간 일정 화면이 표시되지 않았습니다."

        event_title = WebDriverWait(driver, 30).until(
            EC.visibility_of_element_located(
                (By.CSS_SELECTOR, ".schedule-event__title")
            )
        )
        assert event_title.is_displayed(), "일정 목록이 표시되지 않았습니다."

    with business_step(2):
        event_selector = (
            "div.schedule-page > section.monthly-calendar > "
            "div.monthly-calendar__grid:nth-of-type(2) > "
            "div.monthly-calendar__cell:nth-of-type(5) > "
            "ul.monthly-calendar__events > li.schedule-event"
        )
        event = scroll_and_wait_for_center(driver, event_selector)
        event.click()

        modal = WebDriverWait(driver, 30).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, ".schedule-modal"))
        )
        assert modal.is_displayed(), "일정 상세 화면이 표시되지 않았습니다."

        title_matches = WebDriverWait(driver, 30).until(
            lambda browser: visible_text_equals_target(
                browser,
                "#schedule-title",
                "value",
                event_selector + " .schedule-event__title",
                "text",
            )
        )
        assert title_matches, "일정 제목이 목록 제목과 일치하지 않습니다."

        description_nonempty = WebDriverWait(driver, 30).until(
            lambda browser: visible_nonempty_property(
                browser, "#schedule-description", "value"
            )
        )
        assert description_nonempty, "일정 상세 내용이 비어 있습니다."

    with business_step(3):
        modal_visible = WebDriverWait(driver, 30).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, ".schedule-modal"))
        )
        assert modal_visible.is_displayed(), "일정 상세 화면이 표시되지 않았습니다."

finally:
    driver.quit()