"""SP-01 contract test: OrderService split must preserve external surface.

Pinned via TDD before splitting `app/services/order.py` into a package.
Any future refactor that breaks these invariants will fail loudly.
"""
import inspect
import logging

import pytest



def test_top_level_module_reexports_public_surface():
    """`app.services.order` (whether file or package) must re-export every
    symbol the rest of the codebase / tests reach into via patch().
    """
    import app.services.order as mod

    # Constants & helpers used by tests/unit/test_decimal_money.py and others
    assert hasattr(mod, "SERVICE_PRICES"), "SERVICE_PRICES must remain top-level"
    assert hasattr(mod, "generate_order_number"), "generate_order_number must remain importable"
    assert hasattr(mod, "ORDER_EXPIRY_HOURS")

    # `app.services.order.logger` is patched by tests/test_orders.py
    assert hasattr(mod, "logger"), "module-level logger must remain (test patch target)"
    assert isinstance(mod.logger, logging.Logger)

    # `app.services.order.PaymentService` is patched by tests/test_orders.py
    assert hasattr(mod, "PaymentService"), "PaymentService re-export required for patch path"

    # OrderService class must remain importable from same path
    assert hasattr(mod, "OrderService")


def test_order_service_method_surface_unchanged():
    """The full public API of OrderService must remain intact."""
    from app.services.order import OrderService

    expected_public_methods = {
        "create_order",
        "get_order",
        "list_orders",
        "accept_order",
        "start_order",
        "request_start_service",
        "confirm_start_service",
        "complete_order",
        "cancel_order",
        "pay_order",
        "refund_order",
        "reject_order",
        "check_expired_orders",
    }
    actual = {
        name
        for name, _ in inspect.getmembers(OrderService, predicate=inspect.isfunction)
        if not name.startswith("_")
    }
    missing = expected_public_methods - actual
    assert not missing, f"OrderService missing methods after refactor: {missing}"


def test_order_service_private_helpers_preserved():
    """Helpers used across mixins must still exist on the composed class."""
    from app.services.order import OrderService

    for name in (
        "_get_order_or_404",
        "_get_order_for_update_or_404",
        "_validate_transition",
        "_record_history",
        "_fill_payment_status",
        "_fill_timeline",
    ):
        assert hasattr(OrderService, name), f"OrderService missing helper {name}"


def test_order_service_constructor_attributes():
    """Constructor must wire the same set of repo / service attributes."""
    from unittest.mock import MagicMock

    from app.services.order import OrderService

    svc = OrderService(MagicMock())
    for attr in (
        "order_repo",
        "hospital_repo",
        "payment_repo",
        "history_repo",
        "companion_repo",
        "notification_svc",
        "payment_svc",
        "chat_repo",
        "session",
    ):
        assert hasattr(svc, attr), f"OrderService.__init__ must set {attr}"


def test_order_service_mro_includes_all_mixins():
    """OrderService MRO must include every mixin + base + object, in order.

    Guards against a future refactor that drops a mixin from the inheritance
    chain (which would silently lose methods).
    """
    from app.services.order import OrderService
    from app.services.order._base import _OrderServiceBase
    from app.services.order.cancel import _OrderCancelMixin
    from app.services.order.expiry import _OrderExpiryMixin
    from app.services.order.lifecycle import _OrderLifecycleMixin
    from app.services.order.payment import _OrderPaymentMixin
    from app.services.order.query import _OrderQueryMixin

    mro = OrderService.__mro__
    expected = {
        _OrderQueryMixin,
        _OrderLifecycleMixin,
        _OrderCancelMixin,
        _OrderPaymentMixin,
        _OrderExpiryMixin,
        _OrderServiceBase,
        object,
    }
    assert expected.issubset(set(mro)), (
        f"OrderService MRO missing classes: {expected - set(mro)}"
    )
    # Sanity: object is always last
    assert mro[-1] is object


def test_mixins_have_no_method_name_conflicts():
    """Each mixin's own public methods must not collide with another mixin's.

    Conflicts would cause MRO order to silently change which implementation
    wins. Currently the mixins are non-overlapping by design (cancel.py
    docstring promises this); this test enforces it.
    """
    from app.services.order.cancel import _OrderCancelMixin
    from app.services.order.expiry import _OrderExpiryMixin
    from app.services.order.lifecycle import _OrderLifecycleMixin
    from app.services.order.payment import _OrderPaymentMixin
    from app.services.order.query import _OrderQueryMixin

    mixins = {
        "query": _OrderQueryMixin,
        "lifecycle": _OrderLifecycleMixin,
        "cancel": _OrderCancelMixin,
        "payment": _OrderPaymentMixin,
        "expiry": _OrderExpiryMixin,
    }

    def own_methods(cls):
        return {
            name
            for name, _ in inspect.getmembers(cls, predicate=inspect.isfunction)
            if not name.startswith("_") and name in cls.__dict__
        }

    method_owners: dict[str, str] = {}
    conflicts: list[str] = []
    for owner, cls in mixins.items():
        for m in own_methods(cls):
            if m in method_owners:
                conflicts.append(
                    f"{m}: {method_owners[m]} vs {owner}"
                )
            method_owners[m] = owner
    assert not conflicts, f"Mixin method name conflicts: {conflicts}"


def test_submodules_importable_in_isolation():
    """Each submodule must be importable on its own without relying on the
    package being already imported (regression guard for the old
    `sys.modules['app.services.order'].logger` hack).
    """
    import importlib
    import sys

    for mod_name in (
        "app.services.order.cancel",
        "app.services.order.expiry",
        "app.services.order.lifecycle",
        "app.services.order.payment",
        "app.services.order.query",
        "app.services.order._base",
    ):
        sys.modules.pop(mod_name, None)
    sys.modules.pop("app.services.order", None)

    # Import a leaf first; importing the package implicitly is fine,
    # but the leaf must not raise KeyError on a missing parent attr.
    cancel = importlib.import_module("app.services.order.cancel")
    assert hasattr(cancel, "_OrderCancelMixin")


def test_logger_patch_path_still_works():
    """`patch("app.services.order.logger")` must affect logger calls made
    through `self.logger` from any mixin (regression guard).
    """
    from unittest.mock import MagicMock, patch

    from app.services.order import OrderService

    svc = OrderService(MagicMock())
    with patch("app.services.order.logger") as mock_logger:
        svc.logger.info("hello")
        mock_logger.info.assert_called_once_with("hello")
