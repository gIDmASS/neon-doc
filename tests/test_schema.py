"""Схема для Ollama должна сохранять все поля моделей (баг 09.11: пропадало поле title)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from reportgen.schema import Outline, Section, TextPart, ollama_schema  # noqa: E402


def fields(schema):
    found = set()
    def walk(n):
        if isinstance(n, dict):
            found.update(n.get("properties", {}).keys())
            for v in n.values():
                walk(v)
        elif isinstance(n, list):
            for v in n:
                walk(v)
    walk(schema)
    return found


for model, expected in [(Outline, {"goal", "sections", "title", "purpose", "tables", "figures"}),
                        (Section, {"title", "blocks", "subsections", "type", "text", "id", "caption",
                                   "columns", "rows", "items", "ordered"}),
                        (TextPart, {"paragraphs"})]:
    got = fields(ollama_schema(model))
    missing = expected - got
    assert not missing, f"{model.__name__}: пропали поля {missing}"
    print(f"{model.__name__}: OK")
