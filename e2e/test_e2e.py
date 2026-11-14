"""End-to-end browser tests (Playwright + Chromium) against a running ASTRA server.

    cd backend && python run.py --reset-db        # terminal 1
    pytest e2e -q                                  # terminal 2   (pip install playwright && playwright install chromium)

Set ASTRA_URL to test another address. Screenshots are written to docs/screenshots/.
"""
import os
import time
from pathlib import Path

import pytest
import requests

pw = pytest.importorskip("playwright.sync_api")
B = os.environ.get("ASTRA_URL", "http://127.0.0.1:8000")
SHOTS = Path(__file__).resolve().parents[1] / "docs" / "screenshots"
SHOTS.mkdir(parents=True, exist_ok=True)


def token(user):
    return requests.post(B + "/api/v1/auth/login", json={"username": user, "password": "astra-demo"}, timeout=30).json()["token"]


def api(user, method, path, body=None):
    r = requests.request(method, B + "/api/v1" + path, json=body, headers={"Authorization": "Bearer " + token(user)}, timeout=60)
    return r


@pytest.fixture(scope="module")
def browser():
    try:
        requests.get(B + "/api/v1/health", timeout=5)
    except Exception:
        pytest.skip(f"ASTRA server not running at {B}")
    with pw.sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


def login(browser, user, width=1440):
    page = browser.new_page(viewport={"width": width, "height": 1000})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(B + "/")
    page.fill("input[autocomplete=username]", user)
    page.fill("input[type=password]", "astra-demo")
    page.click("button.btn-primary")
    page.wait_for_selector(".rail nav", timeout=15000)
    page.errors = errors
    return page


def run_scenario(name, days=10, speed=96):
    api("ramirez", "POST", "/simulator/reset")
    assert api("ramirez", "POST", "/simulator/start", {"scenario": name, "speed": speed, "days": days}).status_code == 200
    for _ in range(600):
        if api("ramirez", "GET", "/simulator").json()["state"] not in ("running", "paused"):
            return
        time.sleep(1)


def test_login_rejects_bad_password(browser):
    page = browser.new_page()
    page.goto(B + "/")
    page.fill("input[autocomplete=username]", "vega")
    page.fill("input[type=password]", "nope")
    page.click("button.btn-primary")
    page.wait_for_selector(".error-box")
    assert "invalid username or password" in page.inner_text(".error-box")
    page.screenshot(path=str(SHOTS / "01_login.png"))
    page.close()


def test_manual_measurement_flow(browser):
    api("ramirez", "POST", "/simulator/reset")
    page = login(browser, "okafor")
    page.goto(B + "/#/routine")
    form = page.locator("form[aria-label='Blood pressure']")
    form.wait_for()
    inputs = form.locator("input[type=number]")
    inputs.nth(0).fill("112")
    inputs.nth(1).fill("71")
    form.locator("select").nth(2).select_option("valid")
    form.locator("button.btn-primary").click()
    page.wait_for_selector("form[aria-label='Blood pressure'] .note.ok", timeout=10000)
    assert "Saved 2 measurements" in form.inner_text()
    # invalid value is rejected with a clear reason
    inputs.nth(0).fill("900")
    inputs.nth(1).fill("70")
    form.locator("button.btn-primary").click()
    page.wait_for_selector("form[aria-label='Blood pressure'] .note.warn", timeout=10000)
    assert "plausible input range" in form.inner_text()
    page.screenshot(path=str(SHOTS / "05_daily_routine.png"), full_page=False)
    assert not page.errors
    page.close()


def test_private_checkin_and_privacy(browser):
    page = login(browser, "okafor")
    page.goto(B + "/#/routine?tab=checkin")
    form = page.locator("form.private")
    form.wait_for()
    form.get_by_role("radio", name="Low").first.click()
    form.locator("textarea").first.fill("E2E SYNTHETIC note for medical")
    form.locator("button.btn-primary").click()
    page.wait_for_selector("form.private .note.ok", timeout=10000)
    page.close()
    # the Crew Medical Officer sees the alert only redacted; the flight surgeon sees it
    cmo = [a for a in api("mori", "GET", "/alerts?astronaut_id=AST-003").json() if a["rule_id"] == "DEMO-NOTE-TO-MEDICAL"]
    fs = [a for a in api("ramirez", "GET", "/alerts?astronaut_id=AST-003").json() if a["rule_id"] == "DEMO-NOTE-TO-MEDICAL"]
    assert cmo and cmo[0]["redacted"] and fs and not fs[0]["redacted"]
    page = login(browser, "vega")
    page.goto(B + "/#/overview")
    page.wait_for_selector(".lamp")
    assert "Amara" not in page.inner_text("main")  # other crew member's data never appears
    page.close()


def test_emergency_workflow_end_to_end(browser):
    run_scenario("emergency")
    api("ramirez", "POST", "/sync/link", {"earth_link_status": "offline", "comm_delay_seconds": 2})
    page = login(browser, "mori")
    page.goto(B + "/#/overview")
    page.wait_for_selector(".lamp.tone-urgent", timeout=15000)
    assert "Urgent procedure" in page.inner_text(".lamp")
    page.screenshot(path=str(SHOTS / "02_mission_overview_urgent.png"), full_page=True)
    page.click("text=Open Medical Response Center")
    page.wait_for_selector(".event-hero.is-urgent", timeout=15000)
    assert "SYNTHETIC DEMONSTRATION PROCEDURE" in page.inner_text(".procedure")
    # verification checklist
    first = page.locator(".checklist li button").first
    first.click()
    page.wait_for_function("document.querySelectorAll('.checklist li button:disabled').length >= 1", timeout=10000)
    # escalate
    page.fill("textarea[placeholder^='What the crew member reports']", "E2E: SpO2 repeated on second oximeter, 90 %")
    page.click("text=Escalate to medical personnel")
    page.wait_for_selector(".state-track li.now:has-text('Escalated')", timeout=15000)
    page.wait_for_selector(".panel:has-text('Medical reports') .linkish", timeout=15000)
    page.screenshot(path=str(SHOTS / "04_medical_response_center.png"), full_page=True)
    # report is queued while the Earth link is offline, delivered when it returns
    reports = api("mori", "GET", "/medical-reports").json()
    assert reports and reports[0]["sync_status"] == "queued"
    api("ramirez", "POST", "/sync/link", {"earth_link_status": "online", "comm_delay_seconds": 0})
    api("ramirez", "POST", "/sync/run")
    api("ramirez", "POST", "/sync/run")
    assert api("mori", "GET", f"/medical-reports/{reports[0]['id']}").json()["sync_status"] == "acknowledged"
    # resolving requires medical role + reason
    page.fill("label:has-text('Reason') input", "E2E: stabilised per synthetic scenario; monitoring")
    page.click("text=Move to Monitoring")
    page.wait_for_selector(".state-track li.now:has-text('Monitoring')", timeout=10000)
    page.fill("label:has-text('Reason') input", "E2E: resolved by CMO after review")
    page.click("button:has-text('Resolve')")
    page.wait_for_selector(".state-track li.now:has-text('Resolved')", timeout=10000)
    assert not page.errors
    api("ramirez", "POST", "/sync/link", {"earth_link_status": "online", "comm_delay_seconds": 300})
    page.close()


def test_body_systems_interaction(browser):
    page = login(browser, "mori")
    page.goto(B + "/#/body")
    page.wait_for_selector(".system-head h1")
    page.locator(".bodymap .region-respiratory path").first.click()
    page.wait_for_selector(".system-head h1:has-text('Respiratory')", timeout=10000)
    page.locator(".bodymap .region-immune circle").first.click()
    page.wait_for_selector(".system-head h1:has-text('Immune')", timeout=10000)
    page.click(".bodymap .region-cardiovascular")
    page.wait_for_selector(".system-head h1:has-text('Cardiovascular')", timeout=10000)
    time.sleep(1.5)
    page.screenshot(path=str(SHOTS / "03_body_systems.png"), full_page=False)
    page.close()


def test_analytics_and_inspection(browser):
    page = login(browser, "vega")
    page.goto(B + "/#/analytics?metric=heart_rate")
    page.wait_for_selector(".chart svg circle.pt", timeout=15000)
    page.locator(".chart svg circle.pt").last.click(force=True)
    page.wait_for_selector(".drawer:has-text('Observation ID')", timeout=10000)
    assert "Device" in page.inner_text(".drawer")
    page.keyboard.press("Escape")
    page.screenshot(path=str(SHOTS / "06_health_analytics.png"), full_page=False)
    page.close()


def test_environment_radiation_and_library(browser):
    run_scenario("radiation_event")
    page = login(browser, "vega")
    page.goto(B + "/#/environment")
    page.wait_for_selector("text=Radiation event", timeout=15000)
    time.sleep(1)
    page.screenshot(path=str(SHOTS / "07_mission_environment.png"), full_page=True)
    page.goto(B + "/#/library")
    page.click("text=Assessment rules")
    page.wait_for_selector("text=Demonstration only")
    page.screenshot(path=str(SHOTS / "08_knowledge_library.png"), full_page=False)
    page.close()


def test_admin_has_no_health_pages_and_ops(browser):
    page = login(browser, "admin")
    page.wait_for_selector(".sim-panel", timeout=10000)
    nav = page.inner_text(".rail nav")
    assert "Mission overview" not in nav and "Mission operations" in nav
    page.screenshot(path=str(SHOTS / "09_mission_operations.png"), full_page=False)
    page.close()


def test_mobile_layout(browser):
    page = login(browser, "vega", width=390)
    page.goto(B + "/#/overview")
    page.wait_for_selector(".lamp")
    page.screenshot(path=str(SHOTS / "10_mobile_overview.png"), full_page=False)
    page.close()
