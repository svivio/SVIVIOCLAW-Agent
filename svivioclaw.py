#!/usr/bin/env python3
"""SVIVIOCLAW — Entry point alias (delegates to guioc.py)."""
import runpy, sys
sys.argv[0] = "svivioclaw"
runpy.run_module("guioc", run_name="__main__", alter_sys=True)
