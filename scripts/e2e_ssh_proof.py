import asyncio
import asyncssh
import sys
import logging

logging.basicConfig(level=logging.INFO, format="%(message)s")

async def run_proof(session_token: str):
    """
    Connect to the OpsForge broker using the session token as the password,
    and attempt to run a privileged command allowed by the JIT grant.
    """
    try:
        # Broker runs on port 2223 by default in our E2E script
        async with asyncssh.connect(
            '127.0.0.1',
            port=2223,
            username='opsforge-svc',
            password=session_token,
            known_hosts=None # Trust whatever the broker presents for test
        ) as conn:
            # First, check that we can run basic commands (non-privileged)
            result = await conn.run('whoami')
            if result.exit_status != 0:
                logging.error(f"Failed basic SSH connection test. Exit status: {result.exit_status}, stdout: {result.stdout}, stderr: {result.stderr}")
                sys.exit(1)

            # Now, attempt the privileged command (from system_health_check)
            # The opsforge_helper installs sudo drop-ins that allow these commands
            logging.info("Attempting privileged capability: sudo /usr/bin/uptime")
            priv_result = await conn.run('sudo -n /usr/bin/uptime')

            if priv_result.exit_status == 0:
                logging.info(f"SUCCESS: Privileged capability exercised. Output: {priv_result.stdout.strip()}")
                sys.exit(0)
            else:
                # If sudo fails, it means the privilege was NOT granted/was revoked
                logging.error(f"DENIED: Privileged capability denied. Error: {priv_result.stderr.strip()}")
                sys.exit(2)

    except asyncssh.PermissionDenied:
        logging.error("DENIED: SSH Authentication failed (session token invalid or expired)")
        sys.exit(3)
    except Exception as e:
        logging.error(f"FAILURE: Unexpected error: {e}")
        sys.exit(4)

if __name__ == "__main__":
    import os
    token = os.environ.get('SESSION_TOKEN')
    if not token:
        print("Error: SESSION_TOKEN environment variable not set")
        sys.exit(1)

    asyncio.run(run_proof(token))
