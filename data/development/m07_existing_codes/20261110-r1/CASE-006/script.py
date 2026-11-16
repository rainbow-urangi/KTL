import os
from urllib.parse import urlparse

from ktl_runtime import business_step
from selenium import webdriver
from selenium.common.exceptions import StaleElementReferenceException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


def wait_visible(driver, selector, timeout=30):
    return WebDriverWait(driver, timeout).until(
        EC.visibility_of_element_located((By.CSS_SELECTOR, selector))
    )


def wait_invisible(driver, selector, timeout=30):
    return WebDriverWait(driver, timeout).until(
        EC.invisibility_of_element_located((By.CSS_SELECTOR, selector))
    )


def wait_text_contains(driver, selector, expected, timeout=30):
    def contains_text(current_driver):
        return current_driver.execute_script(
            """
            const element = document.querySelector(arguments[0]);
            return !!element &&
                (element.innerText || element.textContent || '').includes(arguments[1]);
            """,
            selector,
            expected,
        )

    return WebDriverWait(driver, timeout).until(contains_text)


def wait_url_path(driver, expected_path, timeout=30):
    return WebDriverWait(driver, timeout).until(
        lambda current_driver: urlparse(current_driver.current_url).path == expected_path
    )


def scroll_target_to_center(driver, selector):
    element = wait_visible(driver, selector)
    driver.execute_script(
        """
        arguments[0].scrollIntoView({
            block: "center",
            inline: "center",
            behavior: "instant"
        });
        """,
        element,
    )

    def is_center_interactable(current_driver):
        try:
            return current_driver.execute_script(
                """
                const element = arguments[0];
                const rect = element.getBoundingClientRect();
                const x = rect.left + rect.width / 2;
                const y = rect.top + rect.height / 2;
                const inside = x >= 0 && y >= 0 &&
                    x < window.innerWidth && y < window.innerHeight;
                const hit = document.elementFromPoint(x, y);
                return inside && !!hit &&
                    (hit === element || element.contains(hit));
                """,
                element,
            )
        except StaleElementReferenceException:
            return False

    WebDriverWait(driver, 20).until(is_center_interactable)
    return element


def native_click(driver, selector):
    scroll_target_to_center(driver, selector).click()


def wait_focused(driver, selector, timeout=20):
    return WebDriverWait(driver, timeout).until(
        lambda current_driver: current_driver.execute_script(
            """
            const element = document.querySelector(arguments[0]);
            return !!element && document.activeElement === element;
            """,
            selector,
        )
    )


def wait_input_value(driver, selector, expected, timeout=30):
    return WebDriverWait(driver, timeout).until(
        lambda current_driver: current_driver.execute_script(
            """
            const element = document.querySelector(arguments[0]);
            return !!element && element.value === arguments[1];
            """,
            selector,
            expected,
        )
    )


options = webdriver.ChromeOptions()
if os.environ.get("KTL_M04_HEADLESS", "1") != "0":
    options.add_argument("--headless=new")

driver = webdriver.Chrome(options=options)

try:
    driver.set_window_size(1440, 1100)
    wait = WebDriverWait(driver, 30)

    # 로그인 설정
    driver.get("https://rainbowlab.ai.kr/rbem")
    wait.until(
        lambda current_driver: current_driver.execute_script(
            "return document.readyState === 'complete';"
        )
    )
    if driver.find_elements(By.CSS_SELECTOR, "#loginId"):
        username = os.environ["KTL_M04_RBEM_USERNAME"]
        password = os.environ["KTL_M04_RBEM_PASSWORD"]

        username_element = scroll_target_to_center(driver, "#loginId")
        username_element.click()
        username_element.clear()
        username_element.send_keys(username)

        password_element = scroll_target_to_center(driver, "#password")
        password_element.click()
        password_element.clear()
        password_element.send_keys(password)

        native_click(driver, 'form.login-card button.login-submit[type="submit"]')
        wait.until(
            lambda current_driver: not current_driver.find_elements(
                By.CSS_SELECTOR, "#loginId"
            )
        )

    with business_step(1):
        driver.get("https://rainbowlab.ai.kr/mypage/work/weekly")
        assert wait_url_path(driver, "/mypage/work/weekly"), "업무 목록 경로가 올바르지 않습니다."
        assert wait_visible(driver, ".work-report-page .work-report-table"), "업무 목록이 표시되지 않습니다."
        assert wait_visible(driver, ".work-report-table__title button"), "업무 목록 버튼이 표시되지 않습니다."

    with business_step(2):
        native_click(
            driver,
            "div.mypage-layout > section.mypage-content > div.work-report-page > div.work-report-page__bottom:nth-of-type(2) > div.work-report-page__footer:nth-of-type(2) > button.work-report-page__register",
        )
        assert wait_visible(driver, ".work-report-form-modal"), "업무 등록 화면이 표시되지 않습니다."
        assert wait_text_contains(
            driver, ".work-report-form-modal__date-button", "2026.11.10 (화)"
        ), "초기 보고 대상일이 올바르지 않습니다."

    with business_step(3):
        assert wait_visible(driver, ".work-report-form-modal"), "업무 입력 화면이 표시되지 않습니다."

    with business_step(4):
        native_click(
            driver,
            "section.mypage-content > div.work-report-form-modal:nth-of-type(2) > div.work-report-form-modal__panel > div.work-report-form-modal__meta:nth-of-type(2) > div.work-report-form-modal__date > button.work-report-form-modal__date-button",
        )
        assert wait_visible(
            driver, ".work-report-form-modal__date-picker"
        ), "보고 대상일 달력이 표시되지 않습니다."

    with business_step(5):
        assert wait_visible(
            driver, ".work-report-form-modal__date-picker"
        ), "보고 대상일 달력이 표시되지 않습니다."

    with business_step(6):
        native_click(driver, '.work-date-calendar__day[aria-label="2026-11-09"]')
        assert wait_invisible(
            driver, ".work-report-form-modal__date-picker"
        ), "보고 대상일 달력이 닫히지 않았습니다."
        assert wait_visible(driver, ".work-report-form-modal"), "업무 입력 화면이 닫혔습니다."
        assert wait_text_contains(
            driver, ".work-report-form-modal__date-button", "2026.11.09 (월)"
        ), "선택한 보고 대상일이 올바르지 않습니다."

    with business_step(7):
        assert wait_invisible(
            driver, ".work-report-form-modal__date-picker"
        ), "보고 대상일 달력이 닫히지 않았습니다."

    with business_step(8):
        title_selector = "#daily-report-create-title-input"
        title_value = "KTL-7C91-CU06-TITLE-P2-GPT-20261110-R1"
        title_element = scroll_target_to_center(driver, title_selector)
        title_element.click()
        title_element.clear()
        title_element.send_keys(title_value)
        assert wait_input_value(driver, title_selector, title_value), "제목 입력값이 올바르지 않습니다."
        assert wait_focused(driver, title_selector), "제목 입력란에 포커스가 없습니다."

    with business_step(9):
        content_selector = "#daily-report-create-content-input"
        content_value = "KTL-7C91-CU06 new report content-P2-GPT-20261110-R1"
        content_element = scroll_target_to_center(driver, content_selector)
        content_element.click()
        content_element.clear()
        content_element.send_keys(content_value)
        assert wait_input_value(driver, content_selector, content_value), "내용 입력값이 올바르지 않습니다."
        assert wait_focused(driver, content_selector), "내용 입력란에 포커스가 없습니다."

    with business_step(10):
        native_click(
            driver,
            "div.mypage-layout > section.mypage-content > div.work-report-form-modal:nth-of-type(2) > div.work-report-form-modal__panel > div.work-report-form-modal__footer:nth-of-type(4) > button.work-report-form-modal__submit",
        )
        assert wait_invisible(driver, ".work-report-form-modal"), "저장 후 입력 화면이 닫히지 않았습니다."
        assert wait_visible(
            driver, ".work-report-message-modal__panel"
        ), "저장 결과 화면이 표시되지 않습니다."
        assert wait_text_contains(
            driver, ".work-report-message-modal__panel", "저장되었습니다."
        ), "저장 완료 메시지가 올바르지 않습니다."

    with business_step(11):
        assert wait_visible(
            driver, ".work-report-message-modal__panel"
        ), "저장 결과 화면이 표시되지 않습니다."

    with business_step(12):
        assert wait_invisible(driver, ".work-report-form-modal"), "업무 입력 화면이 닫히지 않았습니다."

    with business_step(13):
        driver.get("https://rainbowlab.ai.kr/mypage/work/weekly")
        assert wait_url_path(driver, "/mypage/work/weekly"), "업무 목록 경로가 올바르지 않습니다."
        assert wait_visible(driver, ".work-report-page .work-report-table"), "업무 목록이 표시되지 않습니다."
        assert wait_visible(driver, ".work-report-table__title button"), "업무 목록 버튼이 표시되지 않습니다."
        assert wait_text_contains(
            driver,
            ".work-report-page .work-report-table",
            "KTL-7C91-CU06-TITLE-P2-GPT-20261110-R1",
        ), "저장한 업무가 목록에 표시되지 않습니다."
finally:
    driver.quit()