from __future__ import annotations

import ipaddress
import socket


class NetworkPolicy:
    def validate_host(self, host: str) -> tuple[str, ...]:
        value = str(host or "").strip().rstrip(".").casefold()
        if not value or value == "localhost" or value.endswith(".localhost"):
            raise ValueError("network policy rejects local targets")
        try:
            addresses = (ipaddress.ip_address(value),)
        except ValueError:
            try:
                addresses = tuple({ipaddress.ip_address(item[4][0]) for item in socket.getaddrinfo(value, None, type=socket.SOCK_STREAM)})
            except OSError as exc:
                raise ValueError("network policy could not resolve target") from exc
        if not addresses or any(
            address.is_private or address.is_loopback or address.is_link_local or address.is_multicast
            or address.is_reserved or address.is_unspecified
            for address in addresses
        ):
            raise ValueError("network policy rejects non-public targets")
        return tuple(sorted(str(address) for address in addresses))

