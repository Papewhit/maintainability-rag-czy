"""Document parsing and ingestion helpers.

Layers (top-down):
    parse_adapter — ParseAdapter protocol, DeepDoc + Excel parsers
    normalizer    — structure enrichment (heading tree, lists, figures)
    chunker       — maintainability-aware parent/leaf chunking

The legacy DocumentLoader in loader.py is retained for backward
compatibility and will be deprecated once the new pipeline is complete.
"""
