"""Optional trusted local execution adapter. Use an isolated test environment.

Requires separately installed selenium and Chrome. It never reports success
unless the generated script exits successfully. Input/output: JSON on stdin/stdout.
"""
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path


def scenario_code(scenario):
    lines = ["from selenium import webdriver", "from selenium.webdriver.common.by import By",
             "from selenium.webdriver.support.ui import WebDriverWait",
             "from selenium.webdriver.support import expected_conditions as EC",
             "options = webdriver.ChromeOptions()", "options.add_argument('--headless=new')",
             "driver = webdriver.Chrome(options=options)", "driver.set_page_load_timeout(30)", "try:"]
    for step in scenario["steps"]:
        action = step["action"]
        if action == "navigate":
            lines.append(f"    driver.get({step['url']!r})")
        else:
            lines.append(f"    element = WebDriverWait(driver, 10).until(EC.visibility_of_element_located((By.CSS_SELECTOR, {step['selector']!r})))")
            if action == "click":
                lines.append("    element.click()")
            elif action == "fill":
                lines.extend(["    element.clear()", f"    element.send_keys({step['value']!r})"])
            elif action == "assert_text":
                lines.append(f"    assert {step['text']!r} in element.text, 'Expected text missing'")
            elif action == "assert_visible":
                lines.append("    assert element.is_displayed(), 'Expected visible element'")
            else:
                raise ValueError(f"Unsupported action: {action}")
    lines.extend(["finally:", "    driver.quit()"])
    return "\n".join(lines) + "\n"


def main():
    try:
        request = json.load(sys.stdin)
        if request["mode"] == "scenario":
            code = scenario_code(request["scenario"])
        elif request["mode"] == "python":
            code = request["code"]
            if hashlib.sha256(code.encode()).hexdigest() != request["code_sha256"]:
                raise ValueError("Code hash mismatch")
        else:
            raise ValueError("Unsupported execution mode")
        with tempfile.TemporaryDirectory(prefix="rainbow-execution-") as temp:
            script = Path(temp) / "test_scenario.py"
            script.write_text(code, encoding="utf-8")
            completed = subprocess.run([sys.executable, str(script)], capture_output=True, text=True,
                                       timeout=90, cwd=temp)
        result = {"success": completed.returncode == 0, "returncode": completed.returncode,
                  "code": code, "stdout": completed.stdout[-8000:], "stderr": completed.stderr[-8000:]}
    except Exception as exc:
        result = {"success": False, "error": str(exc)}
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
