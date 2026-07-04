"""CLI 入口 — Click + Rich."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import print as rprint

from fanqie import __version__
from fanqie.genres.loader import (
    list_all_genres, list_builtin_genres, list_custom_genres,
    load_genre, get_genre_path,
)
from fanqie.style.analyzer import analyze_style
from fanqie.style.profile import StyleProfile
from fanqie.utils.config import load_config, save_global_config, get_llm_config

console = Console()


@click.group()
@click.version_option(__version__, prog_name="fanqie")
def main():
    """fanqie — 爽文 AI 智能体，长篇网文创作引擎."""
    pass


# ============================================================
# config
# ============================================================

@main.group()
def config():
    """配置管理."""
    pass


@config.command("set")
@click.option("--base-url", help="API 地址")
@click.option("--api-key", help="API Key")
@click.option("--model", help="模型名称")
def config_set(base_url, api_key, model):
    """设置 LLM 配置."""
    cfg = load_config()
    if base_url:
        cfg["llm"]["base_url"] = base_url
    if api_key:
        cfg["llm"]["api_key"] = api_key
    if model:
        cfg["llm"]["model"] = model
    save_global_config(cfg)
    console.print("[green]配置已保存[/green]")


@config.command("show")
def config_show():
    """查看当前配置."""
    cfg = load_config()
    llm = cfg.get("llm", {})
    table = Table(title="当前配置")
    table.add_column("项目", style="cyan")
    table.add_column("值", style="white")
    table.add_row("Base URL", llm.get("base_url", ""))
    table.add_row("Model", llm.get("model", ""))
    table.add_row("API Key", "***" if llm.get("api_key") else "(未设置)")
    table.add_row("Temperature", str(llm.get("temperature", 0.7)))
    console.print(table)


# ============================================================
# genre
# ============================================================

@main.group()
def genre():
    """题材模板管理."""
    pass


@genre.command("list")
def genre_list():
    """列出所有可用题材."""
    all_genres = list_all_genres()
    table = Table(title="可用题材")
    table.add_column("ID", style="cyan")
    table.add_column("名称", style="white")
    table.add_column("来源", style="green")

    for gid, source in sorted(all_genres.items()):
        g = load_genre(gid)
        name = g.name if g else gid
        table.add_row(gid, name, source)

    console.print(table)


@genre.command("show")
@click.argument("genre_id")
def genre_show(genre_id):
    """查看题材详情."""
    g = load_genre(genre_id)
    if g is None:
        console.print(f"[red]题材 '{genre_id}' 不存在[/red]")
        return

    console.print(Panel(f"[bold cyan]{g.name}[/bold cyan] ({g.id})", title="题材"))
    console.print(g.description)
    console.print()
    console.print(f"[bold]章节类型:[/bold] {'、'.join(g.chapter_types)}")
    console.print(f"[bold]爽点类型:[/bold] {'、'.join(g.satisfaction_types)}")
    console.print(f"[bold]节奏规则:[/bold] {g.pacing_rule}")
    console.print(f"[bold]数值体系:[/bold] {'是' if g.numerical_system else '否'}")
    console.print(f"[bold]力量体系:[/bold] {'是' if g.power_scaling else '否'}")
    console.print()
    console.print("[bold red]禁忌:[/bold red]")
    for p in g.prohibitions:
        console.print(f"  - {p}")
    console.print()
    console.print("[bold]写作规则:[/bold]")
    for k, v in g.rules.items():
        console.print(f"  [cyan]{k}:[/cyan] {v}")


@genre.command("create")
@click.argument("genre_id")
@click.option("--from", "base_genre", default="xuanhuan", help="基于哪个内置模板")
def genre_create(genre_id, base_genre):
    """基于内置模板创建自定义题材."""
    custom_dir = Path(__file__).parent.parent / "genres" / "custom"
    custom_dir.mkdir(parents=True, exist_ok=True)

    source_path = get_genre_path(base_genre)
    if source_path is None:
        console.print(f"[red]基础题材 '{base_genre}' 不存在[/red]")
        return

    dest_path = custom_dir / f"{genre_id}.toml"
    if dest_path.exists():
        console.print(f"[yellow]自定义题材 '{genre_id}' 已存在[/yellow]")
        return

    with open(source_path, "r", encoding="utf-8") as src:
        content = src.read()

    with open(dest_path, "w", encoding="utf-8") as dst:
        dst.write(content)

    console.print(f"[green]已创建自定义题材 '{genre_id}'（基于 {base_genre}）[/green]")
    console.print(f"  路径: {dest_path}")


# ============================================================
# new
# ============================================================

@main.command()
@click.argument("title")
@click.option("--genre", "-g", "genre_id", default="xuanhuan", help="题材 ID")
@click.option("--words", "-w", default=2000, help="每章目标字数")
@click.option("--chapters", "-c", default=500, help="目标总章数")
@click.option("--brief", "-b", "brief_file", default=None, help="创意简报文件路径")
@click.option("--yes", "-y", "auto_confirm", is_flag=True, default=False, help="跳过 Foundation 确认")
def new(title, genre_id, words, chapters, brief_file, auto_confirm):
    """创建新书（含 Foundation 生成）."""
    from fanqie.engine.orchestrator import create_book

    g = load_genre(genre_id)
    if g is None:
        console.print(f"[red]题材 '{genre_id}' 不存在，请用 'fanqie genre list' 查看可用题材[/red]")
        return

    brief_text = ""
    if brief_file:
        brief_path = Path(brief_file)
        if not brief_path.exists():
            console.print(f"[red]简报文件 '{brief_file}' 不存在[/red]")
            return
        with open(brief_path, "r", encoding="utf-8") as f:
            brief_text = f.read()
        console.print(f"[cyan]已读取简报: {brief_file} ({len(brief_text)} 字)[/cyan]")

    orch = create_book(
        title=title,
        genre_id=genre_id,
        chapter_word_count=words,
        target_chapters=chapters,
    )

    console.print(f"[green]新书已创建[/green]")
    console.print(f"  书名: {title}")
    console.print(f"  题材: {g.name}")
    console.print(f"  ID: {orch.book.id}")
    console.print(f"  目录: {orch.book_dir}")

    if brief_text:
        console.print()
        console.print("[bold cyan]Step 0: 简报优化...[/bold cyan]")
        with console.status("AI 正在分析简报..."):
            report = orch.run_brief(brief_text)
        console.print(f"  [bold]评分: {report.score.total}/100 — {report.score.verdict}[/bold]")
        console.print(f"  题材契合度: {report.score.genre_fit}/30")
        console.print(f"  爽点潜力: {report.score.satisfaction_potential}/25")
        console.print(f"  可执行性: {report.score.executability}/20")
        console.print(f"  完整性: {report.score.completeness}/15")
        console.print(f"  差异化: {report.score.differentiation}/10")
        if report.suggestions:
            console.print(f"  [yellow]建议:[/yellow]")
            for s in report.suggestions[:3]:
                console.print(f"    - {s}")
        if report.missing_elements:
            console.print(f"  [yellow]缺失要素: {', '.join(report.missing_elements)}[/yellow]")

        if report.score.total < 50:
            console.print("[red]评分过低，建议重写简报后再试[/red]")
            return
        elif report.score.total < 70:
            console.print("[yellow]评分偏低，建议优化后使用。已自动使用优化版简报[/yellow]")
            brief_text = report.optimized_brief

    console.print()
    console.print("[bold cyan]Step 1: 生成 Foundation...[/bold cyan]")
    with console.status("AI 正在构建世界观..."):
        foundation = orch.build_foundation(brief=brief_text)
    console.print("[green]Foundation 生成完成[/green]")

    console.print()
    console.print("[bold cyan]Step 2: 卷纲规划...[/bold cyan]")
    with console.status("AI 正在规划卷纲..."):
        volume_plan = orch.build_volume_plan()
    console.print(f"[green]卷纲规划完成 — 共 {len(volume_plan.volumes)} 卷[/green]")

    console.print()
    summary = orch.get_foundation_summary()
    console.print(Panel(summary[:2000], title="Foundation 摘要"))

    if not auto_confirm:
        console.print()
        console.print("[bold]请确认以上设定:[/bold]")
        console.print("  [green]y[/green] - 确认，进入 ready 状态")
        console.print("  [yellow]m <部分>[/yellow] - 要求修改某部分")
        console.print("  [red]n[/red] - 取消，全部重新生成")

        response = click.prompt("", default="y").strip().lower()

        if response == "n":
            console.print("[yellow]已取消，请重新运行 fanqie new[/yellow]")
            return
        elif response.startswith("m"):
            change = response[1:].strip() if len(response) > 1 else ""
            console.print(f"[yellow]修改请求: {change}[/yellow]")
            console.print("[cyan]正在执行 Advise 修改...[/cyan]")
            with console.status("AI 正在分析波及影响..."):
                impact = orch.advise(change)
            console.print(f"[green]修改完成 — 影响 {len(impact.impacts)} 个文件[/green]")

    console.print()
    console.print("[bold cyan]Step 4: 初始化状态...[/bold cyan]")
    orch.initialize_book_state()
    console.print(f"[green]书籍 '{title}' 已就绪，可以开始写作！[/green]")
    console.print(f"  运行: fanqie write {orch.book.id}")


# ============================================================
# write
# ============================================================

@main.command()
@click.argument("book_id")
@click.option("--chapters", "-n", default=1, help="生成章数")
@click.option("--instruction", "-i", default="", help="干预指令")
def write(book_id, chapters, instruction):
    """写章节."""
    orch = _load_orchestrator(book_id)
    if orch is None:
        return

    # 检查完结状态
    if orch.is_complete:
        console.print(f"[green]《{orch.book.title}》已完结 ✅[/green]")
        console.print(f"  完结报告: {orch.book_dir / 'story' / 'completion_report.md'}")
        return

    # 检查完结窗口
    ch_count = orch.repo.get_chapter_count()
    from fanqie.engine.planner import is_in_completion_window, compute_completion_window
    if is_in_completion_window(ch_count + 1, orch.book.target_chapters):
        remaining = orch.book.target_chapters - ch_count
        console.print(f"[bold yellow]🔔 完结窗口 — 剩余 {remaining} 章[/bold yellow]")
        console.print(f"  系统将自动规划伏笔回收和收尾弧线")

    for i in range(chapters):
        ch_num = orch.repo.get_chapter_count() + 1
        console.print(f"[cyan]正在写第 {ch_num} 章...[/cyan]")

        try:
            chapter = orch.write_next_chapter(user_instruction=instruction if i == 0 else "")
        except RuntimeError as e:
            console.print(f"[red]{e}[/red]")
            return

        status_color = "green" if chapter.status.value == "approved" else "yellow"
        score = f" (评分: {chapter.audit_score})" if chapter.audit_score else ""

        # 完结标记
        completion_tag = ""
        from fanqie.engine.planner import is_final_chapter
        if is_final_chapter(chapter.chapter_number, orch.book.target_chapters):
            completion_tag = " [bold green]🎉 最终章！[/bold green]"
        elif is_in_completion_window(chapter.chapter_number, orch.book.target_chapters):
            completion_tag = " [yellow][完结窗口][/yellow]"

        console.print(
            f"  [{status_color}]第 {chapter.chapter_number} 章 {chapter.title}[/{status_color}]"
            f" — {chapter.word_count} 字{score}{completion_tag}"
        )

        if chapter.audit_issues:
            criticals = [i for i in chapter.audit_issues if i.get("severity") == "critical"]
            warnings = [i for i in chapter.audit_issues if i.get("severity") == "warning"]
            if criticals:
                console.print(f"    [red]{len(criticals)} 个严重问题[/red]")
            if warnings:
                console.print(f"    [yellow]{len(warnings)} 个警告[/yellow]")

    # 写完后检查是否已自动完结
    if orch.is_complete:
        console.print()
        console.print(f"[bold green]🎉 《{orch.book.title}》完结！[/bold green]")
        console.print(f"  完结报告: {orch.book_dir / 'story' / 'completion_report.md'}")


# ============================================================
# complete
# ============================================================

@main.command()
@click.argument("book_id")
@click.option("--yes", "-y", "auto_confirm", is_flag=True, default=False, help="跳过确认")
def complete(book_id, auto_confirm):
    """手动完结一本书（用于超目标或提前完结）."""
    orch = _load_orchestrator(book_id)
    if orch is None:
        return

    if orch.is_complete:
        console.print(f"[green]《{orch.book.title}》已完结 ✅[/green]")
        return

    ch_count = orch.repo.get_chapter_count()
    chapters = orch.repo.get_all_chapters()
    total_words = sum(ch.get("word_count", 0) for ch in chapters)

    # 显示当前状态
    console.print(f"[bold]《{orch.book.title}》完结前状态[/bold]")
    console.print(f"  已写章节: {ch_count} 章")
    console.print(f"  目标章节: {orch.book.target_chapters} 章")
    console.print(f"  总字数: {total_words} 字")

    # 检查伏笔状态
    hook_pool = orch.state_mgr.load_hook_pool()
    unresolved = [h for h in hook_pool.hooks if h.status.value not in ("resolved", "deferred")]
    if unresolved:
        console.print(f"  [yellow]未回收伏笔: {len(unresolved)} 个[/yellow]")
        for h in unresolved:
            console.print(f"    - {h.hook_id}（{h.status.value}）: {h.expected_payoff[:60]}")
    else:
        console.print(f"  [green]伏笔: 全部已回收 ✅[/green]")

    if not auto_confirm:
        console.print()
        if unresolved:
            console.print("[yellow]⚠️ 存在未回收伏笔，完结将强制标记为已回收。[/yellow]")
        console.print("[bold]确认完结？[/bold]")
        console.print("  [green]y[/green] - 确认完结")
        console.print("  [red]n[/red] - 取消")

        response = click.prompt("", default="y").strip().lower()
        if response != "y":
            console.print("[yellow]已取消[/yellow]")
            return

    console.print()
    console.print("[cyan]正在生成完结报告...[/cyan]")
    with console.status("AI 正在生成完结报告..."):
        report = orch.finalize()

    console.print()
    console.print(f"[bold green]🎉 《{orch.book.title}》完结！[/bold green]")
    console.print(f"  总章节: {report.total_chapters} 章")
    console.print(f"  总字数: {report.total_words} 字")
    console.print(f"  伏笔回收: {report.hooks_resolved}/{report.hooks_total}")
    console.print(f"  完结报告: {orch.book_dir / 'story' / 'completion_report.md'}")


# ============================================================
# audit
# ============================================================

@main.command()
@click.argument("book_id")
@click.argument("chapter_number", type=int)
@click.option("--retry", "-r", default=3, help="最大重试次数")
def audit(book_id, chapter_number, retry):
    """对指定章节执行审计+自动重写."""
    orch = _load_orchestrator(book_id)
    if orch is None:
        return

    # 加载章节
    chapters = orch.repo.get_all_chapters()
    target_ch = None
    for ch in chapters:
        if ch["chapter_number"] == chapter_number:
            target_ch = ch
            break

    if target_ch is None:
        console.print(f"[red]第{chapter_number}章不存在[/red]")
        return

    from fanqie.models import Chapter, ChapterMemo
    from fanqie.engine.auditor import audit_and_revise

    chapter = Chapter(
        book_id=book_id,
        chapter_number=chapter_number,
        title=target_ch.get("title", ""),
        content=target_ch.get("content", ""),
        word_count=target_ch.get("word_count", 0),
    )

    # 构建一个简单的 memo（审计主要看内容质量，memo 辅助）
    memo = ChapterMemo(
        book_id=book_id,
        chapter_number=chapter_number,
        goal="",
        reader_waiting_for="",
        pay_off="",
        keep_hidden="",
        transition_duty="",
        key_choice_check="",
        end_changes="",
        must_avoid=[],
        style_emphasis=[],
    )

    console.print(f"[cyan]正在审计第{chapter_number}章《{chapter.title}》...[/cyan]")
    console.print(f"  最大重试: {retry} 次")

    with console.status("AI 正在审计..."):
        revised, history = audit_and_revise(
            client=orch.client,
            genre=orch.genre,
            state_mgr=orch.state_mgr,
            chapter=chapter,
            memo=memo,
            max_retries=retry,
        )

    # 显示审计历史
    for i, audit_result in enumerate(history):
        icon = "✅" if audit_result.passed else "❌"
        score = audit_result.overall_score or 0
        score_color = "green" if score >= 85 else "yellow" if score >= 70 else "red"
        console.print(f"  [{score_color}]第{i+1}轮 {icon} 评分: {score}/100[/{score_color}]")
        if audit_result.issues:
            criticals = [iss for iss in audit_result.issues if iss.severity == "critical"]
            warnings = [iss for iss in audit_result.issues if iss.severity == "warning"]
            if criticals:
                console.print(f"    [red]{len(criticals)} 个严重问题:[/red]")
                for iss in criticals[:5]:
                    console.print(f"      - [{iss.category}] {iss.description[:80]}")
            if warnings:
                console.print(f"    [yellow]{len(warnings)} 个警告[/yellow]")

    final = history[-1]
    if final.passed:
        console.print(f"\n[green]✅ 审计通过！评分: {final.overall_score}/100[/green]")
    else:
        console.print(f"\n[yellow]⚠️ {retry} 次重试后仍未通过，评分: {final.overall_score}/100[/yellow]")

    # 保存修订后的章节
    if revised.content != chapter.content:
        orch._save_chapter_file(revised)
        orch.repo.save_chapter({
            "book_id": book_id,
            "chapter_number": revised.chapter_number,
            "title": revised.title,
            "content": revised.content,
            "word_count": revised.word_count,
            "status": "approved" if final.passed else "revised",
            "audit_score": final.overall_score,
            "audit_issues": json.dumps([i.model_dump() for i in final.issues], ensure_ascii=False),
            "created_at": target_ch.get("created_at", ""),
            "updated_at": datetime.now().isoformat(),
        })
        console.print(f"[green]已保存修订后的章节[/green]")


# ============================================================
# rewrite
# ============================================================

@main.command()
@click.argument("book_id")
@click.argument("chapter_number", type=int)
@click.option("--instruction", "-i", default="", help="重写意见（你对这一章的不满与要求）")
@click.option("--mode", "-m", type=click.Choice(["refine", "rewrite"]), default="refine",
              help="refine=按意见微调（默认）；rewrite=按意见大幅重写")
@click.option("--truncate", "-t", is_flag=True, default=False,
              help="删除本章之后的所有章节并回滚记忆（后续推倒重来）")
def rewrite(book_id, chapter_number, instruction, mode, truncate):
    """按你的意见重写指定章节（覆盖前自动备份为 .bak）."""
    orch = _load_orchestrator(book_id)
    if orch is None:
        return

    mode_label = "微调" if mode == "refine" else "大幅重写"
    console.print(f"[cyan]正在{mode_label}第{chapter_number}章...[/cyan]")
    if instruction:
        console.print(f"[dim]意见：{instruction}[/dim]")
    if truncate:
        console.print(f"[yellow]将删除第{chapter_number}章之后的所有章节并回滚记忆[/yellow]")

    try:
        with console.status(f"AI 正在{mode_label}..."):
            revised = orch.rewrite_chapter(
                chapter_number, instruction=instruction, mode=mode, truncate_after=truncate,
            )
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        return
    except Exception as e:
        console.print(f"[red]重写失败：{e}[/red]")
        return

    console.print(f"[green]✓ 第{chapter_number}章已重写完成[/green]")
    console.print(f"  标题：{revised.title}")
    console.print(f"  字数：{revised.word_count}")
    console.print(f"[dim]原章已备份为 {chapter_number:04d}.md.bak[/dim]")
    if truncate:
        console.print(f"[dim]第{chapter_number}章之后的章节已移除，记忆已回滚[/dim]")


# ============================================================
# status
# ============================================================

@main.command()
@click.argument("book_id")
def status(book_id):
    """查看写作状态."""
    orch = _load_orchestrator(book_id)
    if orch is None:
        return

    s = orch.get_status()
    table = Table(title=f"书籍 {s['book']}")
    table.add_column("项目", style="cyan")
    table.add_column("值", style="white")
    for k, v in s.items():
        if k != "book":
            table.add_row(k, str(v))

    ch_count = orch.repo.get_chapter_count()
    if ch_count > 0:
        chapters_per_volume = 50
        current_vol = (ch_count - 1) // chapters_per_volume + 1
        table.add_row("当前卷", f"第{current_vol}卷")

    hook_pool = orch.state_mgr.load_hook_pool()
    if hook_pool.hooks:
        resolved = sum(1 for h in hook_pool.hooks if h.status.value in ("resolved", "deferred"))
        table.add_row("伏笔", f"{len(hook_pool.hooks)} 个（{resolved} 已回收）")

    # 完结窗口信息
    from fanqie.engine.planner import is_in_completion_window, compute_completion_window
    if not orch.is_complete and is_in_completion_window(ch_count + 1, orch.book.target_chapters):
        remaining = orch.book.target_chapters - ch_count
        window_start = compute_completion_window(orch.book.target_chapters)
        table.add_row("完结窗口", f"第{window_start}-{orch.book.target_chapters}章（剩余 {remaining} 章）")

        # 显示完结计划
        completion_plan = orch.get_completion_plan()
        if completion_plan:
            pending = sum(1 for h in completion_plan.hook_schedule if h.status == "pending")
            resolved_in_plan = sum(1 for h in completion_plan.hook_schedule if h.status == "resolved")
            table.add_row("伏笔回收进度", f"{resolved_in_plan}/{len(completion_plan.hook_schedule)} 已回收")

    # 完结状态
    if orch.is_complete:
        table.add_row("完结报告", str(orch.book_dir / "story" / "completion_report.md"))

    console.print(table)


# ============================================================
# advise
# ============================================================

@main.command()
@click.argument("book_id")
@click.argument("instruction")
@click.option("--dry-run", is_flag=True, default=False, help="仅做波及分析，不实际修改")
def advise(book_id, instruction, dry_run):
    """人机协作编辑：先做波及分析再修改.

    fanqie advise <book-id> "修改意见"
    """
    orch = _load_orchestrator(book_id)
    if orch is None:
        return

    console.print(f"[cyan]正在分析波及影响...[/cyan]")
    with console.status("AI 正在分析..."):
        impact = orch.advise(instruction)

    console.print()
    console.print(Panel(impact.summary, title="波及分析"))

    if impact.affected_nodes:
        console.print(f"[yellow]受影响节点:[/yellow]")
        for node in impact.affected_nodes:
            console.print(f"  - {node}")

    if impact.impacts:
        console.print(f"\n[yellow]受影响文件 ({len(impact.impacts)} 个):[/yellow]")
        for imp in impact.impacts:
            sev_color = {"critical": "red", "major": "yellow", "moderate": "cyan", "minor": "white"}
            color = sev_color.get(imp.severity, "white")
            console.print(f"  [{color}][{imp.severity}][/{color}] {imp.file}: {imp.reason[:80]}")

    if dry_run:
        console.print("\n[yellow]--dry-run 模式，未实际修改文件[/yellow]")
    else:
        console.print(f"\n[green]修改完成 — 已记录到 modification_log.md[/green]")


# ============================================================
# style
# ============================================================

@main.group()
def style():
    """文风管理."""
    pass


@style.command("analyze")
@click.argument("file", type=click.Path(exists=True))
@click.option("--output", "-o", default=None, help="输出 JSON 路径")
def style_analyze(file, output):
    """分析参考文本的文风指纹."""
    with open(file, "r", encoding="utf-8") as f:
        text = f.read()

    profile = analyze_style(text, source_name=os.path.basename(file))

    console.print(Panel(f"[bold]文风分析结果 — {profile.source_name}[/bold]"))
    console.print(f"平均句长: {profile.avg_sentence_length} 字 (标准差 {profile.sentence_length_stddev})")
    console.print(f"平均段长: {profile.avg_paragraph_length} 字 (范围 {profile.paragraph_length_range[0]}-{profile.paragraph_length_range[1]})")
    console.print(f"词汇多样性: {profile.vocabulary_diversity}")
    if profile.top_patterns:
        console.print(f"高频开头: {'、'.join(profile.top_patterns)}")
    if profile.rhetorical_features:
        console.print(f"修辞特征: {'、'.join(profile.rhetorical_features)}")

    if output:
        with open(output, "w", encoding="utf-8") as f:
            json.dump(profile.to_dict(), f, ensure_ascii=False, indent=2)
        console.print(f"[green]已保存到 {output}[/green]")


@style.command("import")
@click.argument("file", type=click.Path(exists=True))
@click.argument("book_id")
def style_import(file, book_id):
    """导入文风指纹到指定书."""
    with open(file, "r", encoding="utf-8") as f:
        data = json.load(f)

    profile = StyleProfile.from_dict(data)

    orch = _load_orchestrator(book_id)
    if orch is None:
        return

    orch.style_profile = profile

    profile_path = orch.book_dir / "style_profile.json"
    with open(profile_path, "w", encoding="utf-8") as f:
        json.dump(profile.to_dict(), f, ensure_ascii=False, indent=2)

    console.print(f"[green]文风指纹已导入到 {orch.book.title}[/green]")


@style.command("show")
@click.argument("book_id")
def style_show(book_id):
    """查看当前书的文风指纹."""
    orch = _load_orchestrator(book_id)
    if orch is None:
        return

    if orch.style_profile is None:
        console.print("[yellow]该书未设置文风指纹[/yellow]")
        return

    p = orch.style_profile
    console.print(Panel(f"[bold]文风指纹 — {p.source_name or '未知来源'}[/bold]"))
    console.print(f"平均句长: {p.avg_sentence_length} 字")
    console.print(f"平均段长: {p.avg_paragraph_length} 字")
    console.print(f"词汇多样性: {p.vocabulary_diversity}")


@style.command("remove")
@click.argument("book_id")
def style_remove(book_id):
    """移除文风指纹."""
    orch = _load_orchestrator(book_id)
    if orch is None:
        return

    orch.style_profile = None
    profile_path = orch.book_dir / "style_profile.json"
    if profile_path.exists():
        profile_path.unlink()

    console.print(f"[green]已移除 {orch.book.title} 的文风指纹[/green]")


# ============================================================
# export
# ============================================================

@main.command()
@click.argument("book_id")
@click.option("--format", "-f", "fmt", default="txt", help="导出格式 (txt/md)")
@click.option("--output", "-o", default=None, help="输出路径")
def export(book_id, fmt, output):
    """导出书籍."""
    orch = _load_orchestrator(book_id)
    if orch is None:
        return

    chapters = orch.repo.get_all_chapters()
    if not chapters:
        console.print("[yellow]暂无章节[/yellow]")
        return

    lines = [f"# {orch.book.title}", "", f"题材: {orch.genre.name}", ""]
    for ch in chapters:
        lines.append(f"## 第{ch['chapter_number']}章 {ch['title']}")
        lines.append("")
        lines.append(ch["content"])
        lines.append("")
        lines.append("---")
        lines.append("")

    content = "\n".join(lines)
    ext = "md" if fmt == "md" else "txt"
    out_path = output or f"{orch.book.title}.{ext}"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(content)

    console.print(f"[green]已导出到 {out_path}[/green]")
    console.print(f"  共 {len(chapters)} 章，{sum(ch['word_count'] for ch in chapters)} 字")


# ============================================================
# helpers
# ============================================================

def _load_orchestrator(book_id: str):
    """加载 Orchestrator."""
    from fanqie.engine.orchestrator import Orchestrator
    from fanqie.models import BookConfig
    from fanqie.storage.repository import Repository

    data_dir = "data"
    repo = Repository(data_dir, book_id)
    book_data = repo.get_book()
    if book_data is None:
        console.print(f"[red]书籍 '{book_id}' 不存在[/red]")
        return None

    book = BookConfig(**book_data)
    genre = load_genre(book.genre_id)
    if genre is None:
        console.print(f"[red]题材 '{book.genre_id}' 不存在[/red]")
        return None

    style_profile = None
    profile_path = Path(data_dir) / book_id / "style_profile.json"
    if profile_path.exists():
        with open(profile_path, "r", encoding="utf-8") as f:
            style_profile = StyleProfile.from_dict(json.load(f))

    return Orchestrator(book=book, genre=genre, data_dir=data_dir, style_profile=style_profile)


if __name__ == "__main__":
    main()
