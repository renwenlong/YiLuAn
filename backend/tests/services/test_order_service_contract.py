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
