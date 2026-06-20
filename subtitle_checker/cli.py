import argparse
import os
import sys
from typing import List, Optional
from .models import SubtitleFile
from .parser import SubtitleParser
from .scanner import SubtitleScanner
from .fixer import SubtitleFixer
from .splitter import DualLanguageSplitter
from .merger import SubtitleMerger
from .reporter import ReportGenerator
from .config import Config
from .utils import find_subtitle_files, get_output_path, parse_timecode, format_timecode


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="subtitle-checker",
        description="字幕翻译质量检查工具 - 批量检查和修复字幕文件",
    )
    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    scan_parser = subparsers.add_parser("scan", help="扫描字幕文件检查问题")
    _add_common_args(scan_parser)
    scan_parser.add_argument("--preview", type=str, default=None,
                            help="预览指定时间段的字幕，格式: HH:MM:SS,mmm-HH:MM:SS,mmm")
    scan_parser.add_argument("--report", type=str, default=None,
                            help="输出报告文件路径（支持 .txt 或 .json）")

    fix_parser = subparsers.add_parser("fix", help="自动修正常见格式问题")
    _add_common_args(fix_parser)
    fix_parser.add_argument("--output-dir", type=str, default=None,
                           help="修复后文件输出目录，默认在原文件同目录加_fixed后缀")
    fix_parser.add_argument("--suffix", type=str, default="_fixed",
                           help="输出文件后缀")

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
    merge_parser.add_argument("--pattern", type=str, default=None,
                             help="匹配分段文件的正则模式")

    report_parser = subparsers.add_parser("report", help="生成详细的问题报告")
    _add_common_args(report_parser)
    report_parser.add_argument("--output", type=str, default="subtitle_report.txt",
                              help="报告输出路径（.txt 或 .json）")
    report_parser.add_argument("--format", type=str, choices=["text", "json"],
                               default="text", help="报告格式")

    return parser


def _add_common_args(parser: argparse.ArgumentParser):
    parser.add_argument("path", type=str, nargs="?", default=".",
                       help="字幕文件或目录路径")
    parser.add_argument("--language", "-l", type=str, default=None,
                       choices=["zh", "en"],
                       help="指定字幕语言（zh/en），不指定则自动检测")
    parser.add_argument("--fps", type=float, default=24.0,
                       help="视频帧率（默认: 24）")
    parser.add_argument("--config", "-c", type=str, default=None,
                       help="配置文件路径（JSON）")
    parser.add_argument("--no-recursive", action="store_true",
                       help="不递归扫描子目录")


def _load_files(path: str, language: Optional[str], recursive: bool) -> List[SubtitleFile]:
    files = []
    if os.path.isfile(path):
        sf = SubtitleParser.parse(path, language)
        if sf:
            files.append(sf)
    else:
        subtitle_paths = find_subtitle_files(path, recursive=recursive)
        for fp in subtitle_paths:
            sf = SubtitleParser.parse(fp, language)
            if sf:
                files.append(sf)
    return files


def cmd_scan(args: argparse.Namespace, config: Config):
    files = _load_files(args.path, args.language, not args.no_recursive)
    if not files:
        print("未找到字幕文件")
        return 1

    scanner = SubtitleScanner(config)
    result = scanner.scan_directory(files)

    if args.preview:
        parts = args.preview.split("-")
        if len(parts) == 2:
            start = parse_timecode(parts[0])
            end = parse_timecode(parts[1])
            if start is not None and end is not None:
                for sf in files:
                    print(f"\n预览 {sf.filepath} [{format_timecode(start)} - {format_timecode(end)}]:")
                    previews = scanner.preview_range(sf, start, end)
                    for e in previews:
                        print(f"  #{e.index} {format_timecode(e.start_time)} --> {format_timecode(e.end_time)}")
                        for line in e.text_lines:
                            print(f"    {line}")

    ReportGenerator.print_console_summary(result)

    for sf in result.files:
        print(f"\n{sf.filepath} ({len(sf.issues)} 个问题)")
        for issue in sf.issues:
            sev = issue.severity.value.upper()
            idx = f"#{issue.subtitle_index}" if issue.subtitle_index else ""
            print(f"  [{sev}] {idx} {issue.message}")

    if args.report:
        if args.report.endswith(".json"):
            ReportGenerator.generate_json_report(result, args.report)
        else:
            ReportGenerator.generate_text_report(result, args.report)
        print(f"\n报告已保存到: {args.report}")
    return 0


def cmd_fix(args: argparse.Namespace, config: Config):
    files = _load_files(args.path, args.language, not args.no_recursive)
    if not files:
        print("未找到字幕文件")
        return 1

    fixer = SubtitleFixer(config)
    scanner = SubtitleScanner(config)

    for sf in files:
        fixed = fixer.fix_file(sf)
        if args.output_dir:
            os.makedirs(args.output_dir, exist_ok=True)
            out_name = os.path.basename(sf.filepath)
            base, ext = os.path.splitext(out_name)
            out_path = os.path.join(args.output_dir, base + args.suffix + ext)
        else:
            out_path = get_output_path(sf.filepath, args.suffix)
        SubtitleParser.write_srt(fixed, out_path)
        print(f"修复并保存: {out_path}")

        scan_result = scanner.scan_file(fixed)
        remaining = len(scan_result.issues)
        if remaining > 0:
            print(f"  仍有 {remaining} 个问题需手动处理")
        else:
            print(f"  所有问题已自动修复 ✓")

    print(f"\n共处理 {len(files)} 个文件")
    return 0


def cmd_split(args: argparse.Namespace, config: Config):
    files = _load_files(args.path, args.language, not args.no_recursive)
    if not files:
        print("未找到字幕文件")
        return 1

    for sf in files:
        zh_path, en_path = DualLanguageSplitter.split_and_save(sf, args.output_dir)
        print(f"已拆分 {sf.filepath}:")
        print(f"  中文: {zh_path}")
        print(f"  英文: {en_path}")

    return 0


def cmd_merge(args: argparse.Namespace, config: Config):
    if os.path.isfile(args.path):
        print("merge 命令需要指定目录")
        return 1

    segment_files = SubtitleMerger.find_segment_files(args.path, args.pattern)
    if not segment_files:
        print("未找到可合并的分段字幕文件")
        return 1

    print(f"找到 {len(segment_files)} 个分段文件:")
    for f in segment_files:
        print(f"  {os.path.basename(f)}")

    merged = SubtitleMerger.merge_files(segment_files, args.language, args.gap, args.output)
    print(f"\n已合并到: {merged.filepath}")
    print(f"共 {len(merged.entries)} 条字幕")
    return 0


def cmd_report(args: argparse.Namespace, config: Config):
    files = _load_files(args.path, args.language, not args.no_recursive)
    if not files:
        print("未找到字幕文件")
        return 1

    scanner = SubtitleScanner(config)
    result = scanner.scan_directory(files)

    if args.format == "json" or args.output.endswith(".json"):
        ReportGenerator.generate_json_report(result, args.output)
    else:
        ReportGenerator.generate_text_report(result, args.output)

    print(f"报告已生成: {args.output}")
    print(f"扫描 {len(result.files)} 个文件，发现 {result.total_issues} 个问题")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 1

    config = Config(args.config)

    commands = {
        "scan": cmd_scan,
        "fix": cmd_fix,
        "split": cmd_split,
        "merge": cmd_merge,
        "report": cmd_report,
    }

    handler = commands.get(args.command)
    if handler:
        return handler(args, config)
    return 1
