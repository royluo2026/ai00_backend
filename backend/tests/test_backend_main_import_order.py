from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MAIN_FILE = REPO_ROOT / 'backend' / 'main.py'


def test_backend_main_avoids_module_level_settings_resolution():
    text = MAIN_FILE.read_text(encoding='utf-8')
    assert '_settings = get_settings()' not in text
    assert 'allow_origins=_resolve_cors_allow_origins()' in text
    assert 'from backend.config import get_settings as _gs' in text
