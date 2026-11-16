import os
from urllib.parse import urlparse

from ktl_runtime import business_step
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait


SCENARIO_ID = "CANON-SCN-20e027bcdd1838249676cc26"
TIMEOUT = 30


def visible_state(driver, selector, expected):
    script = """
        const nodes = Array.from(document.querySelectorAll(arguments[0]));
        const visible = nodes.some(el => {
            const style = window.getComputedStyle(el);
            return el.getClientRects().length > 0 &&
                   style.display !== "none" &&
                   style.visibility !== "hidden";
        });
        return visible === arguments[1];
    """
    return driver.execute_script(script, selector, expected)


def scroll_native_target(driver, selector):
    element = driver.find_element(By.CSS_SELECTOR, selector)
    driver.execute_script(
        'arguments[0].scrollIntoView({block:"center",inline:"center",behavior:"instant"});',
        element,
    )

    def center_is_hit(d):
        target = d.find_element(By.CSS_SELECTOR, selector)
        return d.execute_script(
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
            target,
        )

    WebDriverWait(driver, TIMEOUT).until(center_is_hit)
    return driver.find_element(By.CSS_SELECTOR, selector)


def nonempty_inner_text(driver, selector):
    return driver.execute_script(
        """
        const nodes = Array.from(document.querySelectorAll(arguments[0]));
        const visible = nodes.filter(el => {
            const style = window.getComputedStyle(el);
            return el.getClientRects().length > 0 &&
                   style.display !== "none" &&
                   style.visibility !== "hidden";
        });
        if (visible.length !== 1) return false;
        const text = (visible[0].innerText || "").trim();
        return text.length > 0;
        """,
        selector,
    )


def matching_inner_text(driver, selector, other_selector):
    return driver.execute_script(
        """
        const visibleElements = selector => Array.from(document.querySelectorAll(selector)).filter(el => {
            const style = window.getComputedStyle(el);
            return el.getClientRects().length > 0 &&
                   style.display !== "none" &&
                   style.visibility !== "hidden";
        });
        const first = visibleElements(arguments[0]);
        const second = visibleElements(arguments[1]);
        if (first.length !== 1 || second.length !== 1 || first[0] === second[0]) {
            return false;
        }
        const left = (first[0].innerText || "").trim();
        const right = (second[0].innerText || "").trim();
        return left.length > 0 && right.length > 0 && left === right;
        """,
        selector,
        other_selector,
    )


driver = None
try:
    options = webdriver.ChromeOptions()
    if os.environ.get("KTL_M04_HEADLESS") != "0":
        options.add_argument("--headless=new")

    driver = webdriver.Chrome(options=options)
    driver.set_window_size(1440, 1100)
    wait = WebDriverWait(driver, TIMEOUT)

    # 로그인 정보는 지정된 환경 변수에서만 읽는다.
    username = os.environ.get("KTL_M04_RBEM_USERNAME", "")
    password = os.environ.get("KTL_M04_RBEM_PASSWORD", "")
    assert username.strip(), "로그인 사용자 환경 변수가 비어 있습니다."
    assert password.strip(), "로그인 비밀번호 환경 변수가 비어 있습니다."

    driver.get("https://rainbowlab.ai.kr/rbem")
    username_selector = "#loginId"
    password_selector = "#password"
    submit_selector = 'form.login-card button.login-submit[type="submit"]'

    login_visible = wait.until(
        lambda d: visible_state(d, username_selector, True)
        and visible_state(d, password_selector, True)
    )
    assert login_visible, "로그인 입력 화면이 표시되지 않았습니다."

    username_input = scroll_native_target(driver, username_selector)
    username_input.click()
    username_input.clear()
    username_input.send_keys(username)

    password_input = scroll_native_target(driver, password_selector)
    password_input.click()
    password_input.clear()
    password_input.send_keys(password)

    submit_button = scroll_native_target(driver, submit_selector)
    submit_button.click()
    login_closed = wait.until(
        lambda d: not visible_state(d, username_selector, True)
    )
    assert login_closed, "로그인 화면이 닫히지 않았습니다."

    with business_step(1):
        driver.get("https://rainbowlab.ai.kr/mypage/work/monthly")

        monthly_path = wait.until(
            lambda d: urlparse(d.current_url).path
            if urlparse(d.current_url).path == "/mypage/work/monthly"
            else False
        )
        assert monthly_path == "/mypage/work/monthly", "월간 업무 화면으로 이동하지 못했습니다."

        table_visible = wait.until(
            lambda d: visible_state(
                d, ".work-report-page .work-report-table", True
            )
        )
        assert table_visible, "업무 목록이 표시되지 않았습니다."

        title_button_visible = wait.until(
            lambda d: visible_state(d, ".work-report-table__title button", True)
        )
        assert title_button_visible, "업무 제목 버튼이 표시되지 않았습니다."

    with business_step(2):
        row_title_selector = (
            "section.mypage-content > div.work-report-page > "
            "table.work-report-table > tbody > tr:nth-of-type(1) > "
            "td.work-report-table__title:nth-of-type(1)"
        )
        row_title = scroll_native_target(driver, row_title_selector)
        row_title.click()

        modal_visible = wait.until(
            lambda d: visible_state(d, ".work-report-detail-modal__panel", True)
        )
        assert modal_visible, "업무 상세 화면이 표시되지 않았습니다."

        title_matches = wait.until(
            lambda d: matching_inner_text(
                d,
                ".work-report-detail-modal__meta > dd:nth-of-type(5)",
                "section.mypage-content > div.work-report-page > "
                "table.work-report-table > tbody > tr:nth-of-type(1) > "
                "td.work-report-table__title:nth-of-type(1) > button",
            )
        )
        assert title_matches, "상세 제목이 선택한 목록 제목과 일치하지 않습니다."

        content_nonempty = wait.until(
            lambda d: nonempty_inner_text(
                d, ".work-report-detail-modal__meta + .work-report-detail-modal__content"
            )
        )
        assert content_nonempty, "업무 상세 내용이 비어 있습니다."

    with business_step(3):
        detail_visible = wait.until(
            lambda d: visible_state(d, ".work-report-detail-modal__panel", True)
        )
        assert detail_visible, "업무 상세 화면이 표시되지 않았습니다."

    with business_step(4):
        close_selector = (
            "div.mypage-layout > section.mypage-content > "
            "div.work-report-detail-modal:nth-of-type(2) > "
            "div.work-report-detail-modal__panel > "
            "div.work-report-detail-modal__head:nth-of-type(1) > "
            "button.work-report-detail-modal__close"
        )
        close_button = scroll_native_target(driver, close_selector)
        close_button.click()

        modal_hidden = wait.until(
            lambda d: visible_state(d, ".work-report-detail-modal__panel", False)
        )
        assert modal_hidden, "업무 상세 화면이 닫히지 않았습니다."

        table_visible_after_close = wait.until(
            lambda d: visible_state(
                d, ".work-report-page .work-report-table", True
            )
        )
        assert table_visible_after_close, "업무 목록이 다시 표시되지 않았습니다."

    with business_step(5):
        detail_remains_hidden = wait.until(
            lambda d: visible_state(d, ".work-report-detail-modal__panel", False)
        )
        assert detail_remains_hidden, "업무 상세 화면이 여전히 표시됩니다."

finally:
    if driver is not None:
        driver.quit()