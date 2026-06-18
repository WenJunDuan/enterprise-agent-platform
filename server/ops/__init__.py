"""Operational layer: runtime diagnostics and maintenance.

These modules orchestrate across stores/platform to report health and run
housekeeping. They sit above stores (which they read) and below routes/app
(which invoke them) — deliberately kept out of ``server.platform`` so the
platform foundation stays a leaf with no upward dependencies.
"""
