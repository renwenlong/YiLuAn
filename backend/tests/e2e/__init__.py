"""End-to-end test package.

These tests hit real external services (WeChat Pay, Aliyun SMS, etc.)
and are skipped by default. Each module guards its tests behind an
environment variable so CI stays green until the corresponding Blocker
is unblocked.
"""
