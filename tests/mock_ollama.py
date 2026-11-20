"""Поддельный Ollama для проверки конвейера без GPU: отдаёт заготовленные ответы,
первый ответ на раздел 2 — с ошибкой, чтобы проверить цикл исправления."""
import json
from http.server import BaseHTTPRequestHandler, HTTPServer

OUTLINE = {"goal": "построить функциональную модель бизнес-процесса ООО «Барбершоп 4» в нотации IDEF0",
           "sections": [
               {"title": "Описание бизнес-процесса", "purpose": "какой процесс моделируется", "tables": [], "figures": []},
               {"title": "Контекстная диаграмма A-0", "purpose": "граница процесса", "tables": ["граничные стрелки"], "figures": ["диаграмма A-0"]}]}
S1 = {"title": "Описание бизнес-процесса", "subsections": [], "blocks": [
    {"type": "paragraph", "text": "Для моделирования взят процесс «Запись и обслуживание клиента». Отвечает за процесс владелец барбершопа."}]}
S2_BAD = {"title": "Контекстная диаграмма A-0", "subsections": [], "blocks": [
    {"type": "paragraph", "text": "Контекстная диаграмма показывает процесс одним блоком (Таблица 1)."},
    {"type": "table", "id": "arrows_a0", "caption": "Граничные стрелки", "columns": ["Тип стрелки", "Наименование"],
     "rows": [["Вход", "Запись к барберу"], ["Выход"]]},
    {"type": "figure", "id": "ctx_a0", "caption": "Контекстная диаграмма A-0"}]}
S2_OK = {"title": "Контекстная диаграмма A-0", "subsections": [], "blocks": [
    {"type": "paragraph", "text": "Контекстная диаграмма показывает процесс одним блоком. Граничные стрелки перечислены ниже ([[table:arrows_a0]])."},
    {"type": "table", "id": "arrows_a0", "caption": "Граничные стрелки", "columns": ["Тип стрелки", "Наименование"],
     "rows": [["Вход", "Запись к барберу"], ["Выход", "Кассовый чек"]]},
    {"type": "paragraph", "text": "Сама диаграмма приведена ниже ([[figure:ctx_a0]]). [уточнить: кто владелец модели]"},
    {"type": "figure", "id": "ctx_a0", "caption": "Контекстная диаграмма A-0"}]}
CONCL = {"paragraphs": ["Функциональная модель процесса построена в нотации IDEF0.", "Модель согласована с EPC-схемой."]}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _send(self, obj):
        b = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        self._send({"models": [{"name": "qwen3.6:27b"}]})

    def do_POST(self):
        req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if "format" not in req:   # свободный чат: потоковый ответ построчно
            body = "".join(json.dumps({"message": {"content": w + " "}, "done": False}, ensure_ascii=False) + "\n"
                           for w in "Привет! Это **тестовый** ответ.\n\n- пункт один\n- пункт два".split(" "))
            body += json.dumps({"done": True}) + "\n"
            b = body.encode()
            self.send_response(200); self.send_header("Content-Type", "application/x-ndjson")
            self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
            return
        props = req["format"]["properties"]
        last = req["messages"][-1]["content"]
        assert req["think"] is False and req["options"]["temperature"] == 0
        if "goal" in props:
            out = OUTLINE
        elif "paragraphs" in props:
            out = CONCL
        elif "Напиши раздел 1" in last:
            out = S1
        elif "Проверка нашла ошибки" in last:
            out = S2_OK
        else:
            out = S2_BAD
        self._send({"message": {"content": json.dumps(out, ensure_ascii=False)},
                    "prompt_eval_count": 1500, "eval_count": 400, "total_duration": 9_000_000_000})


HTTPServer(("127.0.0.1", 11555), H).serve_forever()
