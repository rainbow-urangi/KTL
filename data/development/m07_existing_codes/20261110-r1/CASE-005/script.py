import os
from urllib.parse import urlparse

from ktl_runtime import business_step
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


SCENARIO_ID = "CANON-SCN-6abf300bb9140162836dca0d"

options = webdriver.ChromeOptions()
if os.environ.get("KTL_M04_HEADLESS") != "0":
    options.add_argument("--headless=new")

driver = webdriver.Chrome(options=options)
driver.set_window_size(1440, 1100)

wait = WebDriverWait(driver, 30)


def scroll_and_wait_for_center(locator):
    element = wait.until(EC.visibility_of_element_located(locator))
    driver.execute_script(
        "arguments[0].scrollIntoView({block:'center',inline:'center',behavior:'instant'});",
        element,
    )
    wait.until(
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
        is True
    )
    return element


def visible_state(selector):
    return driver.execute_script(
        """
        const selector = arguments[0];
        const visible = el => {
            const s = getComputedStyle(el);
            return el.getClientRects().length > 0 &&
                   s.display !== 'none' &&
                   s.visibility !== 'hidden' &&
                   s.visibility !== 'collapse' &&
                   s.opacity !== '0';
        };
        return Array.from(document.querySelectorAll(selector)).some(visible);
        """,
        selector,
    )


def wait_for_visible_state(selector, expected):
    return wait.until(lambda d: visible_state(selector) is expected)


def wait_for_nonempty(selector, property_name):
    return wait.until(
        lambda d: d.execute_script(
            """
            const selector = arguments[0];
            const property = arguments[1];
            const visible = el => {
                const s = getComputedStyle(el);
                return el.getClientRects().length > 0 &&
                       s.display !== 'none' &&
                       s.visibility !== 'hidden' &&
                       s.visibility !== 'collapse' &&
                       s.opacity !== '0';
            };
            const matches = Array.from(document.querySelectorAll(selector)).filter(visible);
            if (matches.length !== 1) return false;
            const value = matches[0][property];
            return typeof value === 'string' && value.trim().length > 0;
            """,
            selector,
            property_name,
        )
        is True
    )


def wait_for_matching_text(target, target_property, other_target, other_property):
    return wait.until(
        lambda d: d.execute_script(
            """
            const target = arguments[0];
            const targetProperty = arguments[1];
            const otherTarget = arguments[2];
            const otherProperty = arguments[3];
            const visible = el => {
                const s = getComputedStyle(el);
                return el.getClientRects().length > 0 &&
                       s.display !== 'none' &&
                       s.visibility !== 'hidden' &&
                       s.visibility !== 'collapse' &&
                       s.opacity !== '0';
            };
            const first = Array.from(document.querySelectorAll(target)).filter(visible);
            const second = Array.from(document.querySelectorAll(otherTarget)).filter(visible);
            if (first.length !== 1 || second.length !== 1 || first[0] === second[0]) return false;
            const firstValue = first[0][targetProperty];
            const secondValue = second[0][otherProperty];
            return typeof firstValue === 'string' &&
                   typeof secondValue === 'string' &&
                   firstValue.trim().length > 0 &&
                   secondValue.trim().length > 0 &&
                   firstValue.trim() === secondValue.trim();
            """,
            target,
            target_property,
            other_target,
            other_property,
        )
        is True
    )


try:
    # 로그인 준비
    driver.get("https://rainbowlab.ai.kr/rbem")
    username_locator = (By.CSS_SELECTOR, "#loginId")
    password_locator = (By.CSS_SELECTOR, "#password")
    submit_locator = (
        By.CSS_SELECTOR,
        'form.login-card button.login-submit[type="submit"]',
    )

    username_elements = driver.find_elements(*username_locator)
    if username_elements and username_elements[0].is_displayed():
        username = os.environ.get("KTL_M04_RBEM_USERNAME", "")
        password = os.environ.get("KTL_M04_RBEM_PASSWORD", "")
        assert username.strip(), "로그인 사용자 환경 변수가 필요합니다."
        assert password.strip(), "로그인 비밀번호 환경 변수가 필요합니다."

        username_input = scroll_and_wait_for_center(username_locator)
        username_input.click()
        username_input.clear()
        username_input.send_keys(username)

        password_input = scroll_and_wait_for_center(password_locator)
        password_input.click()
        password_input.clear()
        password_input.send_keys(password)

        submit_button = scroll_and_wait_for_center(submit_locator)
        submit_button.click()
        wait.until(
            lambda d: urlparse(d.current_url).path != "/rbem"
            or not any(
                element.is_displayed()
                for element in d.find_elements(*username_locator)
            )
        )

    with business_step(1):
        driver.get("https://rainbowlab.ai.kr/mypage/work/weekly")
        actual_path = wait.until(
            lambda d: urlparse(d.current_url).path
            if urlparse(d.current_url).path == "/mypage/work/weekly"
            else False
        )
        assert actual_path == "/mypage/work/weekly", "주간 업무 조회 경로가 올바르지 않습니다."
        table_visible = wait_for_visible_state(
            ".work-report-page .work-report-table", True
        )
        assert table_visible is True, "주간 업무 목록이 표시되지 않습니다."
        title_button_visible = wait_for_visible_state(
            ".work-report-table__title button", True
        )
        assert title_button_visible is True, "업무 제목 버튼이 표시되지 않습니다."

    with business_step(2):
        detail_row_title = (
            By.CSS_SELECTOR,
            "section.mypage-content > div.work-report-page > table.work-report-table > tbody > tr:nth-of-type(1) > td.work-report-table__title:nth-of-type(1)",
        )
        title_cell = scroll_and_wait_for_center(detail_row_title)
        title_cell.click()

        panel_visible = wait_for_visible_state(
            ".work-report-detail-modal__panel", True
        )
        assert panel_visible is True, "업무 상세 화면이 표시되지 않습니다."

        titles_match = wait_for_matching_text(
            ".work-report-detail-modal__meta > dd:nth-of-type(5)",
            "innerText",
            "section.mypage-content > div.work-report-page > table.work-report-table > tbody > tr:nth-of-type(1) > td.work-report-table__title:nth-of-type(1) > button",
            "innerText",
        )
        assert titles_match is True, "목록 제목과 상세 제목이 일치하지 않습니다."

        content_nonempty = wait_for_nonempty(
            ".work-report-detail-modal__meta + .work-report-detail-modal__content",
            "innerText",
        )
        assert content_nonempty is True, "업무 상세 내용이 비어 있습니다."

    with business_step(3):
        detail_visible = wait_for_visible_state(
            ".work-report-detail-modal__panel", True
        )
        assert detail_visible is True, "업무 상세 화면이 표시되지 않습니다."

    with business_step(4):
        close_locator = (
            By.CSS_SELECTOR,
            "div.mypage-layout > section.mypage-content > div.work-report-detail-modal:nth-of-type(2) > div.work-report-detail-modal__panel > div.work-report-detail-modal__head:nth-of-type(1) > button.work-report-detail-modal__close",
        )
        close_button = scroll_and_wait_for_center(close_locator)
        close_button.click()

        panel_hidden = wait_for_visible_state(
            ".work-report-detail-modal__panel", False
        )
        assert panel_hidden is False, "업무 상세 화면이 닫히지 않았습니다."

        table_visible_after_close = wait_for_visible_state(
            ".work-report-page .work-report-table", True
        )
        assert table_visible_after_close is True, "업무 목록이 표시되지 않습니다."

    with business_step(5):
        panel_hidden_after_close = wait_for_visible_state(
            ".work-report-detail-modal__panel", False
        )
        assert panel_hidden_after_close is False, "업무 상세 화면이 여전히 표시됩니다."

finally:
    driver.quit()