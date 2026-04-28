"""Observability primitives (Prometheus metrics, etc.).

Domain-specific metrics live in submodules so producers (cron tasks,
service-layer hooks) can import without dragging unrelated counters into
the import graph.
"""
