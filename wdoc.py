"""Рабочие документы из командной строки (то же, что вкладка «Работа» в приложении).

  python wdoc.py templates                         — список шаблонов
  python wdoc.py list                              — список документов
  python wdoc.py new robot-desc "Сверка платежей" code=ROBOT0001 name="Сверка платежей"
  python wdoc.py add <id> файл1 файл2 …            — приложить материалы
  python wdoc.py fill <id> [раздел …]              — заполнить через Qwen (все или указанные)
  python wdoc.py check <id>                        — проверка по требованиям + вопросы к заказчику
  python wdoc.py build <id> [docx|pdf|txt|confluence]
"""
import sys
from pathlib import Path

from neondoc import wdocs, wdocs_render


class _Job:
    def emit(self, s): print(s)
    def stop_requested(self): return False


def main(a):
    if not a or a[0] in ("-h", "--help"):
        return print(__doc__)
    cmd = a[0]
    if cmd == "templates":
        for t in wdocs.list_templates():
            print(f"{t['slug']:16} {t['name']}  ({len(t['sections'])} разделов)")
    elif cmd == "list":
        for d in wdocs.list_all():
            print(f"{d['id']}  {d['title']}  [{d['template']}]  {d['filled']}/{d['total']}")
    elif cmd == "new":
        fields = dict(x.split("=", 1) for x in a[3:])
        print(wdocs.create(a[1], a[2] if len(a) > 2 else "", fields))
    elif cmd == "add":
        for f in a[2:]:
            print("+", wdocs.add_material_path(a[1], Path(f)))
    elif cmd == "fill":
        from neondoc.server import settings
        settings()
        wdocs.generate(a[1], a[2:] or None, _Job())
    elif cmd == "check":
        for x in wdocs.check(a[1]):
            print(f"[{x['level']}] {x['section']}: {x['msg']}")
        print()
        print(wdocs.questions_text(a[1]))
    elif cmd == "build":
        r = wdocs_render.build(a[1], a[2] if len(a) > 2 else "docx", print)
        print(r["path"])
        for w in r["warnings"]:
            print("!", w)
    else:
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
