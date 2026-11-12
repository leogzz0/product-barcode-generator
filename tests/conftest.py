from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def write_csv(tmp_path):
    def _write(text: str, name: str = "products.csv", encoding: str = "utf-8") -> Path:
        path = tmp_path / name
        path.write_bytes(text.encode(encoding))
        return path

    return _write


@pytest.fixture
def sample_csv() -> Path:
    return ROOT / "products.csv"
