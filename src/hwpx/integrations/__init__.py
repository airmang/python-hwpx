# SPDX-License-Identifier: Apache-2.0
"""Thin adapters that hand python-hwpx output to other Python frameworks.

Each adapter lives in its own submodule and imports its framework there, so
nothing here loads unless you import that submodule, and each has its own
optional extra (``pip install "python-hwpx[langchain]"``).
"""
