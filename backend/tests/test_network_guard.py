"""Regression probes for the process-wide outbound-network guard."""

from __future__ import annotations

import ast
import socket
import subprocess
import sys
import threading
from pathlib import Path

import httpx
import pytest

from tests import network_guard
from tests.network_guard import OutboundNetworkBlockedError

_BLOCKED_TARGET = ("192.0.2.1", 9)  # RFC 5737 TEST-NET-1; never a production API.
_EXPECTED_MESSAGE = "该用例需 mock 外部调用"
_AUDITED_ALLOW_NETWORK_EXEMPTIONS: set[str] = set()


def test_function_body_external_tcp_is_blocked():
    with pytest.raises(OutboundNetworkBlockedError, match=_EXPECTED_MESSAGE):
        socket.create_connection(_BLOCKED_TARGET, timeout=0.01)


@pytest.mark.parametrize("method_name", ["connect", "connect_ex"])
def test_direct_socket_entry_points_are_blocked(method_name):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
        with pytest.raises(OutboundNetworkBlockedError, match=_EXPECTED_MESSAGE):
            getattr(client, method_name)(_BLOCKED_TARGET)


def test_connectionless_udp_entry_point_is_blocked():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
        with pytest.raises(OutboundNetworkBlockedError, match=_EXPECTED_MESSAGE):
            client.sendto(b"controlled-probe", _BLOCKED_TARGET)


@pytest.mark.parametrize(
    "resolve",
    [
        lambda: socket.getaddrinfo("network-guard-probe.invalid", 443),
        lambda: socket.gethostbyname("network-guard-probe.invalid"),
        lambda: socket.gethostbyname_ex("network-guard-probe.invalid"),
        lambda: socket.gethostbyaddr("192.0.2.1"),
        lambda: socket.getnameinfo(("192.0.2.1", 443), 0),
    ],
    ids=["getaddrinfo", "gethostbyname", "gethostbyname-ex", "gethostbyaddr", "getnameinfo"],
)
def test_external_dns_is_blocked_before_resolution(resolve):
    with pytest.raises(OutboundNetworkBlockedError, match=_EXPECTED_MESSAGE):
        resolve()


def test_external_dns_probe_is_non_vacuous_when_guard_is_disabled():
    """The same reserved-domain probe reaches the real resolver without guard."""
    with network_guard._network_permission(allowed=True, nodeid="negative-control"):
        with pytest.raises(socket.gaierror):
            socket.getaddrinfo("network-guard-probe.invalid", 443)

    with pytest.raises(OutboundNetworkBlockedError, match=_EXPECTED_MESSAGE):
        socket.getaddrinfo("network-guard-probe.invalid", 443)


@pytest.mark.parametrize(
    ("family", "bind_address", "connect_address"),
    [
        (socket.AF_INET, ("127.0.0.1", 0), lambda port: ("localhost", port)),
        (socket.AF_INET, ("127.0.0.1", 0), lambda port: ("127.0.0.1", port)),
        (socket.AF_INET6, ("::1", 0), lambda port: ("::1", port)),
    ],
    ids=["localhost-hostname", "loopback-ipv4", "loopback-ipv6"],
)
def test_loopback_tcp_is_allowed(family, bind_address, connect_address):
    with socket.socket(family, socket.SOCK_STREAM) as listener:
        listener.bind(bind_address)
        listener.listen(1)
        port = listener.getsockname()[1]
        with socket.create_connection(connect_address(port), timeout=1):
            pass


def _run_isolated_pytest(tmp_path: Path, source: str) -> subprocess.CompletedProcess[str]:
    probe = tmp_path / "test_probe.py"
    probe.write_text(source, encoding="utf-8")
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "tests.network_guard",
            "--rootdir",
            str(tmp_path),
            "-q",
            str(probe),
        ],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )


def test_module_import_external_tcp_is_blocked(tmp_path):
    result = _run_isolated_pytest(
        tmp_path,
        """\
import socket
socket.create_connection((\"192.0.2.1\", 9), timeout=0.01)

def test_never_collected():
    assert False
""",
    )

    assert result.returncode != 0
    assert _EXPECTED_MESSAGE in result.stdout + result.stderr
    assert "collection/import" in result.stdout + result.stderr


def test_session_fixture_external_tcp_is_blocked(tmp_path):
    result = _run_isolated_pytest(
        tmp_path,
        """\
import socket
import pytest

@pytest.fixture(scope=\"session\")
def external_session_fixture():
    socket.create_connection((\"192.0.2.1\", 9), timeout=0.01)


def test_fixture_probe(external_session_fixture):
    assert False
""",
    )

    assert result.returncode != 0
    assert _EXPECTED_MESSAGE in result.stdout + result.stderr
    assert "test_fixture_probe" in result.stdout + result.stderr


def test_fixture_teardown_external_tcp_is_blocked(tmp_path):
    result = _run_isolated_pytest(
        tmp_path,
        """\
import socket
import pytest

@pytest.fixture
def teardown_probe():
    yield
    socket.create_connection(("192.0.2.1", 9), timeout=0.01)


def test_fixture_probe(teardown_probe):
    pass
""",
    )

    assert result.returncode != 0
    assert _EXPECTED_MESSAGE in result.stdout + result.stderr
    assert "test_fixture_probe" in result.stdout + result.stderr


def test_allow_network_marker_enables_only_the_generated_probe(tmp_path):
    result = _run_isolated_pytest(
        tmp_path,
        """\
import socket
import pytest

@pytest.mark.allow_network
def test_explicit_escape_hatch():
    with pytest.raises(socket.gaierror):
        socket.getaddrinfo(\"network-guard-probe.invalid\", 443)
""",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "1 passed" in result.stdout


def test_httpx_request_construction_does_not_open_a_connection():
    request = httpx.Request("POST", "https://api.mch.weixin.qq.com/v3/pay/probe")
    assert request.method == "POST"
    assert request.url.host == "api.mch.weixin.qq.com"


def test_curl_subprocess_boundary_is_explicit_and_loopback_still_works():
    """The Python monkeypatch does not cross exec; prove and document that edge.

    The child curl is intentionally limited to loopback. A separate AST guard
    below rejects checked-in subprocess commands containing external URLs.
    """
    response = b"HTTP/1.1 204 No Content\r\nContent-Length: 0\r\n\r\n"
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        port = listener.getsockname()[1]

        def serve_once() -> None:
            conn, _ = listener.accept()
            with conn:
                conn.recv(4096)
                conn.sendall(response)

        server = threading.Thread(target=serve_once, daemon=True)
        server.start()
        result = subprocess.run(
            ["curl", "--fail", "--silent", f"http://127.0.0.1:{port}/probe"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        server.join(timeout=2)

    assert result.returncode == 0, result.stderr


def _is_allow_network_marker(node: ast.expr) -> bool:
    if isinstance(node, ast.Call):
        node = node.func
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "allow_network"
        and isinstance(node.value, ast.Attribute)
        and node.value.attr == "mark"
        and isinstance(node.value.value, ast.Name)
        and node.value.value.id == "pytest"
    )


def test_checked_in_allow_network_markers_match_audited_registry():
    tests_root = Path(__file__).resolve().parent
    marked_nodeids: set[str] = set()
    for path in tests_root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if any(_is_allow_network_marker(marker) for marker in node.decorator_list):
                marked_nodeids.add(f"{path.relative_to(tests_root)}::{node.name}")

    assert marked_nodeids == _AUDITED_ALLOW_NETWORK_EXEMPTIONS


def _string_literals(node: ast.AST) -> list[str]:
    return [
        child.value
        for child in ast.walk(node)
        if isinstance(child, ast.Constant) and isinstance(child.value, str)
    ]


def test_no_external_url_or_curl_in_test_subprocess_commands():
    """Static proof for the subprocess boundary documented by AC#7.

    Python monkeypatches cannot govern arbitrary child processes. Fail if the
    current test tree checks in an obvious subprocess curl/wget or external URL;
    dynamically built child-network commands remain a documented review risk.
    """
    tests_root = Path(__file__).resolve().parent
    violations: list[str] = []
    subprocess_methods = {"run", "Popen", "call", "check_call", "check_output"}

    for path in tests_root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for call in (node for node in ast.walk(tree) if isinstance(node, ast.Call)):
            func = call.func
            if not isinstance(func, ast.Attribute) or func.attr not in subprocess_methods:
                continue
            if not isinstance(func.value, ast.Name) or func.value.id != "subprocess":
                continue
            literals = " ".join(_string_literals(call)).lower()
            has_network_tool = "curl" in literals or "wget" in literals
            has_url = "http://" in literals or "https://" in literals
            has_loopback_url = has_url and any(
                host in literals for host in ("localhost", "127.0.0.1", "[::1]")
            )
            has_external_url = has_url and not has_loopback_url
            has_dynamic_network_target = has_network_tool and not has_url
            if has_external_url or has_dynamic_network_target:
                violations.append(f"{path.relative_to(tests_root)}:{call.lineno}")

    assert violations == [], "发现可能绕过 Python guard 的子进程外呼: " + ", ".join(violations)
