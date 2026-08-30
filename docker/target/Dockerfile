FROM debian:bookworm-slim

# Install OpenSSH server, sudo, python3, procps, and core utilities
RUN apt-get update && apt-get install -y --no-install-recommends \
    openssh-server \
    sudo \
    python3 \
    passwd \
    procps \
    sysstat \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create SSH privilege separation directory
RUN mkdir -p /run/sshd && chmod 0755 /run/sshd

# Configure hardened sshd config:
# - Key auth only
# - Password authentication disabled
# - Root login disabled
RUN sed -i 's/#PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config && \
    sed -i 's/PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config && \
    sed -i 's/#PermitRootLogin prohibit-password/PermitRootLogin no/' /etc/ssh/sshd_config && \
    sed -i 's/#PubkeyAuthentication yes/PubkeyAuthentication yes/' /etc/ssh/sshd_config && \
    echo "AuthenticationMethods publickey" >> /etc/ssh/sshd_config && \
    echo "KbdInteractiveAuthentication no" >> /etc/ssh/sshd_config

# Create dedicated bootstrap user: opsforge-svc
RUN useradd -m -s /bin/bash opsforge-svc && \
    passwd -l opsforge-svc && \
    mkdir -p /home/opsforge-svc/.ssh && \
    chmod 0700 /home/opsforge-svc/.ssh && \
    chown -R opsforge-svc:opsforge-svc /home/opsforge-svc

# Install test-only bootstrap authorized public key
COPY docker/target/id_ed25519_opsforge_svc.pub /home/opsforge-svc/.ssh/authorized_keys
RUN chown opsforge-svc:opsforge-svc /home/opsforge-svc/.ssh/authorized_keys && \
    chmod 0600 /home/opsforge-svc/.ssh/authorized_keys

# Install deterministic test host keys
COPY docker/target/ssh_host_ed25519_key /etc/ssh/ssh_host_ed25519_key
COPY docker/target/ssh_host_ed25519_key.pub /etc/ssh/ssh_host_ed25519_key.pub
COPY docker/target/ssh_host_rsa_key /etc/ssh/ssh_host_rsa_key
COPY docker/target/ssh_host_rsa_key.pub /etc/ssh/ssh_host_rsa_key.pub
RUN chmod 0600 /etc/ssh/ssh_host_*_key && \
    chmod 0644 /etc/ssh/ssh_host_*_key.pub

# Install opsforge-helper
COPY app/execution/helper/opsforge_helper.py /usr/local/sbin/opsforge-helper
RUN chown root:root /usr/local/sbin/opsforge-helper && \
    chmod 0750 /usr/local/sbin/opsforge-helper

# Configure strictly bounded sudoers rule for opsforge-svc
RUN echo "opsforge-svc ALL=(root) NOPASSWD: /usr/local/sbin/opsforge-helper" > /etc/sudoers.d/opsforge-svc && \
    chown root:root /etc/sudoers.d/opsforge-svc && \
    chmod 0440 /etc/sudoers.d/opsforge-svc

# Initialize protected ownership manifest directory
RUN mkdir -p /var/lib/opsforge && \
    echo '{"schema_version": 1, "managed_accounts": []}' > /var/lib/opsforge/ownership_manifest.json && \
    chown -R root:root /var/lib/opsforge && \
    chmod 0700 /var/lib/opsforge && \
    chmod 0600 /var/lib/opsforge/ownership_manifest.json

# Copy and setup entrypoint
COPY docker/target/entrypoint.sh /entrypoint.sh
RUN chmod 0755 /entrypoint.sh

EXPOSE 22

ENTRYPOINT ["/entrypoint.sh"]
