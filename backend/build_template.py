"""Inline handler.py into template.yaml so the stack deploys from the console with no packaging step.
Run after editing handler.py:  python build_template.py
"""
from pathlib import Path

here = Path(__file__).parent
code = (here / "handler.py").read_text()
indented = "\n".join(("          " + line) if line.strip() else "" for line in code.splitlines())
src = (here / "template.src.yaml").read_text()
(here / "template.yaml").write_text(src.replace("__HANDLER__", indented))
print("wrote template.yaml")
