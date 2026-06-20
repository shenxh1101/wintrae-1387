import argparse
import os
import sys
from datetime import datetime
from typing import List, Optional
from .models import ScanResult, SubtitleFile, IssueSeverity, IssueType, ISSUE_TYPE_LABELS
from .parser import SubtitleParser
from .scanner import SubtitleScanner
from .fixer import SubtitleFixer
from .splitter import DualLanguageSplitter
from .merger import SubtitleMerger
from .reporter import ReportGenerator
from .config import Config, PROJECT_CONFIG_FILENAME
from .utils import (
    find_subtitle_files,
    get_output_path,
    parse_timecode,
    format_timecode,
    format_time_with_frames,
    parse_since,
    ensure_directory,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="subtitle-checker",
        description="字幕翻译质量检查工具 - 批量检查和修复字幕文件",
    )
    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    init_parser = subparsers.add_parser("init", help="生成项目配置文件")
    init_parser.add_argument("--output", "-o", type=str, default=PROJECT_CONFIG_FILENAME,
                            help=f"输出配置文件路径（默认: {PROJECT_CONFIG_FILENAME}）")

    scan_parser = subparsers.add_parser("scan", help="扫描字幕文件检查问题")
    _add_common_args(scan_parser)
    scan_parser.add_argument("--preview", type=str, default=None,
                            help="预览指定时间段的字幕，格式: HH:MM:SS,mmm-HH:MM:SS,mmm")
    scan_parser.add_argument("--report", type=str, default=None,
                            help="输出报告文件路径（支持 .txt/.json/.csv/.html）")
    scan_parser.add_argument("--no-ignore", action="store_true",
                            help="不使用忽略清单，显示所有问题")

    fix_parser = subparsers.add_parser("fix", help="自动修正常见格式问题")
    _add_common_args(fix_parser)
    fix_parser.add_argument("--output-dir", type=str, default=None,
                           help="修复后文件输出目录")
    fix_parser.add_argument("--suffix", type=str, default="_fixed",
                           help="输出文件后缀")
    fix_parser.add_argument("--align-frames", dest="align_frames", action="store_true",
                           default=None, help="时间轴对齐到帧边界（默认开启）")
    fix_parser.add_argument("--no-align-frames", dest="align_frames", action="store_false",
                           help="不对齐到帧边界")

    split_parser = subparsers.add_parser("split", help="拆分双语字幕")
    _add_common_args(split_parser)
    split_parser.add_argument("--output-dir", type=str, default=None,
                             help="拆分后文件输出目录")

    merge_parser = subparsers.add_parser("merge", help="合并分段字幕文件")
    _add_common_args(merge_parser)
    merge_parser.add_argument("--gap", type=int, default=0,
                             help="分段之间的间隔时间（毫秒）")
    merge_parser.add_argument("--output", type=str, default=None,
                             help="合并后输出文件路径")
    merge_parser.add_argument("--merge-pattern", type=str, default=None,
                             help="匹配分段文件的正则模式")

    report_parser = subparsers.add_parser("report", help="生成详细的问题报告")
    _add_common_args(report_parser)
    report_parser.add_argument("--output", "-o", type=str, default=None,
                              help="报告输出路径（.txt/.json/.csv/.html）")
    report_parser.add_argument("--format", type=str, choices=["text", "json", "csv", "html"],
                               default=None, help="报告格式（不指定则根据扩展名判断）")

    ignore_parser = subparsers.add_parser("ignore", help="管理忽略清单")
    ignore_sub = ignore_parser.add_subparsers(dest="ignore_action")
    add_parser = ignore_sub.add_parser("add", help="添加忽略项")
    add_parser.add_argument("file", type=str, help="字幕文件路径")
    add_parser.add_argument("--index", "-i", type=int, required=True, help="字幕编号")
    add_parser.add_argument("--type", "-t", type=str, required=True,
                           choices=[t.value for t in IssueType], help="问题类型")
    add_parser.add_argument("--line", "-n", type=int, default=None, help="行号（可选）")
    add_parser.add_argument("--reason", "-r", type=str, default="", help="忽略原因")
    list_parser = ignore_sub.add_parser("list", help="列出所有忽略项")
    clear_parser = ignore_sub.add_parser("clear", help="清空忽略清单")
    _add_common_args(ignore_parser)
    _add_common_args(add_parser)
    _add_common_args(list_parser)
    _add_common_args(clear_parser)

    return parser


def _add_common_args(parser: argparse.ArgumentParser):
    parser.add_argument("path", type=str, nargs="?", default=".",
                       help="字幕文件或目录路径")
    parser.add_argument("--language", "-l", type=str, default=None,
                       choices=["zh", "en"],
                       help="指定字幕语言（zh/en），覆盖配置文件设置")
    parser.add_argument("--fps", type=float, default=None,
                       help="视频帧率，覆盖配置文件设置")
    parser.add_argument("--config", "-c", type=str, default=None,
                       help="配置文件路径（不指定则自动搜索 subtitle_config.json）")
    parser.add_argument("--no-recursive", action="store_true",
                       help="不递归扫描子目录")
    parser.add_argument("--since", type=str, default=None,
                       help="只扫描最近修改的文件，支持天数(如 3)或日期(如 2026-01-01)")
    parser.add_argument("--pattern", type=str, default=None,
                       help="按文件名模式筛选，支持通配符（如 *ep01*.srt）")


def _resolve_config(args: argparse.Namespace) -> Config:
    config_path = getattr(args, "config", None)
    if not config_path:
        config_path = Config.find_project_config(".")
    config = Config(config_path)
    return config


def _resolve_fps(args: argparse.Namespace, config: Config) -> float:
    fps = getattr(args, "fps", None)
    if fps is not None:
        return fps
    return config.get_fps()


def _resolve_language(args: argparse.Namespace, config: Config) -> Optional[str]:
    lang = getattr(args, "language", None)
    if lang:
        return lang
    return config.get_language()


def _resolve_output_dir(args: argparse.Namespace, config: Config) -> Optional[str]:
    outdir = getattr(args, "output_dir", None)
    if outdir:
        return outdir
    return config.get_output_dir()


def _resolve_report_path(args: argparse.Namespace, config: Config, default_name: str) -> str:
    output = getattr(args, "output", None) or getattr(args, "report", None) or default_name
    if not os.path.isabs(output):
        cfg_outdir = config.get_output_dir()
        if cfg_outdir:
            ensure_directory(cfg_outdir)
            output = os.path.join(cfg_outdir, os.path.basename(output))
    parent = os.path.dirname(output)
    if parent:
        ensure_directory(parent)
    return output


def _load_files(
    path: str,
    language: Optional[str],
    fps: float,
    recursive: bool,
    pattern: Optional[str] = None,
    since: Optional[float] = None,
) -> List[SubtitleFile]:
    files = []
    if os.path.isfile(path):
        sf = SubtitleParser.parse(path, language, fps)
        if sf:
            files.append(sf)
    else:
        subtitle_paths = find_subtitle_files(path, recursive=recursive, pattern=pattern, since=since)
        for fp in subtitle_paths:
            sf = SubtitleParser.parse(fp, language, fps)
            if sf:
                files.append(sf)
    return files


def cmd_init(args: argparse.Namespace, config: Config) -> int:
    output = args.output
    if os.path.exists(output):
        print(f"配置文件已存在: {output}")
        print("如需覆盖，请先删除现有文件")
        return 1
    Config.generate_template(output)
    print(f"已生成项目配置文件: {output}")
    print("请根据项目需要编辑其中的参数")
    return 0


def cmd_scan(args: argparse.Namespace, config: Config) -> int:
    fps = _resolve_fps(args, config)
    language = _resolve_language(args, config)
    since_ts = parse_since(args.since) if getattr(args, "since", None) else None
    use_ignore = not getattr(args, "no_ignore", False)

    files = _load_files(args.path, language, fps, not args.no_recursive,
                       getattr(args, "pattern", None), since_ts)
    if not files:
        print("未找到字幕文件")
        return 1

    scanner = SubtitleScanner(config, fps=fps, use_ignore_list=use_ignore)
    result = scanner.scan_directory(files)

    if getattr(args, "preview", None):
        preview = args.preview
        parts = preview.split("-")
        if len(parts) == 2:
            start = parse_timecode(parts[0])
            end = parse_timecode(parts[1])
            if start is not None and end is not None:
                for sf in files:
                    print(f"\n预览 {sf.filepath} [{format_time_with_frames(start, fps)} - {format_time_with_frames(end, fps)}]:")
                    previews = scanner.preview_range(sf, start, end)
                    for e in previews:
                        print(f"  #{e.index} {format_time_with_frames(e.start_time, fps)} --> {format_time_with_frames(e.end_time, fps)}")
                        for line in e.text_lines:
                            print(f"    {line if line.strip() else '(空行)'}")

    ReportGenerator.print_console_summary(result)

    for sf in result.files:
        print(f"\n{sf.filepath} ({len(sf.issues)} 个问题, {sf.fps}fps)")
        for issue in sf.issues:
            sev = issue.severity.value.upper()
            idx = f"#{issue.subtitle_index}" if issue.subtitle_index else ""
            print(f"  [{sev}] {idx} {issue.message}")

    if getattr(args, "report", None):
        report_path = _resolve_report_path(args, config, args.report)
        _save_report(result, report_path, fps, getattr(args, "format", None))
        print(f"\n报告已保存到: {report_path}")
    return 0


def cmd_fix(args: argparse.Namespace, config: Config) -> int:
    fps = _resolve_fps(args, config)
    language = _resolve_language(args, config)
    since_ts = parse_since(args.since) if getattr(args, "since", None) else None
    output_dir = _resolve_output_dir(args, config)
    align_frames = getattr(args, "align_frames", None)

    files = _load_files(args.path, language, fps, not args.no_recursive,
                       getattr(args, "pattern", None), since_ts)
    if not files:
        print("未找到字幕文件")
        return 1

    fixer = SubtitleFixer(config, fps=fps, align_frames=align_frames)
    scanner = SubtitleScanner(config, fps=fps, use_ignore_list=False)

    total_fixed = 0
    total_remaining = 0

    for sf in files:
        scanner.scan_file(sf)
        original_issues = len(sf.issues)
        fixed = fixer.fix_file(sf)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
            out_name = os.path.basename(sf.filepath)
            base, ext = os.path.splitext(out_name)
            out_path = os.path.join(output_dir, base + args.suffix + ext)
        else:
            out_path = get_output_path(sf.filepath, args.suffix)
        SubtitleParser.write_srt(fixed, out_path)

        scan_result = scanner.scan_file(fixed)
        remaining = len(scan_result.issues)
        fixed_count = original_issues - remaining
        total_fixed += max(0, fixed_count)
        total_remaining += remaining

        status = "✓ 所有问题已自动修复" if remaining == 0 else f"仍有 {remaining} 个问题需手动处理"
        print(f"修复: {sf.filename} -> {os.path.basename(out_path)} ({status})")

    align_info = f" (帧对齐: {'开' if fixer.align_frames else '关'}, {fps}fps)"
    print(f"\n共处理 {len(files)} 个文件{align_info}，自动修复 {total_fixed} 个问题，{total_remaining} 个需手动处理")
    return 0


def cmd_split(args: argparse.Namespace, config: Config) -> int:
    fps = _resolve_fps(args, config)
    language = _resolve_language(args, config)
    output_dir = _resolve_output_dir(args, config)

    files = _load_files(args.path, language, fps, not args.no_recursive,
                       getattr(args, "pattern", None))
    if not files:
        print("未找到字幕文件")
        return 1

    for sf in files:
        zh_path, en_path = DualLanguageSplitter.split_and_save(sf, output_dir)
        print(f"已拆分 {sf.filepath}:")
        print(f"  中文: {zh_path}")
        print(f"  英文: {en_path}")

    return 0


def cmd_merge(args: argparse.Namespace, config: Config) -> int:
    if os.path.isfile(args.path):
        print("merge 命令需要指定目录")
        return 1

    segment_files = SubtitleMerger.find_segment_files(args.path, getattr(args, "merge_pattern", None))
    if not segment_files:
        print("未找到可合并的分段字幕文件")
        return 1

    print(f"找到 {len(segment_files)} 个分段文件:")
    for f in segment_files:
        print(f"  {os.path.basename(f)}")

    merged = SubtitleMerger.merge_files(segment_files, None, args.gap, args.output)
    print(f"\n已合并到: {merged.filepath}")
    print(f"共 {len(merged.entries)} 条字幕")
    return 0


def cmd_report(args: argparse.Namespace, config: Config) -> int:
    fps = _resolve_fps(args, config)
    language = _resolve_language(args, config)
    since_ts = parse_since(args.since) if getattr(args, "since", None) else None

    files = _load_files(args.path, language, fps, not args.no_recursive,
                       getattr(args, "pattern", None), since_ts)
    if not files:
        print("未找到字幕文件")
        return 1

    scanner = SubtitleScanner(config, fps=fps)
    result = scanner.scan_directory(files)

    default_output = f"subtitle_report.{args.format or 'html'}"
    report_path = _resolve_report_path(args, config, getattr(args, "output", None) or default_output)
    _save_report(result, report_path, fps, getattr(args, "format", None))
    print(f"报告已生成: {report_path}")
    print(f"扫描 {len(result.files)} 个文件，发现 {result.total_issues} 个问题")
    return 0


def cmd_ignore(args: argparse.Namespace, config: Config) -> int:
    action = getattr(args, "ignore_action", None)
    if action == "add":
        if not os.path.isfile(args.file):
            print(f"文件不存在: {args.file}")
            return 1
        fps = _resolve_fps(args, config)
        language = _resolve_language(args, config)
        sf = SubtitleParser.parse(args.file, language, fps)
        if not sf:
            print(f"无法解析字幕文件: {args.file}")
            return 1
        scanner = SubtitleScanner(config, fps=fps, use_ignore_list=False)
        scanner.scan_file(sf)
        target_line = getattr(args, "line", None)
        matched_issues = [
            i for i in sf.issues
            if i.subtitle_index == args.index
            and i.type.value == args.type
            and (target_line is None or i.line_number == target_line)
        ]
        if not matched_issues:
            print(f"未找到匹配的问题: #{args.index} [{args.type}]" +
                  (f" line={target_line}" if target_line else ""))
            print("请确认字幕编号、问题类型和行号是否正确")
            return 1
        issue = matched_issues[0]
        key = issue.get_key(sf.filepath)
        config.ignore_list.entries = [
            e for e in config.ignore_list.entries
            if not (e.get("key") == key and os.path.abspath(e.get("file", "")) == os.path.abspath(sf.filepath))
        ]
        content_hash = config.ignore_list.compute_content_hash(sf.filepath)
        config.ignore_list.entries.append({
            "key": key,
            "file": os.path.abspath(sf.filepath),
            "issue_type": issue.type.value,
            "subtitle_index": issue.subtitle_index,
            "line_number": issue.line_number,
            "start_ms": issue.details.get("start_ms"),
            "text_snippet": issue.details.get("text", "")[:50],
            "content_hash": content_hash,
            "reason": getattr(args, "reason", ""),
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        })
        config.save_ignore_list()
        type_label = ISSUE_TYPE_LABELS.get(IssueType(args.type), args.type)
        line_info = f" 第{issue.line_number}行" if issue.line_number else ""
        print(f"已添加忽略项: {os.path.basename(args.file)} #{args.index}{line_info} [{type_label}]")
        print(f"键值: {key}")
        if getattr(args, "reason", ""):
            print(f"原因: {args.reason}")
        return 0
    elif action == "list":
        if not config.ignore_list.entries:
            print("忽略清单为空")
            return 0
        print(f"忽略清单共 {len(config.ignore_list.entries)} 项:")
        for e in config.ignore_list.entries:
            type_label = ISSUE_TYPE_LABELS.get(IssueType(e.get("issue_type", "")), e.get("issue_type", ""))
            idx = e.get("subtitle_index", "?")
            reason = e.get("reason", "")
            fp = e.get("file", "")
            print(f"  #{idx} [{type_label}] {os.path.basename(fp)} {reason}")
        return 0
    elif action == "clear":
        if not config.ignore_list.entries:
            print("忽略清单为空")
            return 0
        config.ignore_list.clear()
        config.save_ignore_list()
        print("忽略清单已清空")
        return 0
    else:
        print("请指定动作: add / list / clear")
        print("  ignore add    - 添加忽略项")
        print("  ignore list   - 列出所有忽略项")
        print("  ignore clear  - 清空忽略清单")
        return 1


def _save_report(result: ScanResult, output_path: str, fps: float, fmt: Optional[str] = None) -> Optional[str]:
    try:
        if fmt is None:
            lower = output_path.lower()
            if lower.endswith(".json"):
                fmt = "json"
            elif lower.endswith(".csv"):
                fmt = "csv"
            elif lower.endswith(".html") or lower.endswith(".htm"):
                fmt = "html"
            else:
                fmt = "text"

        if fmt == "json":
            ReportGenerator.generate_json_report(result, output_path, fps)
        elif fmt == "csv":
            ReportGenerator.generate_csv_report(result, output_path, fps)
        elif fmt == "html":
            ReportGenerator.generate_html_report(result, output_path, fps)
        else:
            ReportGenerator.generate_text_report(result, output_path, fps)
        return output_path
    except Exception as e:
        print(f"警告: 保存报告失败 {output_path}: {e}")
        return None


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 1

    if args.command == "init":
        config = Config()
        return cmd_init(args, config)

    config = _resolve_config(args)

    commands = {
        "scan": cmd_scan,
        "fix": cmd_fix,
        "split": cmd_split,
        "merge": cmd_merge,
        "report": cmd_report,
        "ignore": cmd_ignore,
    }

    handler = commands.get(args.command)
    if handler:
        return handler(args, config)
    return 1
