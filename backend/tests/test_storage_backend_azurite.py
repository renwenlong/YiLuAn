"""Azurite integration tests for AzureBlobStorageBackend real-SDK mode.

S2-DEV-016-PHASE-B-PREFLIGHT-SDK AC#2 / AC#3.

These exercise the **real azure-storage-blob SDK path** against a local
azurite emulator (no 21Vianet creds needed). They are marked
``@pytest.mark.azurite`` and excluded from the default test run
(``addopts = -m 'not smoke and not docker and not azurite'``) because they
require a running azurite container.

Run locally / in the dedicated CI job:

    docker run -d --name azurite -p 10000:10000 \\
        mcr.microsoft.com/azure-storage/azurite azurite-blob --blobHost 0.0.0.0
    pytest -m azurite

If azurite is unreachable the module-level fixture skips (does not fail), so
a normal ``pytest`` invocation that somehow selects these never hard-fails on
a dev box without azurite.

WORM (AC#4) is NOT tested here: azurite does not support immutability
(Azure/Azurite Issue #2648); WORM enforcement is verified by the REAL task
smoke after creds land. See ``test_storage_backend.py`` for the skip-marked
WORM unit test.
"""
from __future__ import annotations

import uuid

import pytest

from app.services.storage_backend import (
    AzureBlobStorageBackend,
    StoredObject,
)

pytestmark = pytest.mark.azurite

# azurite well-known dev account (https://learn.microsoft.com/azure/storage/common/storage-use-azurite)
_AZURITE_CONN = (
    "DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;"
    "AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuF"
    "q2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;"
    "BlobEndpoint=http://127.0.0.1:10000/devstoreaccount1;"
)
_ACCOUNT = "devstoreaccount1"


@pytest.fixture(scope="module")
def azurite_client():
    """Connect to a running azurite; skip the whole module if unreachable."""
    try:
        from azure.storage.blob import BlobServiceClient
    except ImportError:  # pragma: no cover
        pytest.skip("azure-storage-blob not installed")

    svc = BlobServiceClient.from_connection_string(_AZURITE_CONN)
    try:
        # cheap reachability probe
        next(iter(svc.list_containers(results_per_page=1).by_page()), None)
    except Exception as exc:  # azurite not up
        pytest.skip(f"azurite unreachable on :10000 ({type(exc).__name__}: {exc})")
    return svc


@pytest.fixture
def backend(azurite_client):
    """Fresh container per test for isolation; real-SDK backend."""
    container = f"yiluan-test-{uuid.uuid4().hex[:12]}"
    azurite_client.create_container(container)
    be = AzureBlobStorageBackend(
        account_name=_ACCOUNT,
        container_name=container,
        blob_service_client=azurite_client,
    )
    assert be.is_real_sdk is True
    yield be
    try:
        azurite_client.delete_container(container)
    except Exception:
        pass


# ---------- AC#2 upload / download round-trip ----------


def test_put_and_open_round_trip(backend):
    obj = backend.put("cert/a.jpg", b"hello-azure-blob", content_type="image/jpeg")
    assert obj.uri == "azure-blob://cert/a.jpg"
    assert backend.open(obj) == b"hello-azure-blob"


def test_open_missing_raises_not_found(backend):
    from app.exceptions import NotFoundException

    with pytest.raises(NotFoundException):
        backend.open(StoredObject(scheme=backend.scheme, key="cert/missing.jpg"))


def test_put_overwrites(backend):
    backend.put("cert/b.jpg", b"v1", content_type="image/jpeg")
    backend.put("cert/b.jpg", b"v2", content_type="image/jpeg")
    assert backend.open(StoredObject(scheme=backend.scheme, key="cert/b.jpg")) == b"v2"


# ---------- AC#2 put_if_absent (If-None-Match: *) ----------


def test_put_if_absent_new(backend):
    r = backend.put_if_absent("cert/c.jpg", b"first", content_type="image/jpeg")
    assert r.already_exists is False
    assert backend.open(r.stored) == b"first"


def test_put_if_absent_existing_does_not_overwrite(backend):
    backend.put_if_absent("cert/d.jpg", b"first", content_type="image/jpeg")
    r2 = backend.put_if_absent("cert/d.jpg", b"second", content_type="image/jpeg")
    assert r2.already_exists is True
    # content preserved (idempotent WORM write)
    assert backend.open(StoredObject(scheme=backend.scheme, key="cert/d.jpg")) == b"first"


# ---------- AC#3 User Delegation SAS ----------


def test_sign_read_url_generates_sas(backend, monkeypatch):
    """azurite supports SAS; assert a real SAS URL is generated.

    azurite's ``get_user_delegation_key`` support varies by version; if the
    running azurite rejects delegation-key issuance we skip rather than fail,
    since SAS generation against real Azure is covered by the REAL smoke.
    """
    backend.put("cert/e.jpg", b"sas-body", content_type="image/jpeg")
    obj = StoredObject(scheme=backend.scheme, key="cert/e.jpg")
    try:
        signed = backend.sign_read_url(obj, ttl_seconds=300)
    except Exception as exc:  # azurite delegation-key gap
        pytest.skip(f"azurite delegation key unsupported ({type(exc).__name__})")
    assert signed.url.startswith(
        f"https://{_ACCOUNT}.blob.core.chinacloudapi.cn/{backend.container_name}/cert/e.jpg?"
    )
    # SAS query carries a signature + expiry
    assert "sig=" in signed.url
    assert "se=" in signed.url or "se%3D" in signed.url
