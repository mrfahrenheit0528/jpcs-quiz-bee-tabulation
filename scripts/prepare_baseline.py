"""Recreate the original implementation with only test DB injection added."""
from pathlib import Path
import io, subprocess, tarfile
root=Path(__file__).resolve().parents[1];target=root/'tmp'/'baseline-app'
target.mkdir(parents=True,exist_ok=True)
data=subprocess.check_output(['git','archive','3225aa2'],cwd=root)
with tarfile.open(fileobj=io.BytesIO(data)) as archive: archive.extractall(target,filter='data')
factory=target/'website'/'__init__.py'
text=factory.read_text().replace('def create_app():','def create_app(config=None):').replace('    db.init_app(app)','    if config: app.config.update(config)\n    db.init_app(app)')
factory.write_text(text)
print('Baseline source:',target)
print('Use QUIZ_BENCH_APP_ROOT='+str(target)+' with scripts/benchmark_lan.py; all benchmark databases are temporary.')
