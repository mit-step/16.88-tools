"""Load legacy engines by unique names, without starting their HTTP servers."""
import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent


def load(name, path):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


load('pdr_tool', ROOT / 'PDR Evaluation Tool' / 'pdr_tool.py')
load('cdr_tool', ROOT / 'CDR Evaluation Tool' / 'cdr_tool.py')
pdr = load('suite_pdr_workspace', ROOT / 'PDR Evaluation Tool' / 'workspace_app.py')
cdr = load('suite_cdr_workspace', ROOT / 'CDR Evaluation Tool' / 'workspace_app.py')
esdp = load('esdp_review', ROOT / 'ESDP Evaluation Tool' / 'esdp_review.py')
