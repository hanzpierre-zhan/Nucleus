import sys,runpy
from pathlib import Path
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'scratch/rendicion-test-deps'))
sys.path.append('C:/Users/Hanz/AppData/Local/Temp/nucleus-test-deps')
sys.path.append('C:/Users/Hanz/AppData/Local/Programs/Python/Python314/Lib/site-packages')
sys.path.insert(0,str(root))
if len(sys.argv)>1 and sys.argv[1].endswith('.py'):
    target=sys.argv.pop(1);runpy.run_path(target,run_name='__main__')
else:
    import pytest
    raise SystemExit(pytest.main(sys.argv[1:]))
