"""Конвейер: задание -> план -> разделы -> report.json -> .docx

Используется и из командной строки, и из приложения (через emit — колбэк прогресса).

Папка задания (например tasks\\tipup_lr6):
    task.yaml    — титул и параметры (Meta) + необязательные: roles, fixed_sections, prompt_hints
    brief.md     — текст задания из методички + факты о предприятии
    sources.txt  — список источников, по одному в строке (необязательно; модель их не придумывает)
    figures\\     — PNG из draw.io, имя файла = id рисунка

Команды:
    python -m reportgen.pipeline plan   tasks\\tipup_lr6   # шаг 1: outline.json — проверь и поправь руками
    python -m reportgen.pipeline write  tasks\\tipup_lr6   # шаг 2: разделы по плану -> report.json -> .docx
    python -m reportgen.pipeline render tasks\\tipup_lr6   # шаг 3: report.json -> .docx (без модели)
    python -m reportgen.pipeline all    tasks\\tipup_lr6   # всё подряд, без остановки на плане

Журнал вызовов (время, токены, попытки) пишется в run_log.jsonl — это твои цифры «до/после».
"""
from __future__ import annotations

import json
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import yaml
from pydantic import BaseModel

from . import llm
from .render import render
from .schema import Meta, Outline, PlannedSection, Report, Section, TextPart
from .validate import Result, check_outline, check_section, check_text_part

ROOT = Path(__file__).resolve().parent.parent
SYSTEM = (ROOT / "prompts" / "system.md").read_text(encoding="utf-8")

Emit = Callable[[str], None]


class PipelineError(RuntimeError):
    pass


class Stopped(PipelineError):
    pass


class Goal(BaseModel):
    goal: str


@dataclass
class TaskConfig:
    meta: Meta
    brief: str
    roles: list[str] = field(default_factory=list)
    fixed_sections: list[PlannedSection] = field(default_factory=list)
    prompt_hints: str = ""
    sources: list[str] = field(default_factory=list)


def load_task(task: Path) -> TaskConfig:
    raw = yaml.safe_load((task / "task.yaml").read_text(encoding="utf-8")) or {}
    brief = (task / "brief.md").read_text(encoding="utf-8") if (task / "brief.md").exists() else ""
    brief = re.sub(r"<!--.*?-->", "", brief, flags=re.S).strip()  # комментарии — для тебя, не для модели
    src_file = task / "sources.txt"
    sources = [s.strip() for s in src_file.read_text(encoding="utf-8").splitlines() if s.strip()] \
        if src_file.exists() else []
    return TaskConfig(
        meta=Meta(**{k: v for k, v in raw.items() if k in Meta.model_fields}),
        brief=brief,
        roles=[r.strip() for r in raw.get("roles") or [] if str(r).strip()],
        fixed_sections=[PlannedSection(**s) for s in raw.get("fixed_sections") or []],
        prompt_hints=(raw.get("prompt_hints") or "").strip(),
        sources=sources,
    )


def _system(cfg: TaskConfig) -> str:
    s = SYSTEM
    if cfg.prompt_hints:
        s += "\nОсобенности этого типа работы:\n" + cfg.prompt_hints + "\n"
    if cfg.roles:
        s += ("\nДопустимые исполнители и участники (других не придумывай): "
              + ", ".join(cfg.roles) + ".\n")
    return s


def _logger(task: Path, emit: Emit):
    f = task / "run_log.jsonl"

    def log(rec: dict):
        rec = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"), **rec}
        with f.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        status = "OK" if rec.get("ok") else "ошибки: " + "; ".join(rec.get("errors", []))[:300]
        emit(f"  [{rec['step']} #{rec.get('attempt')}] {rec.get('wall_s')} с — {status}")
    return log


def _header(cfg: TaskConfig) -> str:
    m = cfg.meta
    return (f"Работа: {m.work_title} по дисциплине «{m.discipline}»"
            f"{', ' + m.module if m.module else ''}.\nТема: «{m.topic}».\n\n"
            f"ЗАДАНИЕ И ИСХОДНЫЕ ДАННЫЕ:\n{cfg.brief}")


def _check_stop(should_stop):
    if should_stop and should_stop():
        raise Stopped("Остановлено пользователем")


# ------------------------------------------------------------------ шаг 1: план

def cmd_plan(task: Path, emit: Emit = print, should_stop=None) -> Outline:
    cfg = load_task(task)
    log = _logger(task, emit)
    _check_stop(should_stop)
    if cfg.fixed_sections:
        # структура задана шаблоном — модель пишет только цель
        emit("Шаг 1. Структура задана шаблоном, модель формулирует цель…")
        msgs = [{"role": "system", "content": _system(cfg)},
                {"role": "user", "content": _header(cfg) +
                 "\n\nСформулируй цель работы одним предложением. Начни с глагола в инфинитиве, "
                 "без слов «Цель работы»."}]
        goal, res = llm.generate(Goal, msgs, lambda g: Result(
            errors=["Начни с глагола, без слов «Цель работы»."] if g.goal.lower().startswith("цель") else []),
            log)
        if goal is None:
            raise PipelineError("Цель не получилась: " + "; ".join(res.errors))
        outline = Outline(goal=goal.goal, sections=cfg.fixed_sections)
    else:
        emit("Шаг 1. План работы…")
        msgs = [{"role": "system", "content": _system(cfg)},
                {"role": "user", "content": _header(cfg) +
                 "\n\nСоставь план отчёта: цель работы и разделы (2–6). Для каждого раздела — что он "
                 "раскрывает и какие таблицы и рисунки в нём нужны. Если в задании указана структура "
                 "отчёта, следуй ей точно. Введение, заключение и выводы в план не включай."}]
        outline, res = llm.generate(Outline, msgs, check_outline, log)
        if outline is None:
            raise PipelineError("План не получился: " + "; ".join(res.errors))
    (task / "outline.json").write_text(outline.model_dump_json(indent=2), encoding="utf-8")
    emit(f"Цель: {outline.goal}")
    for i, s in enumerate(outline.sections, 1):
        extra = ", ".join(filter(None, [f"табл.: {len(s.tables)}" if s.tables else "",
                                        f"рис.: {len(s.figures)}" if s.figures else ""]))
        emit(f"  {i}. {s.title}" + (f"  ({extra})" if extra else ""))
    return outline


# ------------------------------------------------------------------ шаг 2: текст

def cmd_write(task: Path, emit: Emit = print, should_stop=None) -> Path:
    cfg = load_task(task)
    meta = cfg.meta
    outline = Outline.model_validate_json((task / "outline.json").read_text(encoding="utf-8"))
    log = _logger(task, emit)
    sec_dir = task / "sections"
    sec_dir.mkdir(exist_ok=True)
    sections: list[Section] = []
    known_ids: set[str] = set()
    all_warnings: list[str] = []
    plan_text = "\n".join(f"{i}. {s.title} — {s.purpose}" for i, s in enumerate(outline.sections, 1))

    for i, plan in enumerate(outline.sections, 1):
        _check_stop(should_stop)
        cached = sec_dir / f"{i:02d}.json"
        if cached.exists():   # уже готовые разделы не перегенерируем (удали файл, чтобы переписать)
            sec = Section.model_validate_json(cached.read_text(encoding="utf-8"))
            emit(f"Раздел {i}: «{sec.title}» — уже готов")
        else:
            emit(f"Раздел {i}/{len(outline.sections)}: «{plan.title}»")
            prev = "\n".join(f"- {s.title}: {s.blocks[0].text[:200] if hasattr(s.blocks[0], 'text') else ''}"
                             for s in sections) or "нет"
            need = []
            if plan.tables:
                need.append("таблицы: " + "; ".join(plan.tables))
            if plan.figures:
                need.append("рисунки: " + "; ".join(plan.figures))
            msgs = [{"role": "system", "content": _system(cfg)},
                    {"role": "user", "content": _header(cfg) +
                     f"\n\nЦЕЛЬ РАБОТЫ: {outline.goal}\n\nПЛАН ОТЧЁТА:\n{plan_text}\n\n"
                     f"УЖЕ НАПИСАНО:\n{prev}\n\n"
                     f"Напиши раздел {i} «{plan.title}». Что раскрыть: {plan.purpose}\n"
                     + (f"Обязательно: {'; '.join(need)}.\n" if need else "")
                     + (f"Уже занятые id: {', '.join(sorted(known_ids))}.\n" if known_ids else "")
                     + "Не повторяй то, что уже написано в других разделах."}]
            sec, res = llm.generate(
                Section, msgs, lambda s, p=plan: check_section(s, p, known_ids, cfg.roles), log)
            if sec is None:
                raise PipelineError(f"Раздел {i} не получился: " + "; ".join(res.errors))
            if not res.ok:
                all_warnings += [f"Раздел {i}: НЕ ИСПРАВЛЕНО: {e}" for e in res.errors]
            all_warnings += [f"Раздел {i}: {w}" for w in res.warnings]
            cached.write_text(sec.model_dump_json(indent=2), encoding="utf-8")
        for b in sec.blocks + [b for sub in sec.subsections for b in sub.blocks]:
            if getattr(b, "id", None):
                known_ids.add(b.id)
        sections.append(sec)

    summary = "\n".join(f"{i}. {s.title}: " + " ".join(
        b.text for b in s.blocks if hasattr(b, "text"))[:600] for i, s in enumerate(sections, 1))
    _check_stop(should_stop)
    intro = _text_part(task, cfg, outline, summary, "intro", log, emit, all_warnings) if meta.intro else []
    _check_stop(should_stop)
    concl = _text_part(task, cfg, outline, summary, "conclusion", log, emit, all_warnings) \
        if meta.conclusion else []

    report = Report(meta=meta, goal=outline.goal, intro=intro, sections=sections,
                    conclusion=concl, sources=cfg.sources)
    out = task / "report.json"
    out.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    (task / "review.txt").write_text("\n".join(all_warnings), encoding="utf-8")
    emit(f"Содержание сохранено: {out.name}")
    if all_warnings:
        emit("ПРОВЕРЬ ВРУЧНУЮ:")
        for w in all_warnings:
            emit("  • " + w)
    return out


def _text_part(task, cfg: TaskConfig, outline, summary, kind, log, emit, warnings) -> list[str]:
    meta = cfg.meta
    cached = task / "sections" / f"{kind}.json"
    if cached.exists():   # может быть поправлен руками в приложении — без проверки min_length
        return list(json.loads(cached.read_text(encoding="utf-8")).get("paragraphs", []))
    if kind == "intro":
        ask = ("Напиши ВВЕДЕНИЕ: актуальность в 1–2 предложениях, цель, задачи работы. "
               "Задачи — отдельным абзацем, через точку с запятой.")
    else:
        ask = (f"Напиши раздел «{meta.conclusion}»: что сделано и что показала модель или расчёт. "
               "Только факты из разделов ниже, без новых сведений и без общих фраз о пользе работы.")
    emit(f"{'Введение' if kind == 'intro' else meta.conclusion}…")
    msgs = [{"role": "system", "content": _system(cfg)},
            {"role": "user", "content": _header(cfg) +
             f"\n\nЦЕЛЬ РАБОТЫ: {outline.goal}\n\nКРАТКО ПО РАЗДЕЛАМ:\n{summary}\n\n{ask}"}]
    part, res = llm.generate(TextPart, msgs, check_text_part, log)
    if part is None:
        raise PipelineError(f"{kind} не получился: " + "; ".join(res.errors))
    warnings += [f"{'Введение' if kind == 'intro' else meta.conclusion}: {w}" for w in res.warnings]
    cached.write_text(part.model_dump_json(indent=2), encoding="utf-8")
    return part.paragraphs


# ------------------------------------------------------------------ шаг 3: сборка

def cmd_render(task: Path, emit: Emit = print) -> Path:
    # task.yaml главнее meta в report.json: титул правится без перегенерации
    cfg = load_task(task)
    rp = task / "report.json"
    data = json.loads(rp.read_text(encoding="utf-8"))
    data["meta"] = cfg.meta.model_dump()
    if cfg.sources:
        data["sources"] = cfg.sources
    rp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    path, missing = render(rp)
    emit(f"Готово: {path.name}")
    if missing:
        emit("Нет файлов рисунков (в документе стоят заглушки): "
             + ", ".join(f"figures/{m}.png" for m in missing))
    return path


def main(argv: list[str]):
    if len(argv) < 3 or argv[1] not in ("plan", "write", "render", "all"):
        sys.exit(__doc__)
    task = Path(argv[2])
    try:
        if argv[1] in ("plan", "write", "all"):
            print("Модель:", llm.ping())
        t0 = time.time()
        if argv[1] in ("plan", "all"):
            cmd_plan(task)
        if argv[1] in ("write", "all"):
            cmd_write(task)
        if argv[1] in ("render", "write", "all"):
            cmd_render(task)
        print(f"\nВремя: {time.time() - t0:.0f} с")
    except PipelineError as e:
        sys.exit(str(e))


if __name__ == "__main__":
    main(sys.argv)
