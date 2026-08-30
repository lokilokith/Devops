"""Unit tests for TargetAddressValidator and SSRF defense."""

import socket

import pytest

from app.execution.network_validator import (
    TargetAddressValidationError,
    TargetAddressValidator,
    ValidatedTargetDestination,
)


def test_target_address_validator_public_hostname(monkeypatch):
    """Test standard public hostname resolution and port validation."""

    def fake_getaddrinfo(host, port, **kwargs):
        return [
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                ("93.184.216.34", port),
            )
        ]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

    validator = TargetAddressValidator(allow_loopback=False, allowed_ports={22, 2222})
    dest = validator.validate_destination("example.com", 22)

    assert isinstance(dest, ValidatedTargetDestination)
    assert dest.original_host == "example.com"
    assert dest.resolved_ip == "93.184.216.34"
    assert dest.port == 22
    assert not dest.is_ipv6


def test_target_address_validator_blocks_cloud_metadata(monkeypatch):
    """Test strict rejection of AWS/GCP/Azure cloud metadata IP 169.254.169.254."""

    def fake_getaddrinfo(host, port, **kwargs):
        return [
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                ("169.254.169.254", port),
            )
        ]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

    validator = TargetAddressValidator(
        allow_loopback=True
    )  # Even with loopback enabled, cloud metadata must fail
    with pytest.raises(TargetAddressValidationError, match="Cloud Metadata IP"):
        validator.validate_destination("metadata.google.internal", 22)


def test_target_address_validator_blocks_loopback_by_default(monkeypatch):
    """Test loopback addresses (127.0.0.1, 127.0.0.5) are blocked when allow_loopback=False."""

    def fake_getaddrinfo(host, port, **kwargs):
        return [
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                ("127.0.0.1", port),
            )
        ]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

    validator = TargetAddressValidator(allow_loopback=False)
    with pytest.raises(TargetAddressValidationError, match="loopback address"):
        validator.validate_destination("localhost", 22)


def test_target_address_validator_allows_loopback_in_test_mode(monkeypatch):
    """Test loopback addresses are allowed when allow_loopback=True for local test fixtures."""

    def fake_getaddrinfo(host, port, **kwargs):
        return [
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                ("127.0.0.1", port),
            )
        ]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

    validator = TargetAddressValidator(allow_loopback=True, allowed_ports={22, 2222})
    dest = validator.validate_destination("127.0.0.1", 2222)
    assert dest.resolved_ip == "127.0.0.1"
    assert dest.port == 2222


def test_target_address_validator_blocks_link_local(monkeypatch):
    """Test link-local addresses (169.254.1.1, fe80::1) are strictly rejected."""

    def fake_getaddrinfo(host, port, **kwargs):
        return [
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                ("169.254.10.20", port),
            )
        ]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

    validator = TargetAddressValidator(allow_loopback=True)
    with pytest.raises(TargetAddressValidationError, match="link-local address"):
        validator.validate_destination("linklocal.target", 22)


def test_target_address_validator_blocks_multicast(monkeypatch):
    """Test multicast addresses (224.0.0.1, ff02::1) are rejected."""

    def fake_getaddrinfo(host, port, **kwargs):
        return [
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                ("224.0.0.251", port),
            )
        ]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

    validator = TargetAddressValidator(allow_loopback=True)
    with pytest.raises(TargetAddressValidationError, match="multicast address"):
        validator.validate_destination("mdns.target", 22)


def test_target_address_validator_port_boundary():
    """Test port boundaries (invalid ports, out of range, disallowed ports)."""
    validator = TargetAddressValidator(allowed_ports={22, 2222})

    with pytest.raises(TargetAddressValidationError, match="Invalid port number: 0"):
        validator.validate_destination("target.internal", 0)

    with pytest.raises(
        TargetAddressValidationError, match="Invalid port number: 70000"
    ):
        validator.validate_destination("target.internal", 70000)

    with pytest.raises(
        TargetAddressValidationError, match="Port 80 is not in the allowed"
    ):
        validator.validate_destination("target.internal", 80)


def test_target_address_validator_empty_host():
    """Test empty or whitespace hostnames are rejected."""
    validator = TargetAddressValidator()
    with pytest.raises(
        TargetAddressValidationError, match="Target host must be a non-empty string"
    ):
        validator.validate_destination("", 22)

    with pytest.raises(
        TargetAddressValidationError, match="Target host cannot be empty"
    ):
        validator.validate_destination("   ", 22)


def test_target_address_validator_dns_failure(monkeypatch):
    """Test DNS failure raises TargetAddressValidationError."""

    def fake_getaddrinfo(host, port, **kwargs):
        raise socket.gaierror(-2, "Name or service not known")

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

    validator = TargetAddressValidator()
    with pytest.raises(TargetAddressValidationError, match="DNS resolution failed"):
        validator.validate_destination("nonexistent-host-12345.local", 22)
