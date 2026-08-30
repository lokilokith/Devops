#!/bin/bash
set -e

# Ensure host key permissions
chmod 600 /etc/ssh/ssh_host_*_key 2>/dev/null || true
chmod 644 /etc/ssh/ssh_host_*_key.pub 2>/dev/null || true

# Ensure opsforge-svc SSH directory permissions
if [ -d /home/opsforge-svc/.ssh ]; then
    chown -R opsforge-svc:opsforge-svc /home/opsforge-svc/.ssh
    chmod 700 /home/opsforge-svc/.ssh
    chmod 600 /home/opsforge-svc/.ssh/authorized_keys 2>/dev/null || true
fi

# Ensure helper permissions
chown root:root /usr/local/sbin/opsforge-helper
chmod 0750 /usr/local/sbin/opsforge-helper

# Ensure sudoers.d permissions
chown root:root /etc/sudoers.d/opsforge-svc
chmod 0440 /etc/sudoers.d/opsforge-svc

# Ensure ownership manifest permissions
mkdir -p /var/lib/opsforge
if [ ! -f /var/lib/opsforge/ownership_manifest.json ]; then
    echo '{"schema_version": 1, "managed_accounts": []}' > /var/lib/opsforge/ownership_manifest.json
fi
chown -R root:root /var/lib/opsforge
chmod 700 /var/lib/opsforge
chmod 600 /var/lib/opsforge/ownership_manifest.json

# Execute sshd in foreground
exec /usr/sbin/sshd -D -e
