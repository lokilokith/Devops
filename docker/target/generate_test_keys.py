"""Generate deterministic test keys for disposable target container and test fixtures."""

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, rsa
import os

KEY_DIR = os.path.dirname(os.path.abspath(__file__))

def main():
    # 1. Host Ed25519 Key
    host_ed25519_key = ed25519.Ed25519PrivateKey.generate()
    host_ed25519_priv = host_ed25519_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.OpenSSH,
        encryption_algorithm=serialization.NoEncryption()
    )
    host_ed25519_pub = host_ed25519_key.public_key().public_bytes(
        encoding=serialization.Encoding.OpenSSH,
        format=serialization.PublicFormat.OpenSSH
    )

    with open(os.path.join(KEY_DIR, "ssh_host_ed25519_key"), "wb") as f:
        f.write(host_ed25519_priv)
    with open(os.path.join(KEY_DIR, "ssh_host_ed25519_key.pub"), "wb") as f:
        f.write(host_ed25519_pub)

    # 2. Host RSA Key
    host_rsa_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    host_rsa_priv = host_rsa_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption()
    )
    host_rsa_pub = host_rsa_key.public_key().public_bytes(
        encoding=serialization.Encoding.OpenSSH,
        format=serialization.PublicFormat.OpenSSH
    )

    with open(os.path.join(KEY_DIR, "ssh_host_rsa_key"), "wb") as f:
        f.write(host_rsa_priv)
    with open(os.path.join(KEY_DIR, "ssh_host_rsa_key.pub"), "wb") as f:
        f.write(host_rsa_pub)

    # 3. Bootstrap opsforge-svc Key
    svc_ed25519_key = ed25519.Ed25519PrivateKey.generate()
    svc_priv = svc_ed25519_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.OpenSSH,
        encryption_algorithm=serialization.NoEncryption()
    )
    svc_pub = svc_ed25519_key.public_key().public_bytes(
        encoding=serialization.Encoding.OpenSSH,
        format=serialization.PublicFormat.OpenSSH
    )

    with open(os.path.join(KEY_DIR, "id_ed25519_opsforge_svc"), "wb") as f:
        f.write(svc_priv)
    with open(os.path.join(KEY_DIR, "id_ed25519_opsforge_svc.pub"), "wb") as f:
        f.write(svc_pub)

    print("Keys generated successfully in", KEY_DIR)

if __name__ == "__main__":
    main()
