import os
import json
from typing import Optional
from .models import ScanResult, IssueType, IssueSeverity
from datetime import datetime


class ReportGenerator:
    @staticmethod
    def generate_text_report(result: ScanResult, output_path: Optional[str] = None) -> str:
        lines = []
        lines.append("=" * 60)
        lines.append("字幕翻译质量检查报告")
        lines.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("=" * 60)
        lines.append("")

        total_files = len(result.files)
        total_issues = result.total_issues
        lines.append(f"扫描文件数: {total_files}")
        lines.append(f"发现问题总数: {total_issues}")
        lines.append("")

        for sf in result.files:
            lines.append("-" * 60)
            lines.append(f"文件: {sf.filepath}")
            lines.append(f"语言: {sf.language} | 字幕条数: {len(sf.entries)} | 问题: {len(sf.issues)}")
            lines.append("")

            if not sf.issues:
                lines.append("  未发现问题 ✓")
            else:
                errors = [i for i in sf.issues if i.severity == IssueSeverity.ERROR]
                warnings = [i for i in sf.issues if i.severity == IssueSeverity.WARNING]
                infos = [i for i in sf.issues if i.severity == IssueSeverity.INFO]

                if errors:
                    lines.append(f"  错误 ({len(errors)}):")
                    for issue in errors:
                        idx = f"#{issue.subtitle_index}" if issue.subtitle_index else ""
                        lines.append(f"    [ERROR] {idx} {issue.message}")
                if warnings:
                    lines.append(f"  警告 ({len(warnings)}):")
                    for issue in warnings:
                        idx = f"#{issue.subtitle_index}" if issue.subtitle_index else ""
                        lines.append(f"    [WARN ] {idx} {issue.message}")
                if infos:
                    lines.append(f"  信息 ({len(infos)}):")
                    for issue in infos:
                        idx = f"#{issue.subtitle_index}" if issue.subtitle_index else ""
                        lines.append(f"    [INFO ] {idx} {issue.message}")
            lines.append("")

        lines.append("=" * 60)
        lines.append("问题类型统计:")
        lines.append("=" * 60)
        for itype in IssueType:
            count = len(result.get_issues_by_type(itype))
            if count > 0:
                lines.append(f"  {itype.value}: {count}")

        text = "\n".join(lines)
        if output_path:
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(text)
        return text

    @staticmethod
    def generate_json_report(result: ScanResult, output_path: str) -> dict:
        data = {
            "generated_at": datetime.now().isoformat(),
            "summary": {
                "total_files": len(result.files),
                "total_issues": result.total_issues,
                "by_severity": {
                    "error": 0,
                    "warning": 0,
                    "info": 0,
                },
                "by_type": {},
            },
            "files": [],
        }

        for sf in result.files:
            file_data = {
                "filepath": sf.filepath,
                "language": sf.language,
                "entry_count": len(sf.entries),
                "issues": [],
            }
            for issue in sf.issues:
                data["summary"]["by_severity"][issue.severity.value] += 1
                t = issue.type.value
                if t not in data["summary"]["by_type"]:
                    data["summary"]["by_type"][t] = 0
                data["summary"]["by_type"][t] += 1
                file_data["issues"].append({
                    "type": issue.type.value,
                    "severity": issue.severity.value,
                    "subtitle_index": issue.subtitle_index,
                    "line_number": issue.line_number,
                    "message": issue.message,
                    "details": issue.details,
                })
            data["files"].append(file_data)

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return data

    @staticmethod
    def print_console_summary(result: ScanResult):
        total = result.total_issues
        errors = 0
        warnings = 0
        infos = 0
        for sf in result.files:
            for i in sf.issues:
                if i.severity == IssueSeverity.ERROR:
                    errors += 1
                elif i.severity == IssueSeverity.WARNING:
                    warnings += 1
                else:
                    infos += 1
        print(f"\n扫描完成: {len(result.files)} 个文件, "
              f"发现 {total} 个问题 "
              f"(错误: {errors}, 警告: {warnings}, 信息: {infos})")
