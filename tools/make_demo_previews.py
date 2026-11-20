"""Превью для галереи шаблонов МИСИС на нейтральном демо-тексте (без чужих работ и личных данных).

    python tools/make_demo_previews.py

Собирает три демо-отчёта тем же рендером, что и приложение, и кладёт картинки страниц
в library/templates/<шаблон>/previews/. Нужен Word (Windows) или LibreOffice.
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from neondoc.previews import make_previews  # noqa: E402
from reportgen.render import render  # noqa: E402

META = {"student": "Иванов И.И.", "group": "ГРУППА-00-0", "teacher": "Петров П.П.", "date": "______________",
        "year": 2026, "semester": 3, "city": "Москва", "direction": "38.03.05 «Бизнес-информатика»",
        "file_prefix": "Ivanov_GROUP_00_0", "h1_new_page": True}

P = {
    "proc": "Процесс «Приём и обработка заявки» начинается с поступления заявки от клиента и заканчивается "
            "отправкой результата. Владелец процесса — руководитель отдела. В процессе участвуют менеджер, "
            "специалист и руководитель.",
    "why": "Классификация показывает, какие процессы создают ценность для клиента, а какие поддерживают работу "
           "предприятия. Это основа для дальнейшего описания процессов и выбора кандидатов на автоматизацию.",
    "tab": "Состав работ, исполнители и результаты основных процессов приведены ниже ([[table:main]]).",
    "fig": "Общая схема процессов показана на рисунке ([[figure:scheme]]). Стрелки отражают передачу "
           "результата от одного процесса к другому.",
    "after": "Основные процессы связаны последовательно: результат каждого становится входом следующего. "
             "Обеспечивающие процессы поставляют ресурсы, процессы управления задают цели и контроль.",
}
TABLE = {"type": "table", "id": "main", "caption": "Основные бизнес-процессы",
         "columns": ["Бизнес-процесс", "Состав работ", "Исполнитель", "Выход"],
         "rows": [["Приём заявки", "Регистрация заявки, проверка полноты данных", "Менеджер", "Зарегистрированная заявка"],
                  ["Обработка заявки", "Подготовка решения, согласование с клиентом", "Специалист", "Подготовленное решение"],
                  ["Выдача результата", "Передача результата клиенту, закрытие заявки", "Менеджер", "Закрытая заявка"],
                  ["Контроль качества", "Выборочная проверка закрытых заявок", "Руководитель", "Отчёт о качестве"]]}
FIG = {"type": "figure", "id": "scheme", "caption": "Схема бизнес-процессов предприятия"}


def sections():
    return [
        {"title": "Описание процесса", "subsections": [],
         "blocks": [{"type": "paragraph", "text": P["proc"]}, {"type": "paragraph", "text": P["why"]},
                    {"type": "list", "ordered": False, "items": ["менеджер принимает заявку", "специалист готовит решение",
                                                                 "руководитель контролирует качество", "клиент получает результат"]}]},
        {"title": "Классификация бизнес-процессов", "subsections": [],
         "blocks": [{"type": "paragraph", "text": P["tab"]}, TABLE, {"type": "paragraph", "text": P["after"]},
                    {"type": "paragraph", "text": P["fig"]}, FIG]},
        {"title": "Обеспечивающие процессы", "subsections": [],
         "blocks": [{"type": "paragraph", "text": "Обеспечивающие процессы поставляют основным процессам ресурсы: "
                                                  "оборудование, данные, персонал. Их перечень приведён ниже ([[table:support]])."},
                    {"type": "table", "id": "support", "caption": "Обеспечивающие бизнес-процессы",
                     "columns": ["Бизнес-процесс", "Исполнитель", "Выход"],
                     "rows": [["Закупка материалов", "Руководитель", "Материалы на складе"],
                              ["Обслуживание оборудования", "Специалист", "Исправное оборудование"],
                              ["Ведение баз данных", "Менеджер", "Актуальные данные"]]}]},
        {"title": "Процессы управления", "subsections": [],
         "blocks": [{"type": "paragraph", "text": "Процессы управления задают цели, планы и правила, а также контролируют "
                                                  "их выполнение. Ответственный за все процессы управления — руководитель."},
                    {"type": "list", "ordered": True, "items": ["планирование работ на месяц", "контроль сроков обработки заявок",
                                                                "анализ жалоб клиентов", "распределение задач между сотрудниками"]}]},
    ]


def scheme_png(path: Path):
    from PIL import Image, ImageDraw, ImageFont
    im = Image.new("RGB", (1400, 520), "white")
    d = ImageDraw.Draw(im)
    font = None
    for name in ("arial.ttf", "DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        try:
            font = ImageFont.truetype(name, 34)
            break
        except OSError:
            continue
    names = ["Приём", "Обработка", "Выдача", "Контроль"]
    for i, n in enumerate(names):
        x = 60 + i * 340
        d.rectangle([x, 190, x + 250, 330], outline="black", width=4)
        d.text((x + 125, 260), n, fill="black", font=font, anchor="mm" if font else None)
        if i < len(names) - 1:
            d.line([x + 250, 260, x + 340, 260], fill="black", width=4)
            d.polygon([(x + 340, 260), (x + 322, 250), (x + 322, 270)], fill="black")
    im.save(path)


DEMOS = {
    "tipup-lr": {"meta": {"work_type": "Лабораторная работа", "number": "2", "discipline": "ТИПУП",
                          "module": "модуль «Моделирование бизнес-процессов»",
                          "topic": "Классификация бизнес-процессов", "file_code": "TIPUP",
                          "toc": False, "intro": False, "conclusion": "ВЫВОДЫ"},
                 "intro": [], "sources": []},
    "misis-pr": {"meta": {"work_type": "Практическая работа", "number": "1", "discipline": "Название дисциплины",
                          "module": None, "topic": "Классификация бизнес-процессов предприятия", "file_code": "DISC",
                          "toc": True, "intro": True, "conclusion": "ЗАКЛЮЧЕНИЕ"},
                 "intro": [P["why"], "Цель работы — классифицировать бизнес-процессы демонстрационного предприятия.",
                           "Задачи: описать процесс; выделить группы процессов; определить состав работ и исполнителей."],
                 "sources": ["Фамилия И. О. Название учебника. — М.: Издательство, 2024. — 300 с.",
                             "ГОСТ 7.32-2017. Отчёт о научно-исследовательской работе. Структура и правила оформления."]},
    "misis-referat": {"meta": {"work_type": "Реферат", "number": "", "discipline": "Название дисциплины", "module": None,
                               "topic": "Тема реферата", "file_code": "DISC", "toc": True, "intro": True,
                               "conclusion": "ЗАКЛЮЧЕНИЕ"},
                      "intro": [P["why"], "Цель реферата — рассмотреть тему по источникам и сформулировать собственную позицию.",
                                "Задачи: изучить источники; сравнить подходы; сделать выводы."],
                      "sources": ["Фамилия И. О. Название книги. — М.: Издательство, 2023. — 250 с.",
                                  "Фамилия И. О. Название статьи // Журнал. — 2025. — № 1. — С. 10–20."]},
}
CONCLUSION = ["В работе описан процесс и выделены основные, обеспечивающие и управленческие бизнес-процессы.",
              "Для основных процессов определены состав работ, исполнители и результаты."]


def main():
    for slug, demo in DEMOS.items():
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "figures").mkdir()
            scheme_png(tmp / "figures" / "scheme.png")
            rep = {"meta": {**META, **demo["meta"]}, "goal": "классифицировать бизнес-процессы демонстрационного предприятия",
                   "intro": demo["intro"], "sections": sections(), "conclusion": CONCLUSION, "sources": demo["sources"]}
            (tmp / "report.json").write_text(json.dumps(rep, ensure_ascii=False), encoding="utf-8")
            docx_path, _ = render(tmp / "report.json")
            dest = ROOT / "library" / "templates" / slug / "previews"
            shutil.rmtree(dest, ignore_errors=True)
            pages = make_previews(docx_path, dest, max_pages=6)
            print(f"{slug}: {len(pages)} стр.")


if __name__ == "__main__":
    main()
