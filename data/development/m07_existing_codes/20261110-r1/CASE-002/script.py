import os
from urllib.parse import urlparse

from ktl_runtime import business_step
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

SCENARIO_ID = "CANON-SCN-2c33f8e8ccba60410e7f4993"

SCHEDULE_URL = "https://rainbowlab.ai.kr/mypage/schedule"
TITLE = "KTL-7C91-CU02-TITLE-P3-GPT-20261110-R1"
DESCRIPTION = "KTL-7C91-CU02 new schedule description-P3-GPT-20261110-R1"
TIMEOUT = 30


def visible(driver, selector):
    elements = driver.find_elements(By.CSS_SELECTOR, selector)
    return len(elements) == 1 and elements[0].is_displayed()


def wait_for_visibility(driver, selector, expected):
    return WebDriverWait(driver, TIMEOUT).until(
        lambda d: visible(d, selector) is expected
    )


def wait_for_value(driver, selector, expected):
    return WebDriverWait(driver, TIMEOUT).until(
        lambda d: len(d.find_elements(By.CSS_SELECTOR, selector)) == 1
        and d.find_element(By.CSS_SELECTOR, selector).get_property("value") == expected
    )


def wait_for_count(driver, selector, expected):
    return WebDriverWait(driver, TIMEOUT).until(
        lambda d: len(d.find_elements(By.CSS_SELECTOR, selector)) == expected
    )


def wait_for_text_equals(driver, selector, expected):
    return WebDriverWait(driver, TIMEOUT).until(
        lambda d: d.execute_script(
            """
            const elements = document.querySelectorAll(arguments[0]);
            if (elements.length !== 1) return false;
            const text = (elements[0].innerText || '').trim();
            return text.length > 0 && text === arguments[1];
            """,
            selector,
            expected,
        )
    )


def wait_for_text_contains(driver, selector, expected):
    return WebDriverWait(driver, TIMEOUT).until(
        lambda d: d.execute_script(
            """
            const elements = document.querySelectorAll(arguments[0]);
            if (elements.length !== 1) return false;
            return (elements[0].innerText || '').includes(arguments[1]);
            """,
            selector,
            expected,
        )
    )


def wait_for_path(driver, expected):
    return WebDriverWait(driver, TIMEOUT).until(
        lambda d: urlparse(d.current_url).path == expected
    )


def scroll_and_wait_for_hit(driver, element):
    driver.execute_script(
        "arguments[0].scrollIntoView({block:'center', inline:'center', behavior:'instant'});",
        element,
    )
    return WebDriverWait(driver, TIMEOUT).until(
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


def wait_for_schedule_content(driver, text):
    return WebDriverWait(driver, TIMEOUT).until(
        lambda d: d.execute_script(
            """
            const elements = document.querySelectorAll('.schedule-page .monthly-calendar');
            if (elements.length !== 1) return false;
            return (elements[0].innerText || '').includes(arguments[0]);
            """,
            text,
        )
    )


def wait_for_focus_in_modal(driver):
    return WebDriverWait(driver, TIMEOUT).until(
        lambda d: d.execute_script(
            """
            const modal = document.querySelector('.schedule-modal');
            return !!modal && modal.contains(document.activeElement);
            """
        )
    )


def wait_for_focus_on(driver, selector):
    return WebDriverWait(driver, TIMEOUT).until(
        lambda d: d.execute_script(
            """
            const elements = document.querySelectorAll(arguments[0]);
            return elements.length === 1 && document.activeElement === elements[0];
            """,
            selector,
        )
    )


options = webdriver.ChromeOptions()
if os.environ.get("KTL_M04_HEADLESS") != "0":
    options.add_argument("--headless=new")

driver = webdriver.Chrome(options=options)
driver.set_window_size(1440, 1100)
wait = WebDriverWait(driver, TIMEOUT)

try:
    # 로그인 설정
    driver.get(SCHEDULE_URL)
    wait.until(
        lambda d: d.execute_script(
            """
            return !!document.querySelector('#loginId, .schedule-page .monthly-calendar');
            """
        )
    )

    if driver.find_elements(By.CSS_SELECTOR, "#loginId"):
        username = os.environ.get("KTL_M04_RBEM_USERNAME")
        password = os.environ.get("KTL_M04_RBEM_PASSWORD")
        if not username or not password:
            raise RuntimeError("로그인 환경 변수가 설정되지 않았습니다.")

        driver.find_element(By.CSS_SELECTOR, "#loginId").send_keys(username)
        driver.find_element(By.CSS_SELECTOR, "#password").send_keys(password)
        login_button = driver.find_element(
            By.CSS_SELECTOR, 'form.login-card button.login-submit[type="submit"]'
        )
        scroll_and_wait_for_hit(driver, login_button)
        login_button.click()
        wait.until(
            lambda d: d.find_elements(
                By.CSS_SELECTOR, ".schedule-page .monthly-calendar"
            )
            or not d.find_elements(By.CSS_SELECTOR, "#loginId")
        )

    with business_step(1):
        driver.get(SCHEDULE_URL)
        path_ok = wait_for_path(driver, "/mypage/schedule")
        assert path_ok, "일정 화면 경로가 예상과 다릅니다."
        calendar_visible = wait_for_visibility(
            driver, ".schedule-page .monthly-calendar", True
        )
        assert calendar_visible, "일정 달력이 표시되지 않았습니다."

    with business_step(2):
        date_target = driver.find_element(
            By.CSS_SELECTOR,
            ".monthly-calendar__cell:nth-child(9) .monthly-calendar__date-number",
        )
        scroll_and_wait_for_hit(driver, date_target)
        date_target.click()

        modal_visible = wait_for_visibility(driver, ".schedule-modal", True)
        assert modal_visible, "신규 일정 입력 화면이 표시되지 않았습니다."

        focused_in_modal = wait_for_focus_in_modal(driver)
        assert focused_in_modal, "일정 입력 화면에 포커스가 없습니다."

        delete_count_ok = wait_for_count(
            driver, ".schedule-modal__delete-button", 0
        )
        assert delete_count_ok, "신규 일정 화면에 삭제 버튼이 있습니다."

        heading_ok = wait_for_text_equals(
            driver, ".schedule-modal__head h2", "업무 등록"
        )
        assert heading_ok, "신규 일정 화면 제목이 예상과 다릅니다."

        title_empty = wait_for_value(driver, "#schedule-title", "")
        assert title_empty, "신규 일정 제목 입력란이 비어 있지 않습니다."

        description_empty = wait_for_value(driver, "#schedule-description", "")
        assert description_empty, "신규 일정 설명 입력란이 비어 있지 않습니다."

    with business_step(3):
        modal_visible = wait_for_visibility(driver, ".schedule-modal", True)
        assert modal_visible, "일정 입력 화면이 표시되지 않았습니다."

    with business_step(4):
        title_input = driver.find_element(By.CSS_SELECTOR, "#schedule-title")
        title_input.send_keys(TITLE)

        focused = wait_for_focus_on(driver, "#schedule-title")
        assert focused, "제목 입력란에 포커스가 없습니다."

        title_matches = wait_for_value(driver, "#schedule-title", TITLE)
        assert title_matches, "제목 입력값이 예상과 다릅니다."

    with business_step(5):
        description_input = driver.find_element(
            By.CSS_SELECTOR, "#schedule-description"
        )
        description_input.send_keys(DESCRIPTION)

        focused = wait_for_focus_on(driver, "#schedule-description")
        assert focused, "설명 입력란에 포커스가 없습니다."

        description_matches = wait_for_value(
            driver, "#schedule-description", DESCRIPTION
        )
        assert description_matches, "설명 입력값이 예상과 다릅니다."

    with business_step(6):
        form = driver.find_element(
            By.CSS_SELECTOR,
            "div > main.mypage > div.mypage-layout > section.mypage-content > div.schedule-modal:nth-of-type(2) > form.schedule-modal__panel",
        )
        scroll_and_wait_for_hit(driver, form)
        form.submit()

        modal_hidden = wait_for_visibility(driver, ".schedule-modal", False)
        assert modal_hidden, "저장 후 일정 입력 화면이 닫히지 않았습니다."

        saved_title_visible = wait_for_text_contains(
            driver, ".schedule-page .monthly-calendar", TITLE
        )
        assert saved_title_visible, "저장된 일정이 달력에 표시되지 않았습니다."

    with business_step(7):
        modal_hidden = wait_for_visibility(driver, ".schedule-modal", False)
        assert modal_hidden, "일정 입력 화면이 닫히지 않았습니다."

    with business_step(8):
        driver.get(SCHEDULE_URL)
        path_ok = wait_for_path(driver, "/mypage/schedule")
        assert path_ok, "재조회한 일정 화면 경로가 예상과 다릅니다."

        calendar_visible = wait_for_visibility(
            driver, ".schedule-page .monthly-calendar", True
        )
        assert calendar_visible, "재조회한 일정 달력이 표시되지 않았습니다."

        saved_title_visible = wait_for_schedule_content(driver, TITLE)
        assert saved_title_visible, "재조회 후 저장된 일정이 표시되지 않았습니다."
finally:
    driver.quit()