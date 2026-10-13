"""The eTIMS invoice domain (KRA Electronic Tax Invoice Management System).

The sales domain records *that* a sale happened; this module records the
compliance document that sale produced. It talks to the tax authority only
through an adapter (``base.py``), and today that adapter records locally and
transmits nothing — see ADR-0019 for what is deliberately not claimed.
"""
