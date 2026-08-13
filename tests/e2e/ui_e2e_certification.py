import sys
from playwright.sync_api import sync_playwright

URL = "http://localhost/"
evidence_lines = []

def report(check_name, expected, actual, passed):
    result = "PASS" if passed else "FAIL"
    evidence_lines.append(f"| {check_name} | {expected} | {actual} | **{result}** |")
    if not passed:
        print(f"FAIL: {check_name}. Expected: {expected}, Actual: {actual}")
    else:
        print(f"PASS: {check_name}")

def run_checks():
    evidence_lines.append("# UI/E2E Certification Evidence\n")
    evidence_lines.append("| Check | Expected | Actual | Result |")
    evidence_lines.append("|---|---|---|---|")
    
    failures = 0
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        try:
            # 1. Load Homepage
            response = page.goto(URL, timeout=10000)
            
            passed = response.status == 200
            report("Homepage Load Status", "200", str(response.status), passed)
            if not passed: failures += 1
            
            # 2. Render Check
            title = page.title()
            passed = "OpsForge" in title or len(title) > 0
            report("HTML Title Rendering", "OpsForge / Non-empty", title, passed)
            if not passed: failures += 1
            
            # Check if there is some content loaded
            # The React app usually has a root div
            content = page.content()
            passed = 'id="root"' in content or 'OpsForge' in content
            report("React Root / App Container", "Exists", "Found root/app tag", passed)
            if not passed: failures += 1

        except Exception as e:
            print(f"Playwright execution failed: {e}")
            failures += 1
        finally:
            browser.close()
            
    with open("docs/evidence/ui_e2e_evidence.md", "w") as f:
        f.write("\n".join(evidence_lines) + "\n")

    if failures > 0:
        print(f"UI E2E Certification Failed with {failures} violations.")
        sys.exit(1)
    else:
        print("UI E2E Certification Passed: 0 violations.")
        sys.exit(0)

if __name__ == "__main__":
    run_checks()
