#!/usr/bin/env python3
"""Optional FAT12 disk builder. MAKE.BAT never invokes this script."""
from pathlib import Path
import subprocess
import sys

root=Path(__file__).resolve().parents[1]
dist=root/'dist'
dist.mkdir(exist_ok=True)
cmd=[sys.executable,str(root/'tools'/'pack_app360.py'),
    '--binary',str(dist/'2BASIC.O88'),
    '--bres-binary',str(dist/'2BRES.O88'),
    '--cards',str(root/'resources'/'cards'),
    '--bres-demo',str(root/'resources'/'2bres-demo'),
    '--samples',str(root/'samples'),
    '--output',str(dist/'2BASIC-APPS360.IMG')]
subprocess.run(cmd,check=True)
subprocess.run([sys.executable,str(root/'tools'/'verify_release.py')],check=True)
print('DISK PASSED: dist/2BASIC-APPS360.IMG')
