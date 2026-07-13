from pathlib import Path

MAIN_FILE = Path(__file__).resolve().parents[2] / 'backend' / 'main.py'


def test_backend_main_uses_absolute_static_path():
    text = MAIN_FILE.read_text(encoding='utf-8')
    assert 'Path(__file__).parent / "static"' in text
    assert 'StaticFiles(directory=str(_STATIC_DIR), check_dir=False)' in text
