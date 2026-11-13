#!/usr/bin/env python3
"""Fix duplicate results-dir creation introduced by rewire switch patch.

Run from project root: python3 fix_rewire_output_dir.py .
Preserves rewire mode and logs mode settings after run_six.py creates the directory.
"""
from pathlib import Path
import re
import shutil
import subprocess
import sys


def main(root: Path) -> None:
    sh = root / 'run_one_case.sh'
    runner = root / 'tools' / 'run_six.py'
    if not sh.is_file() or not runner.is_file():
        raise RuntimeError('Project must contain run_one_case.sh and tools/run_six.py')
    sh_orig = sh.read_text(encoding='utf-8')
    py_orig = runner.read_text(encoding='utf-8')

    sh_lines = sh_orig.splitlines(keepends=True)
    indexes = [i for i, line in enumerate(sh_lines)
               if line.strip() == 'mkdir -p "$exp_dir"'
               and i + 3 < len(sh_lines)
               and 'rewire_settings.txt' in ''.join(sh_lines[i+1:i+4])]
    if len(indexes) == 1:
        i = indexes[0]
        block = ''.join(sh_lines[i:i+4])
        if (not sh_lines[i+1].lstrip().startswith('printf "mode: %s')
                or '"$REWIRE_MODE"' not in block
                or '"$REWIRE_GAMMA"' not in block
                or '"$REWIRE_RADIUS_CAP"' not in block
                or '> "$exp_dir/rewire_settings.txt"' not in block):
            raise RuntimeError('Found unrecognized output settings block; no files changed')
        del sh_lines[i:i+4]
        sh_new = ''.join(sh_lines)
    elif not indexes:
        sh_new = sh_orig
        print('No duplicated directory-creation block remains in run_one_case.sh')
    else:
        raise RuntimeError('Several matching blocks; no files changed')

    marker = '# REWIRE_OUTPUT_SETTINGS_AFTER_MKDIR'
    if marker in py_orig:
        py_new = py_orig
    else:
        m = re.search(r'(?m)^(?P<indent>[ \t]*)output\.mkdir\(parents=True,\s*exist_ok=False\)[ \t]*(?:#.*)?$', py_orig)
        if not m:
            raise RuntimeError('Could not locate output.mkdir in tools/run_six.py; no files changed')
        indent = m.group('indent')
        code = (
            '\n' + indent + marker + '\n' +
            indent + 'import os as _rewire_os\n' +
            indent + 'if _rewire_os.environ.get("RRT_REWIRE_MODE"):\n' +
            indent + '    (output / "rewire_settings.txt").write_text(\n' +
            indent + '        "mode: {}\\ngamma: {}\\nradius_cap: {}\\n".format(\n' +
            indent + '            _rewire_os.environ.get("RRT_REWIRE_MODE", ""),\n' +
            indent + '            _rewire_os.environ.get("RRT_REWIRE_GAMMA", ""),\n' +
            indent + '            _rewire_os.environ.get("RRT_REWIRE_RADIUS_CAP", ""),\n' +
            indent + '        ), encoding="utf-8")'
        )
        py_new = py_orig[:m.end()] + code + py_orig[m.end():]

    compile(py_new, str(runner), 'exec')
    if sh_new != sh_orig:
        check = subprocess.run(['bash', '-n'], input=sh_new, text=True, capture_output=True)
        if check.returncode:
            raise RuntimeError('Updated shell script failed bash -n: ' + check.stderr)
    updated = []
    for path, orig, new in ((sh, sh_orig, sh_new), (runner, py_orig, py_new)):
        if new != orig:
            backup = path.with_name(path.name + '.bak_before_rewire_output_fix')
            if not backup.exists():
                shutil.copy2(path, backup)
            path.write_text(new, encoding='utf-8')
            updated.append(str(path))
    for path in updated:
        print('Updated:', path)
    if not updated:
        print('Already fixed; no changes made.')
    print('Next: bash -n run_one_case.sh && ./run_one_case.sh')

if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('Usage: python3 fix_rewire_output_dir.py /path/to/project')
    main(Path(sys.argv[1]).expanduser().resolve())
