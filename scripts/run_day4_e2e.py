import os
import subprocess
import time
import sys

def run_command(cmd, env=None, check=True):
    print(f"Running: {' '.join(cmd)}")
    return subprocess.run(cmd, env=env, check=check)

def wait_for_port(port, host="127.0.0.1", timeout=30):
    import socket
    start = time.time()
    while time.time() - start < timeout:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex((host, port)) == 0:
                return True
        time.sleep(1)
    return False

def main():
    env = os.environ.copy()
    env["DATABASE_URL"] = "postgresql://e2e_user:e2e_password@localhost:5441/opsforge_e2e_db"
    env["VAULT_MASTER_KEY"] = "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA="
    env["SECRET_KEY"] = "e2e_secret_key"
    env["JWT_SECRET_KEY"] = "e2e_jwt_secret_key"
    env["APP_ENV"] = "development"

    print("Starting E2E Database...")
    run_command(["docker", "compose", "-f", "docker-compose.e2e.yml", "up", "-d", "postgres-e2e"])

    print("Starting Disposable Target...")
    run_command(["docker", "compose", "-f", "docker-compose.target.yml", "up", "-d"])

    print("Waiting for Postgres to be ready...")
    if not wait_for_port(5441):
        print("Timeout waiting for PostgreSQL E2E database!")
        sys.exit(1)

    time.sleep(3) # Give PG a moment to initialize

    print("Seeding database (which includes migrations and KMS initialization)...")
    run_command([sys.executable, "tests/e2e/seed_e2e.py"], env=env)

    print("Starting Flask API in background...")
    api_proc = subprocess.Popen(["flask", "run", "--host=0.0.0.0", "--port=5001"], env=env)

    print("Starting Worker Loop in background...")
    worker_proc = subprocess.Popen([sys.executable, "scripts/run_worker_loop.py"], env=env)

    print("Starting SSH Broker in background...")
    broker_proc = subprocess.Popen([sys.executable, "scripts/run_broker.py"], env=env)

    print("Waiting for API to be ready on 5001...")
    time.sleep(3)

    print("Starting Vite Frontend...")
    frontend_env = os.environ.copy()
    frontend_env["VITE_API_BASE_URL"] = "/api/v1"
    frontend_env["VITE_API_PROXY_TARGET"] = "http://127.0.0.1:5001"

    npm_cmd = "npm.cmd" if os.name == "nt" else "npm"
    vite_proc = subprocess.Popen([npm_cmd, "run", "dev", "--", "--port", "5173", "--host", "127.0.0.1"], cwd="frontend", env=frontend_env)

    if not wait_for_port(5173, timeout=60):
        print("Timeout waiting for Vite Frontend")
        api_proc.terminate()
        vite_proc.terminate()
        sys.exit(1)

    print("Environment is up! Running Playwright tests...")
    pw_env = frontend_env.copy()
    pw_env["PLAYWRIGHT_TEST_BASE_URL"] = "http://127.0.0.1:5173"
    pw_env["VITE_API_URL"] = "http://localhost:5001/api"

    # We will pass the test files to playwright
    npm_cmd = "npx.cmd" if os.name == "nt" else "npx"
    exit_code = 1
    try:
        result = subprocess.run([npm_cmd, "playwright", "test", "e2e/session-control.spec.ts", "--project=chromium"], cwd="frontend", env=pw_env, check=False)
        exit_code = result.returncode
    except Exception as e:
        print(f"Playwright execution failed: {e}")
    finally:
        print("Cleaning up processes...")
        api_proc.terminate()
        worker_proc.terminate()
        broker_proc.terminate()
        vite_proc.terminate()

        # Don't tear down DB immediately if you want to inspect after failure, but best practice is to stop containers
        print("Stopping Docker containers...")
        # run_command(["docker", "compose", "-f", "docker-compose.e2e.yml", "down"])

        sys.exit(exit_code)

if __name__ == "__main__":
    main()
