"""Pytest process-wide outbound-network guard.

Imported by the root ``tests/conftest.py`` before application modules.  The
patch therefore protects test-module collection/import as well as fixture and
test execution.  Only loopback TCP/DNS targets are allowed by default.
"""

from __future__ import annotations

import contextlib
import contextvars
import functools
import ipaddress
import socket
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

_BLOCK_MESSAGE = (
    "测试禁止真实外网连接；该用例需 mock 外部调用。"
    "如确需联网，使用 @pytest.mark.allow_network 并登记豁免理由。"
)

_allow_network: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "allow_test_network", default=False
)
_current_nodeid: contextvars.ContextVar[str] = contextvars.ContextVar(
    "network_guard_nodeid", default="collection/import"
)
_installed = False

_CHECKED_IN_TESTS_ROOT = Path(__file__).resolve().parent
# Key: nodeid relative to ``backend/tests``. Value: target/reason/owner/PM trail.
# Empty by design: the repository currently has no approved real-network tests.
AUDITED_ALLOW_NETWORK_EXEMPTIONS: dict[str, dict[str, str]] = {}

_original_socket_connect = socket.socket.connect
_original_socket_connect_ex = socket.socket.connect_ex
_original_socket_sendto = socket.socket.sendto
_original_create_connection = socket.create_connection
_original_getaddrinfo = socket.getaddrinfo
_original_gethostbyname = socket.gethostbyname
_original_gethostbyname_ex = socket.gethostbyname_ex
_original_gethostbyaddr = socket.gethostbyaddr
_original_getnameinfo = socket.getnameinfo


class OutboundNetworkBlockedError(RuntimeError):
    """Raised when a pytest Python process attempts a non-loopback connection."""


def _normalise_host(host: Any) -> str | None:
    if isinstance(host, bytes):
        try:
            return host.decode("ascii")
        except UnicodeDecodeError:
            return None
    if isinstance(host, str):
        return host.rstrip(".").lower()
    return None


def _is_loopback_host(host: Any) -> bool:
    value = _normalise_host(host)
    if value == "localhost":
        return True
    if value is None:
        return False
    try:
        return ipaddress.ip_address(value).is_loopback
    except ValueError:
        return False


def _host_from_address(address: Any) -> Any | None:
    # AF_INET / AF_INET6 addresses are tuples whose first item is the host.
    # str/bytes addresses are AF_UNIX paths and never leave the host.
    if isinstance(address, tuple) and address:
        return address[0]
    return None


def _assert_allowed(host: Any) -> None:
    if _allow_network.get() or _is_loopback_host(host):
        return
    nodeid = _current_nodeid.get()
    raise OutboundNetworkBlockedError(f"{_BLOCK_MESSAGE} target={host!r}; nodeid={nodeid}")


@functools.wraps(_original_socket_connect)
def _guarded_socket_connect(sock: socket.socket, address: Any) -> Any:
    host = _host_from_address(address)
    if host is not None:
        _assert_allowed(host)
    return _original_socket_connect(sock, address)


@functools.wraps(_original_socket_connect_ex)
def _guarded_socket_connect_ex(sock: socket.socket, address: Any) -> int:
    host = _host_from_address(address)
    if host is not None:
        _assert_allowed(host)
    return _original_socket_connect_ex(sock, address)


@functools.wraps(_original_socket_sendto)
def _guarded_socket_sendto(sock: socket.socket, data: Any, *args: Any) -> int:
    # sendto(data, address) and sendto(data, flags, address) both place the
    # destination last. This closes direct UDP/DNS paths that do not connect.
    if args:
        host = _host_from_address(args[-1])
        if host is not None:
            _assert_allowed(host)
    return _original_socket_sendto(sock, data, *args)


@functools.wraps(_original_create_connection)
def _guarded_create_connection(address: Any, *args: Any, **kwargs: Any) -> socket.socket:
    host = _host_from_address(address)
    if host is not None:
        _assert_allowed(host)
    return _original_create_connection(address, *args, **kwargs)


@functools.wraps(_original_getaddrinfo)
def _guarded_getaddrinfo(host: Any, *args: Any, **kwargs: Any) -> Any:
    # ``host=None`` means local/wildcard resolution and is safe.
    if host is not None:
        _assert_allowed(host)
    return _original_getaddrinfo(host, *args, **kwargs)


@functools.wraps(_original_gethostbyname)
def _guarded_gethostbyname(host: Any) -> str:
    _assert_allowed(host)
    return _original_gethostbyname(host)


@functools.wraps(_original_gethostbyname_ex)
def _guarded_gethostbyname_ex(host: Any) -> tuple[str, list[str], list[str]]:
    _assert_allowed(host)
    return _original_gethostbyname_ex(host)


@functools.wraps(_original_gethostbyaddr)
def _guarded_gethostbyaddr(host: Any) -> tuple[str, list[str], list[str]]:
    _assert_allowed(host)
    return _original_gethostbyaddr(host)


@functools.wraps(_original_getnameinfo)
def _guarded_getnameinfo(sockaddr: Any, flags: int) -> tuple[str, str]:
    host = _host_from_address(sockaddr)
    if host is not None:
        _assert_allowed(host)
    return _original_getnameinfo(sockaddr, flags)


def install() -> None:
    """Install the process-wide guard once."""
    global _installed
    if _installed:
        return
    socket.socket.connect = _guarded_socket_connect
    socket.socket.connect_ex = _guarded_socket_connect_ex
    socket.socket.sendto = _guarded_socket_sendto
    socket.create_connection = _guarded_create_connection
    socket.getaddrinfo = _guarded_getaddrinfo
    socket.gethostbyname = _guarded_gethostbyname
    socket.gethostbyname_ex = _guarded_gethostbyname_ex
    socket.gethostbyaddr = _guarded_gethostbyaddr
    socket.getnameinfo = _guarded_getnameinfo
    _installed = True


@contextlib.contextmanager
def _network_permission(*, allowed: bool, nodeid: str) -> Iterator[None]:
    allow_token = _allow_network.set(allowed)
    node_token = _current_nodeid.set(nodeid)
    try:
        yield
    finally:
        _current_nodeid.reset(node_token)
        _allow_network.reset(allow_token)


def pytest_configure(config: Any) -> None:
    install()
    config.addinivalue_line(
        "markers",
        "allow_network: permit real non-loopback network for one test; requires "
        "documented target, reason, owner, and PM approval",
    )


def _checked_in_allow_network_nodeids(items: list[Any]) -> set[str]:
    """Return collected checked-in tests that inherit ``allow_network``.

    Inspecting collected items follows pytest's real marker inheritance, so
    function, class and module-level ``pytestmark`` forms cannot diverge from
    the permission decision in ``pytest_runtest_protocol``.
    """
    marked_nodeids: set[str] = set()
    for item in items:
        try:
            relative_path = Path(str(item.path)).resolve().relative_to(
                _CHECKED_IN_TESTS_ROOT
            )
        except ValueError:
            # Generated probes outside the checked-in test tree may exercise
            # the escape hatch without becoming repository exemptions.
            continue
        if not any(item.iter_markers(name="allow_network")):
            continue
        suffix = item.nodeid.partition("::")[2]
        nodeid = relative_path.as_posix()
        if suffix:
            nodeid = f"{nodeid}::{suffix}"
        marked_nodeids.add(nodeid)
    return marked_nodeids


def pytest_collection_modifyitems(items: list[Any]) -> None:
    """Reject checked-in marker usage that lacks a complete audit record."""
    marked_nodeids = _checked_in_allow_network_nodeids(items)
    audited_nodeids = set(AUDITED_ALLOW_NETWORK_EXEMPTIONS)
    if marked_nodeids == audited_nodeids:
        return

    unregistered = sorted(marked_nodeids - audited_nodeids)
    stale = sorted(audited_nodeids - marked_nodeids)
    details: list[str] = []
    if unregistered:
        details.append("未登记 marker: " + ", ".join(unregistered))
    if stale:
        details.append("失效登记: " + ", ".join(stale))
    raise pytest.UsageError("allow_network 豁免审计不一致；" + "；".join(details))


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_protocol(item: Any, nextitem: Any) -> Iterator[None]:
    """Apply marker permission across setup, call and teardown.

    Wrapping the complete protocol means function/class/session fixture setup is
    covered, not only the test body.  Collection/import has no current item and
    remains blocked by the process-wide default.
    """
    allowed = item.get_closest_marker("allow_network") is not None
    with _network_permission(allowed=allowed, nodeid=item.nodeid):
        yield


# Root conftest imports this module before app imports; install immediately so
# test-module collection/import cannot race ahead of pytest_configure.
install()
