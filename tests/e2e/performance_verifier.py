import requests
import time
import sys
from concurrent.futures import ThreadPoolExecutor

BASE_URL = "http://localhost/api/v1"
ADMIN_CREDS = {"username": "admin", "password": "secret123"}
REQUESTS_COUNT = 50

def login():
    r = requests.post(f"{BASE_URL}/auth/login", json=ADMIN_CREDS)
    if r.status_code != 200:
        print("Login failed")
        sys.exit(1)
    return {"Authorization": f"Bearer {r.json()['data']['access_token']}"}

def make_request(url, headers):
    start = time.perf_counter()
    r = requests.get(url, headers=headers)
    end = time.perf_counter()
    return end - start, r.status_code

def run_performance_test():
    headers = login()
    endpoints = [f"{BASE_URL}/vault/secrets", f"{BASE_URL}/audit"]
    failures = 0

    print("Verifying Performance & Load Thresholds...")

    for endpoint in endpoints:
        print(f"\nTesting endpoint: {endpoint} ({REQUESTS_COUNT} requests)")
        times = []
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(make_request, endpoint, headers) for _ in range(REQUESTS_COUNT)]
            for future in futures:
                duration, status = future.result()
                if status == 200:
                    times.append(duration)
                else:
                    print(f"Warning: Request failed with status {status}")

        if not times:
            print(f"FAIL: No successful requests for {endpoint}")
            failures += 1
            continue

        times.sort()
        idx = int(0.95 * len(times))
        p95 = times[idx] * 1000  # Convert to ms
        mean = (sum(times) / len(times)) * 1000

        print(f"Mean response time: {mean:.2f}ms")
        print(f"95th percentile response time: {p95:.2f}ms")

        if p95 < 500:
            print(f"PASS: {endpoint} P95 response time is {p95:.2f}ms (< 500ms)")
        else:
            print(f"FAIL: {endpoint} P95 response time is {p95:.2f}ms (>= 500ms)")
            failures += 1

    if failures > 0:
        print(f"\nPerformance Certification Failed with {failures} violations.")
        sys.exit(1)
    else:
        print("\nPerformance Certification Passed: 0 violations.")
        sys.exit(0)

if __name__ == "__main__":
    run_performance_test()
