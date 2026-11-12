"""Target Address Validator for OpsForge Execution Plane.

Implements strict address resolution and SSRF defense:
- Resolve once via socket.getaddrinfo.
- Validate resolved IP address against blocked ranges (link-local, cloud metadata, multicast, loopback).
- Validate target port constraints.
- Return validated destination to enforce connecting ONLY to the validated IP.
"""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from typing import Set


class TargetAddressValidationError(Exception):
    """Raised when target address fails validation or resolution."""

    pass


@dataclass(frozen=True)
class ValidatedTargetDestination:
    """Immutable validated target destination for execution connections."""

    original_host: str
    resolved_ip: str
    port: int
    is_ipv6: bool


# Restricted IP networks that must NEVER be accessed as privileged targets
BLOCKED_IPV4_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),  # Current network
    ipaddress.ip_network("100.64.0.0/10"),  # Shared Address Space (CGNAT)
    ipaddress.ip_network(
        "169.254.0.0/16"
    ),  # Link-Local & Cloud Metadata (169.254.169.254)
    ipaddress.ip_network("192.0.0.0/24"),  # IETF Protocol Assignments
    ipaddress.ip_network("192.0.2.0/24"),  # TEST-NET-1
    ipaddress.ip_network("198.51.100.0/24"),  # TEST-NET-2
    ipaddress.ip_network("203.0.113.0/24"),  # TEST-NET-3
    ipaddress.ip_network("224.0.0.0/4"),  # Multicast
    ipaddress.ip_network("240.0.0.0/4"),  # Reserved / Future Use
    ipaddress.ip_network("255.255.255.255/32"),  # Broadcast
]

BLOCKED_IPV6_NETWORKS = [
    ipaddress.ip_network("::/128"),  # Unspecified address
    ipaddress.ip_network("100::/64"),  # Discard prefix
    ipaddress.ip_network("2001:db8::/32"),  # Documentation
    ipaddress.ip_network("fe80::/10"),  # Link-local unicast
    ipaddress.ip_network("ff00::/8"),  # Multicast
]

# Explicit cloud metadata endpoint
CLOUD_METADATA_IPV4 = ipaddress.ip_address("169.254.169.254")

# Standard allowed SSH and administration ports
DEFAULT_ALLOWED_PORTS: Set[int] = {22, 2222}


class TargetAddressValidator:
    """Validates target hostnames and IP addresses against SSRF and network security policies."""

    def __init__(
        self,
        allow_loopback: bool = False,
        allowed_ports: Set[int] | None = None,
        custom_blocked_networks: (
            list[ipaddress.IPv4Network | ipaddress.IPv6Network] | None
        ) = None,
    ) -> None:
        """Initialize validator with security options.

        Args:
            allow_loopback: If True, loopback addresses (127.0.0.0/8, ::1) are permitted (for test harness only).
            allowed_ports: Set of permitted destination ports. Defaults to {22, 2222}.
            custom_blocked_networks: Additional IP networks to reject.
        """
        self.allow_loopback = allow_loopback
        self.allowed_ports = (
            allowed_ports if allowed_ports is not None else DEFAULT_ALLOWED_PORTS
        )
        self.custom_blocked_networks = custom_blocked_networks or []

    def validate_destination(self, host: str, port: int) -> ValidatedTargetDestination:
        """Resolve host once, validate resolved IP and port, and return ValidatedTargetDestination.

        Args:
            host: Target hostname or IP string.
            port: Target destination port.

        Returns:
            ValidatedTargetDestination with resolved IP.

        Raises:
            TargetAddressValidationError: If resolution fails, port is invalid, or IP violates security policies.
        """
        if not host or not isinstance(host, str):
            raise TargetAddressValidationError(
                "Target host must be a non-empty string."
            )

        host = host.strip()
        if not host:
            raise TargetAddressValidationError(
                "Target host cannot be empty or whitespace."
            )

        # Port boundary validation
        if not isinstance(port, int) or port < 1 or port > 65535:
            raise TargetAddressValidationError(
                f"Invalid port number: {port}. Must be 1-65535."
            )

        if self.allowed_ports and port not in self.allowed_ports:
            raise TargetAddressValidationError(
                f"Port {port} is not in the allowed destination port set: {sorted(self.allowed_ports)}"
            )

        # Resolve host once
        try:
            addr_info = socket.getaddrinfo(
                host,
                port,
                family=socket.AF_UNSPEC,
                type=socket.SOCK_STREAM,
                proto=socket.IPPROTO_TCP,
            )
        except (socket.gaierror, socket.herror, OSError) as e:
            raise TargetAddressValidationError(
                f"DNS resolution failed for '{host}': {e}"
            ) from e

        if not addr_info:
            raise TargetAddressValidationError(
                f"No address information resolved for '{host}'"
            )

        # Pick the first resolved IP
        sockaddr = addr_info[0][4]
        resolved_ip_str = sockaddr[0]

        # Parse and validate IP
        try:
            ip_obj = ipaddress.ip_address(resolved_ip_str)
        except ValueError as e:
            raise TargetAddressValidationError(
                f"Invalid resolved IP address '{resolved_ip_str}': {e}"
            ) from e

        # Validate against blocked networks
        self._validate_ip_security(ip_obj, host)

        is_ipv6 = isinstance(ip_obj, ipaddress.IPv6Address)
        return ValidatedTargetDestination(
            original_host=host,
            resolved_ip=str(resolved_ip_str),
            port=port,
            is_ipv6=is_ipv6,
        )

    def _validate_ip_security(
        self, ip_obj: ipaddress.IPv4Address | ipaddress.IPv6Address, original_host: str
    ) -> None:
        """Check IP against SSRF blocklists."""
        # 1. Cloud metadata check
        if ip_obj == CLOUD_METADATA_IPV4:
            raise TargetAddressValidationError(
                f"Destination '{original_host}' resolves to forbidden Cloud Metadata IP: {ip_obj}"
            )

        # 2. Loopback check
        if ip_obj.is_loopback:
            if not self.allow_loopback:
                raise TargetAddressValidationError(
                    f"Destination '{original_host}' resolves to loopback address {ip_obj}, which is forbidden."
                )

        # 3. Link-local check
        if ip_obj.is_link_local:
            raise TargetAddressValidationError(
                f"Destination '{original_host}' resolves to link-local address {ip_obj}, which is forbidden."
            )

        # 4. Multicast check
        if ip_obj.is_multicast:
            raise TargetAddressValidationError(
                f"Destination '{original_host}' resolves to multicast address {ip_obj}, which is forbidden."
            )

        # 5. IPv4 specific blocklist
        if isinstance(ip_obj, ipaddress.IPv4Address):
            for blocked_net in BLOCKED_IPV4_NETWORKS:
                if ip_obj in blocked_net:
                    raise TargetAddressValidationError(
                        f"Destination '{original_host}' resolves to blocked network {blocked_net}: {ip_obj}"
                    )

        # 6. IPv6 specific blocklist
        if isinstance(ip_obj, ipaddress.IPv6Address):
            for blocked_net_v6 in BLOCKED_IPV6_NETWORKS:
                if ip_obj in blocked_net_v6:
                    raise TargetAddressValidationError(
                        f"Destination '{original_host}' resolves to blocked IPv6 network {blocked_net_v6}: {ip_obj}"
                    )

        # 7. Custom blocked networks
        for custom_net in self.custom_blocked_networks:
            if ip_obj in custom_net:
                raise TargetAddressValidationError(
                    f"Destination '{original_host}' resolves to custom blocked network {custom_net}: {ip_obj}"
                )
