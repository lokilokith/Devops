import requests
import sys

URL = "http://localhost/"

def run_ui_check():
    print("Verifying UI Integration...")
    failures = 0
    try:
        r = requests.get(URL)
        if r.status_code == 200:
            print(f"PASS: Frontend loaded successfully from {URL} (Status {r.status_code})")
            if "OpsForge" in r.text or "<html" in r.text.lower():
                print("PASS: Verified HTML content received")
            else:
                print("FAIL: Response did not look like HTML")
                failures += 1
        else:
            print(f"FAIL: Frontend returned status {r.status_code}")
            failures += 1
    except Exception as e:
        print(f"FAIL: Could not connect to {URL} - {e}")
        failures += 1

    if failures > 0:
        print(f"UI Integration Certification Failed with {failures} violations.")
        sys.exit(1)
    else:
        print("UI Integration Certification Passed: 0 violations.")
        sys.exit(0)

if __name__ == "__main__":
    run_ui_check()
