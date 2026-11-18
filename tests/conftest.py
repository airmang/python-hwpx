"""Test-session settings shared by every test module."""
from __future__ import annotations

import os

# Many tests run a repository script, a probe or a manual example in a child Python and read what it prints
# (Korean text among it) as UTF-8 (``subprocess.run(..., encoding="utf-8")``). A child writes to a pipe in its
# locale's encoding unless told otherwise -- cp1252 on an English Windows, where Korean cannot be written at
# all. So the harness tells its children which encoding it reads. This touches only the children's standard
# streams; files the engine reads and writes name their encoding themselves (tests/test_text_encoding.py).
os.environ["PYTHONIOENCODING"] = "utf-8"
