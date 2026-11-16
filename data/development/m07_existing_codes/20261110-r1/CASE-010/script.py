import os
from urllib.parse import urlsplit

from ktl_runtime import business_step
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

SCENARIO_ID = "CANON-SCN-29dc1c16e5cc2b8822c071d3"

BASE_URL = "https://rainbowlab.ai.kr/mypage/cards"
LOGIN_URL = "https://rainbowlab.ai.kr/rbem"


def visible_state(driver, selector):
    return driver.execute_script(
        """
        const nodes = document.querySelectorAll(arguments[0]);
        return Array.from(nodes).some((el) => {
            const style = getComputedStyle(el);
            const rect = el.getBoundingClientRect();
            return style.display !== "none" &&
                   style.visibility !== "hidden" &&
                   Number(style.opacity) !== 0 &&
                   rect.width > 0 && rect.height > 0;
        });
        """,
        selector,
    )


def wait_visible(driver, selector, expected, wait):
    return wait.until(lambda d: visible_state(d, selector) is expected)


def wait_text_contains(driver, selector, text, wait):
    return wait.until(
        lambda d: d.execute_script(
            """
            const el = document.querySelector(arguments[0]);
            return !!el && (el.innerText || el.textContent || "").includes(arguments[1]);
            """,
            selector,
            text,
        )
    )


def scroll_target_to_center(driver, element, wait):
    driver.execute_script(
        'arguments[0].scrollIntoView({block:"center",inline:"center",behavior:"instant"});',
        element,
    )
    wait.until(
        lambda d: d.execute_script(
            """
            const el = arguments[0];
            const rect = el.getBoundingClientRect();
            const x = rect.left + rect.width / 2;
            const y = rect.top + rect.height / 2;
            if (x < 0 || y < 0 || x >= window.innerWidth || y >= window.innerHeight) {
                return false;
            }
            const hit = document.elementFromPoint(x, y);
            return !!hit && (hit === el || el.contains(hit));
            """,
            element,
        )
    )


def fill_native_input(driver, selector, value, wait):
    element = driver.find_element(By.CSS_SELECTOR, selector)
    wait.until(lambda d: element.is_displayed() and element.is_enabled())
    scroll_target_to_center(driver, element, wait)
    element.click()
    element.clear()
    element.send_keys(value)
    wait.until(
        lambda d: d.execute_script(
            "return arguments[0].value === arguments[1];", element, value
        )
    )
    return element


options = webdriver.ChromeOptions()
if os.environ.get("KTL_M04_HEADLESS") != "0":
    options.add_argument("--headless=new")
options.add_argument("--window-size=1440,1100")

driver = None
try:
    driver = webdriver.Chrome(options=options)
    driver.set_window_size(1440, 1100)
    wait = WebDriverWait(driver, 30)

    # 로그인 화면이면 환경 변수의 계정으로 로그인한다.
    driver.get(LOGIN_URL)
    wait.until(lambda d: d.execute_script("return document.readyState") == "complete")
    if driver.find_elements(By.CSS_SELECTOR, "#loginId"):
        username = os.environ.get("KTL_M04_RBEM_USERNAME")
        password = os.environ.get("KTL_M04_RBEM_PASSWORD")
        assert username and password, "로그인 환경 변수가 설정되어야 합니다."
        fill_native_input(driver, "#loginId", username, wait)
        fill_native_input(driver, "#password", password, wait)
        submit = driver.find_element(
            By.CSS_SELECTOR, 'form.login-card button.login-submit[type="submit"]'
        )
        scroll_target_to_center(driver, submit, wait)
        submit.click()
        wait.until(lambda d: not d.find_elements(By.CSS_SELECTOR, "#loginId"))

    with business_step(1):
        driver.get("https://rainbowlab.ai.kr/mypage/cards")
        wait.until(lambda d: d.execute_script("return document.readyState") == "complete")
        wait.until(lambda d: urlsplit(d.current_url).path == "/mypage/cards")
        assert urlsplit(driver.current_url).path == "/mypage/cards", "목록 경로가 올바르지 않습니다."
        wait_visible(
            driver, ".business-card-page .business-card-table", True, wait
        )
        assert visible_state(
            driver, ".business-card-page .business-card-table"
        ), "명함 목록이 표시되어야 합니다."
        wait_visible(driver, ".business-card-table__title button", True, wait)
        assert visible_state(
            driver, ".business-card-table__title button"
        ), "목록 제목 버튼이 표시되어야 합니다."

    with business_step(2):
        selector = (
            "div.mypage-layout > section.mypage-content > "
            "div.work-report-page.business-card-page > "
            "div.work-report-page__bottom:nth-of-type(2) > "
            "div.work-report-page__footer:nth-of-type(2) > "
            "button.work-report-page__register"
        )
        button = driver.find_element(By.CSS_SELECTOR, selector)
        scroll_target_to_center(driver, button, wait)
        button.click()
        wait_visible(driver, ".business-card-form-modal", True, wait)
        assert visible_state(
            driver, ".business-card-form-modal"
        ), "등록 화면이 표시되어야 합니다."

    with business_step(3):
        wait_visible(driver, ".business-card-form-modal", True, wait)
        assert visible_state(
            driver, ".business-card-form-modal"
        ), "등록 화면이 표시되어야 합니다."

    with business_step(4):
        selector = (
            "div.work-report-form-modal__panel.business-card-form-modal > "
            "div.business-card-form-modal__body:nth-of-type(3) > "
            "section.business-card-form-modal__section:nth-of-type(1) > "
            "div.business-card-form-modal__grid:nth-of-type(2) > "
            "label:nth-of-type(2) > input"
        )
        value = "KTL-7c91e6ab-P2-GPT-20261110-R1"
        field = fill_native_input(driver, selector, value, wait)
        assert driver.execute_script(
            "return document.activeElement === arguments[0];", field
        ), "입력란에 포커스가 있어야 합니다."
        assert driver.execute_script(
            "return arguments[0].value === arguments[1];", field, value
        ), "입력 값이 일치해야 합니다."

    with business_step(5):
        selector = (
            "div.work-report-form-modal__panel.business-card-form-modal > "
            "div.business-card-form-modal__body:nth-of-type(3) > "
            "section.business-card-form-modal__section:nth-of-type(1) > "
            "div.business-card-form-modal__grid:nth-of-type(2) > "
            "label:nth-of-type(3) > input"
        )
        value = "KTL-CU10-R1-7c91e6ab-P2-GPT-20261110-R1"
        field = fill_native_input(driver, selector, value, wait)
        assert driver.execute_script(
            "return document.activeElement === arguments[0];", field
        ), "입력란에 포커스가 있어야 합니다."
        assert driver.execute_script(
            "return arguments[0].value === arguments[1];", field, value
        ), "입력 값이 일치해야 합니다."

    with business_step(6):
        selector = (
            "div.work-report-form-modal__panel.business-card-form-modal > "
            "div.business-card-form-modal__body:nth-of-type(3) > "
            "section.business-card-form-modal__section:nth-of-type(2) > "
            "div.business-card-form-modal__grid:nth-of-type(2) > "
            "label:nth-of-type(1) > input"
        )
        value = "010-0000-0042"
        field = fill_native_input(driver, selector, value, wait)
        assert driver.execute_script(
            "return document.activeElement === arguments[0];", field
        ), "입력란에 포커스가 있어야 합니다."
        assert driver.execute_script(
            "return arguments[0].value === arguments[1];", field, value
        ), "입력 값이 일치해야 합니다."

    with business_step(7):
        selector = (
            "div.mypage-layout > section.mypage-content > "
            "div.work-report-form-modal:nth-of-type(2) > "
            "div.work-report-form-modal__panel.business-card-form-modal > "
            "div.work-report-form-modal__footer:nth-of-type(4) > "
            "button.work-report-form-modal__submit"
        )
        button = driver.find_element(By.CSS_SELECTOR, selector)
        scroll_target_to_center(driver, button, wait)
        button.click()
        wait_visible(driver, ".business-card-form-modal", False, wait)
        assert not visible_state(
            driver, ".business-card-form-modal"
        ), "저장 후 등록 화면이 닫혀야 합니다."
        wait_visible(driver, ".work-report-message-modal__panel", True, wait)
        assert visible_state(
            driver, ".work-report-message-modal__panel"
        ), "저장 결과 화면이 표시되어야 합니다."
        wait_text_contains(
            driver, ".work-report-message-modal__panel", "등록되었습니다.", wait
        )
        assert driver.execute_script(
            """
            const el = document.querySelector(arguments[0]);
            return !!el && (el.innerText || el.textContent || "").includes(arguments[1]);
            """,
            ".work-report-message-modal__panel",
            "등록되었습니다.",
        ), "저장 완료 메시지가 표시되어야 합니다."

    with business_step(8):
        wait_visible(driver, ".business-card-form-modal", False, wait)
        assert not visible_state(
            driver, ".business-card-form-modal"
        ), "등록 화면이 닫혀 있어야 합니다."

    with business_step(9):
        wait_visible(driver, ".work-report-message-modal__panel", True, wait)
        assert visible_state(
            driver, ".work-report-message-modal__panel"
        ), "저장 결과 화면이 표시되어야 합니다."

    with business_step(10):
        driver.get("https://rainbowlab.ai.kr/mypage/cards")
        wait.until(lambda d: d.execute_script("return document.readyState") == "complete")
        wait.until(lambda d: urlsplit(d.current_url).path == "/mypage/cards")
        assert urlsplit(driver.current_url).path == "/mypage/cards", "목록 경로가 올바르지 않습니다."
        wait_visible(
            driver, ".business-card-page .business-card-table", True, wait
        )
        assert visible_state(
            driver, ".business-card-page .business-card-table"
        ), "명함 목록이 표시되어야 합니다."
        wait_visible(driver, ".business-card-table__title button", True, wait)
        assert visible_state(
            driver, ".business-card-table__title button"
        ), "목록 제목 버튼이 표시되어야 합니다."
        wait_text_contains(
            driver,
            ".business-card-page .business-card-table",
            "KTL-7c91e6ab-P2-GPT-20261110-R1",
            wait,
        )
        assert driver.execute_script(
            """
            const el = document.querySelector(arguments[0]);
            return !!el && (el.innerText || el.textContent || "").includes(arguments[1]);
            """,
            ".business-card-page .business-card-table",
            "KTL-7c91e6ab-P2-GPT-20261110-R1",
        ), "새 시험 표식이 목록에 표시되어야 합니다."
finally:
    if driver is not None:
        driver.quit()