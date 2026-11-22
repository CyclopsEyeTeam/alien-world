"""Load only the frozen source copy, without executing its main or loading state."""
from dataclasses import dataclass
import hashlib
from pathlib import Path
import runpy
EXPECTED='d354b796963cb9c5beaaa682f506fc4364639e5195067150d38cc9a0040b6bab'
@dataclass(frozen=True)
class Frame:
    cells:tuple
    void:tuple

def load_reference():
    path=Path(__file__).with_name('reference')/'aura_hive.py'
    if hashlib.sha256(path.read_bytes()).hexdigest()!=EXPECTED:raise RuntimeError('Frozen Alien source differs from the comparison baseline')
    outer=runpy.run_path(str(path),run_name='isolated_alien_reference')
    return outer['RenderAgent']._frame.__globals__

def capture_cells(ns):
    def capture(rows,void):return Frame(tuple(map(tuple,rows)),void)
    ns['paint']=capture
