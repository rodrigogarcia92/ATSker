"""The only module that calls a model provider (PRD 5.1).

Nothing else in the tree may import an HTTP client for inference purposes, and
nothing leaves this module without passing through `redaction`.
"""
