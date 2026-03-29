"""Finance services — Contract PDF generation.

Thin wrapper around the top-level contract_generator module.
Blueprint code imports from here instead of the root package.
"""
from contract_generator import generate_contract_pdf  # noqa: F401
