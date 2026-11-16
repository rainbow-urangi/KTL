"""Independent, versioned M01 observation criteria for the twenty source businesses.

The PDF supplies business steps, not collector-event ground truth. This module
explicitly defines a new DEVELOPMENT observation contract from those steps and
the application's static components. No observed CSV or M03/model output is used
to create, select, or change these criteria. Existing stored truths are untouched.
"""
import hashlib
import json


VERSION = "m01-business-observations-v1"
ORIGIN = "https://rainbowlab.ai.kr"
SOURCE_SHA256 = "7acaddc5a1ee2c8b2e9f96a5c4b6f557a18dac799953a270c5175084894743c8"
TEN_SOURCE_SHA256 = "8f0fb27bf28de7d39d221d71781c82fae5456dcdfb0750205024fcf85bcbef72"

_DEFINITIONS = (
    ("BU01", "개인정보 조회", (), "personal-info", "일반정보|개인정보|화면 확인|종료"),
    ("BU02", "일정 조회", ("CU01",), "schedule", "일정관리|일정이 존재하는 날짜 선택|일정 내용 확인|종료"),
    ("BU03", "일정 등록", ("CU02",), "schedule", "일정관리|날짜 선택|일정 입력|등록|종료"),
    ("BU04", "전체업무 목록 조회", (), "work/overview", "업무관리|전체 업무 관리|목록 확인|종료"),
    ("BU05", "전체업무 상세조회", (), "work/overview", "전체 업무 관리|기존 업무 1건 선택|상세 내용 확인|종료"),
    ("BU06", "일일보고 조회", ("CU03",), "work/daily", "업무관리|일일보고|기존 보고 조회|종료"),
    ("BU07", "일일보고 작성", ("CU04",), "work/daily", "일일보고|등록|내용 입력|저장|완료 확인|종료"),
    ("BU08", "주간보고 조회", ("CU05",), "work/weekly", "업무관리|주간보고|기존 주간보고 선택/조회|종료"),
    ("BU09", "주간보고 작성", ("CU06",), "work/weekly", "주간보고|등록|대상 주차 선택|내용 입력|저장|완료 확인"),
    ("BU10", "월간보고 조회", ("CU07",), "work/monthly", "업무관리|월간보고|기존 월간보고 선택/조회|종료"),
    ("BU11", "월간보고 작성", ("CU08",), "work/monthly", "월간보고|등록|대상 월 선택|내용 입력|저장|완료 확인"),
    ("BU12", "명함 목록 조회", (), "cards", "명함관리|목록 확인 또는 검색|종료"),
    ("BU13", "명함 상세조회", ("CU09",), "cards", "명함관리|기존 명함 1건 선택|상세 내용 확인|종료"),
    ("BU14", "명함 등록", ("CU10",), "cards", "명함관리|등록|테스트 명함 정보 입력|저장|종료"),
    ("BU15", "거래처 목록 조회", (), "clients", "거래처 정보 관리|목록/검색|종료"),
    ("BU16", "거래처 상세조회", (), "clients", "거래처 정보 관리|기존 거래처 1건 선택|상세 내용 확인|종료"),
    ("BU17", "거래처 정보 등록", (), "clients", "거래처 정보 관리|등록|테스트 거래처 정보 입력|저장|종료"),
    ("BU18", "자산 목록 조회", (), "assets", "자산관리|목록/검색|종료"),
    ("BU19", "자산 상세조회", (), "assets", "자산관리|기존 자산 1건 선택|상세 내용 확인|종료"),
    ("BU20", "자산 등록", (), "assets", "자산관리|등록|테스트 자산 정보 입력|저장|종료"),
)


def _dom(kind, page, selector, interaction=None):
    condition = dict(event_type=kind, page_url=page, target_selector=selector,
                     selector_match="contains")
    if interaction:
        condition["interaction_type"] = interaction
    return condition


def _requirement(identifier, label, steps, *alternatives, basis="PDF_EXPLICIT_ACTION"):
    return dict(id=identifier, label=label, source_step_indexes=list(steps),
                definition_basis=basis, alternatives=list(alternatives))


def _navigation(identifier, page, steps=(1,)):
    return _requirement(identifier + "-NAV", "대상 화면 이동 이벤트", steps,
                        dict(event_type="navigation", page_url=page),
                        basis="PDF_SCREEN_ENTRY_NOT_SCREEN_CONTENT_VERIFICATION")


def _click(identifier, suffix, label, page, selector, steps):
    return _requirement(identifier + "-" + suffix, label, steps,
                        _dom("click", page, selector))


def _input(identifier, suffix, label, page, selector, steps):
    # A keyboard focus/click is not a field value input. Do not require a mouse
    # click, and accept the existing canonical input mapping for input/change.
    return _requirement(identifier + "-" + suffix, label, steps,
                        _dom("input", page, selector),
                        basis="PDF_INPUT_STEP_SPLIT_BY_STATIC_FORM_FIELDS")


def _popup(identifier, page, selector, steps):
    return _requirement(identifier + "-OPEN", "상세 창 열림 이벤트(내용 정확성 미판정)", steps,
                        _dom("popup", page, selector, "popup_open"),
                        basis="STATIC_COMPONENT_OPEN_EVENT_NOT_BUSINESS_SUCCESS")


def _read_request(identifier, page, endpoint, steps):
    return _requirement(identifier + "-READ", "조회 요청 이벤트(응답 성공·내용 확인 아님)", steps,
                        dict(event_type="network", page_url=page,
                             api_path="/api/" + endpoint, api_method="GET"),
                        basis="STATIC_APP_READ_REQUEST_NOT_UI_VERIFICATION")


def _source_file(path, purpose):
    return dict(path="rainbow_collector_prod/admin-view/frontend/src/" + path,
                purpose=purpose, evidence_kind="STATIC_APPLICATION_SOURCE",
                live_dom_verified=False)


def _requirements(identifier, path):
    page = ORIGIN + "/mypage/" + path
    nav_steps = (1, 2) if identifier in {"BU01", "BU04", "BU06", "BU08", "BU10"} else (1,)
    requirements = [_navigation(identifier, page, nav_steps)]
    sources = [_source_file("pages/mypage/MyPage.tsx", "업무 화면의 route 정의")]
    if identifier == "BU01":
        requirements.append(_read_request(identifier, page, "auth/me", (3,)))
        sources.append(_source_file("pages/mypage/general-info/PersonalInfoPage.tsx", "개인정보 조회 요청"))
    elif identifier == "BU02":
        requirements.extend([
            _click(identifier, "SELECT", "기존 일정 선택 이벤트(날짜값·내용 미검증)", page,
                   ".schedule-event__title", (2,)),
            _popup(identifier, page, ".schedule-modal", (3,)),
        ])
        sources.extend([
            _source_file("pages/mypage/schedule/components/ScheduleEventItem.tsx", "기존 일정 선택"),
            _source_file("pages/mypage/schedule/components/ScheduleModal.tsx", "일정 상세 dialog"),
        ])
    elif identifier == "BU03":
        requirements.extend([
            _click(identifier, "DATE", "등록할 날짜 셀 선택", page,
                   ".monthly-calendar__cell", (2,)),
            _input(identifier, "TITLE", "일정 제목 입력", page, "#schedule-title", (3,)),
            _input(identifier, "CONTENT", "일정 내용 입력", page, "#schedule-description", (3,)),
            _click(identifier, "SAVE", "일정 등록 버튼 클릭(저장 성공 미판정)", page,
                   ".schedule-modal__actions > button:nth-of-type(1)", (4,)),
        ])
        sources.extend([
            _source_file("pages/mypage/schedule/components/CalendarDayCell.tsx", "날짜 셀의 등록 동작"),
            _source_file("pages/mypage/schedule/components/ScheduleModal.tsx", "제목·내용과 등록 버튼"),
        ])
    elif identifier in {"BU04", "BU12", "BU15", "BU18"}:
        endpoint = {"BU04": "work-reports", "BU12": "business-cards",
                    "BU15": "clients", "BU18": "assets"}[identifier]
        requirements.append(_read_request(identifier, page, endpoint, (3,) if identifier == "BU04" else (2,)))
        api_file = {"BU04": "workReports", "BU12": "businessCards", "BU15": "clients", "BU18": "assets"}[identifier]
        sources.append(_source_file("api/" + api_file + ".ts", "목록 GET 요청; 조회 내용/성공과 구분"))
    elif identifier in {"BU05", "BU06", "BU08", "BU10", "BU13", "BU16", "BU19"}:
        reports = path.startswith("work/")
        select_step = 3 if identifier in {"BU06", "BU08", "BU10"} else 2
        requirements.extend([
            _click(identifier, "SELECT", "기존 항목 상세조회 버튼 클릭", page,
                   ".work-report-table__title > button" if reports else ".business-card-table__title > button",
                   (select_step,)),
            _popup(identifier, page, ".work-report-detail-modal__panel",
                   (select_step,) if select_step == 3 else (3,)),
        ])
        if reports:
            source = "pages/mypage/work-management/OverallWorkManagementPage.tsx" if identifier == "BU05" else "pages/mypage/work-management/components/WorkReportListPage.tsx"
            sources.append(_source_file(source, "보고서 선택 버튼·상세 dialog"))
        else:
            component = {"BU13": ("business-card", "BusinessCardListTable"),
                         "BU16": ("client", "ClientListTable"),
                         "BU19": ("asset", "AssetListTable")}[identifier]
            sources.append(_source_file("components/management/" + component[0] + "/" + component[1] + ".tsx", "항목 상세조회 버튼"))
            sources.append(_source_file(_management_page(path), "상세 dialog panel"))
    elif identifier in {"BU07", "BU09", "BU11"}:
        requirements.append(_click(identifier, "REGISTER", "보고서 등록 열기", page,
                                   ".work-report-page__register", (2,)))
        input_step = 3 if identifier == "BU07" else 4
        if identifier != "BU07":
            requirements.append(_click(identifier, "PERIOD", "대상 기간 날짜 선택(주차·월 값 미검증)", page,
                                       ".work-report-form-modal__date-picker > div.work-date-calendar > div.work-date-calendar__grid > button.work-date-calendar__day", (3,)))
        requirements.extend([
            _input(identifier, "TITLE", "보고서 제목 입력", page, "#daily-report-create-title-input", (input_step,)),
            _input(identifier, "CONTENT", "보고서 내용 입력", page, "#daily-report-create-content-input", (input_step,)),
            _click(identifier, "SAVE", "보고서 저장 버튼 클릭(저장 성공 미판정)", page,
                   ".work-report-form-modal__submit", (input_step + 1,)),
        ])
        sources.extend([
            _source_file("pages/mypage/work-management/components/WorkReportListPage.tsx", "등록 열기와 제목·내용 필수 검증"),
            _source_file("pages/mypage/work-management/components/DailyReportCreateModal.tsx", "공통 보고서의 제목·내용 ID, 저장 버튼"),
        ])
        if identifier != "BU07":
            sources.append(_source_file("pages/mypage/work-management/components/WorkDatePickerCalendar.tsx", "특정 날짜 값에 고정하지 않은 기간 선택 셀"))
    else:
        requirements.append(_click(identifier, "REGISTER", "등록 창 열기", page,
                                   ".work-report-page__register", (2,)))
        # Positional fields are explicitly bound to the reviewed default-category
        # form. Never add an unqualified input/textarea fallback, or aliases that
        # would allow one different field to count as the required one.
        body = ".business-card-form-modal__body > section.business-card-form-modal__section:nth-of-type({section}) > div.business-card-form-modal__grid > label:nth-of-type({label}) > input"
        fields = {
            "BU14": (("COMPANY", "명함 회사명 입력", 1, 2), ("NAME", "명함 이름 입력", 1, 3), ("PHONE", "명함 전화번호 입력", 2, 1)),
            "BU17": (("COMPANY", "거래처 회사명 입력", 1, 2), ("NAME", "거래처 대표자명 입력", 1, 3), ("PHONE", "거래처 대표 전화번호 입력", 2, 1)),
            "BU20": (("NAME", "자산명 입력", 1, 2), ("SUMMARY", "자산 요약 입력", 1, 3)),
        }[identifier]
        requirements.extend(_input(identifier, suffix, label, page,
                                   body.format(section=section, label=position), (3,))
                            for suffix, label, section, position in fields)
        requirements.append(_click(identifier, "SAVE", "저장 버튼 클릭(저장 성공 미판정)", page,
                                   ".work-report-form-modal__submit", (4,)))
        sources.append(_source_file(_management_page(path), "기본 구분에서 필수 텍스트 필드·검증·등록/저장 버튼"))
    return requirements, sources


def _management_page(path):
    return {"cards": "pages/mypage/business-cards/BusinessCardManagementPage.tsx",
            "clients": "pages/mypage/client-management/ClientManagementPage.tsx",
            "assets": "pages/mypage/asset-management/AssetManagementPage.tsx"}[path]


def catalog():
    """Return a fresh JSON-compatible catalog and a hash of its exact criteria.

    Source hashes identify the independent documents; the catalog hash binds the
    new observation definitions as well. No external file or historical result
    is required at runtime, and no truth/data file is written by this function.
    """
    scenarios = []
    for identifier, name, aliases, path, original in _DEFINITIONS:
        steps = original.split("|")
        requirements, bindings = _requirements(identifier, path)
        covered = {step for row in requirements for step in row["source_step_indexes"]}
        unscored = [dict(index=index, label=label,
                         reason="실제 화면 내용·업무 완료·종료 결과를 현재 이벤트 조건만으로 확정하지 않습니다.")
                    for index, label in enumerate(steps, 1) if index not in covered]
        scenario = dict(scenario_id=identifier, business_unit_id=identifier,
                        scenario_name=identifier + " " + name, scenario_version=VERSION,
                        aliases=list(aliases), source_page=1 if int(identifier[2:]) <= 15 else 2,
                        source_steps=steps, requirements=requirements,
                        unscored_source_steps=unscored, static_bindings=bindings,
                        approved_for_official=False,
                        scope_notice="필수 관측 이벤트의 존재 여부입니다. 업무 성공·정답 순서·화면 내용·API 응답 성공은 판정하지 않습니다.")
        if identifier in {"BU14", "BU17", "BU20"}:
            scenario["binding_preconditions"] = [
                "기본 구분의 등록 양식만 지원합니다. 구분 직접 입력으로 필드 위치가 달라진 양식은 지원하지 않습니다.",
                "앱의 필수 텍스트 필드를 입력 항목으로 분리합니다. 기본 선택값 변경·선택 필드·마우스 클릭을 강제하지 않습니다.",
            ]
        scenarios.append(scenario)
    value = dict(version=VERSION, source=dict(filename="디딤돌_업무흐름_20개.pdf",
                     path="../docs/디딤돌_업무흐름_20개.pdf", sha256=SOURCE_SHA256, pages=2,
                     role="INDEPENDENT_BUSINESS_DEFINITIONS"),
                 alias_source=dict(filename="디딤돌_업무흐름_10.pdf", sha256=TEN_SOURCE_SHA256,
                                   role="TEN_BUSINESS_SUBSET_ALIASES_ONLY_NOT_EXTRA_SCENARIOS"),
                 definition_basis="NEW_DEVELOPMENT_OBSERVATION_CRITERIA_FROM_PDF_AND_STATIC_APP_SOURCE",
                 approved_for_official=False, scenario_count=len(scenarios),
                 policy=dict(raw_events_used_to_define_criteria=False, model_outputs_used_to_define_criteria=False,
                             login_included=False, fixed_ten_event_denominator=False,
                             missing_source_outcomes_not_fabricated=True,
                             input_values_not_required_or_stored=True,
                             navigation_is_not_screen_content_verification=True,
                             api_requests_are_not_ui_success_or_causality=True),
                 scenarios=scenarios)
    value["sha256"] = hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                               separators=(",", ":")).encode("utf-8")).hexdigest()
    return value
