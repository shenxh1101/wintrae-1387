import os
import csv
import json
from typing import Optional
from .models import ScanResult, IssueType, IssueSeverity, ISSUE_TYPE_LABELS, ISSUE_SUGGESTIONS
from .utils import format_timecode, format_time_with_frames
from datetime import datetime


class ReportGenerator:
    @staticmethod
    def generate_text_report(result: ScanResult, output_path: Optional[str] = None, fps: float = 24.0) -> str:
        lines = []
        lines.append("=" * 70)
        lines.append("字幕翻译质量检查报告")
        lines.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"帧率: {fps} fps")
        lines.append("=" * 70)
        lines.append("")

        total_files = len(result.files)
        total_issues = result.total_issues
        lines.append(f"扫描文件数: {total_files}")
        lines.append(f"发现问题总数: {total_issues}")
        lines.append("")

        lines.append("-" * 70)
        lines.append("按严重程度统计:")
        for sev in IssueSeverity:
            count = len(result.get_issues_by_severity(sev))
            if count > 0:
                lines.append(f"  {sev.value}: {count}")
        lines.append("")

        lines.append("按问题类型统计:")
        for itype in IssueType:
            count = len(result.get_issues_by_type(itype))
            if count > 0:
                label = ISSUE_TYPE_LABELS.get(itype, itype.value)
                lines.append(f"  {label} ({itype.value}): {count}")
        lines.append("")

        lines.append("按文件统计:")
        for sf in result.files:
            lines.append(f"  {sf.filepath}: {len(sf.issues)} 个问题")
        lines.append("")

        for sf in result.files:
            lines.append("=" * 70)
            lines.append(f"文件: {sf.filepath}")
            lines.append(f"语言: {sf.language} | 帧率: {sf.fps}fps | 字幕条数: {len(sf.entries)} | 问题: {len(sf.issues)}")
            lines.append("")

            if not sf.issues:
                lines.append("  未发现问题 ✓")
            else:
                by_sev = {sev: [] for sev in IssueSeverity}
                for issue in sf.issues:
                    by_sev[issue.severity].append(issue)

                for sev in IssueSeverity:
                    issues = by_sev[sev]
                    if not issues:
                        continue
                    sev_label = {"error": "错误", "warning": "警告", "info": "信息"}.get(sev.value, sev.value)
                    lines.append(f"  {sev_label} ({len(issues)}):")
                    for issue in issues:
                        idx = f"#{issue.subtitle_index}" if issue.subtitle_index else ""
                        lines.append(f"    [{sev.value.upper():5s}] {idx} {issue.message}")
                        if issue.suggestion:
                            lines.append(f"           建议: {issue.suggestion}")
            lines.append("")

        text = "\n".join(lines)
        if output_path:
            with open(output_path, "w", encoding="utf-8-sig") as f:
                f.write(text)
        return text

    @staticmethod
    def generate_json_report(result: ScanResult, output_path: str, fps: float = 24.0) -> dict:
        data = {
            "generated_at": datetime.now().isoformat(),
            "fps": fps,
            "summary": {
                "total_files": len(result.files),
                "total_issues": result.total_issues,
                "by_severity": {},
                "by_type": {},
                "by_file": {},
            },
            "files": [],
        }

        for sf in result.files:
            data["summary"]["by_file"][sf.filepath] = len(sf.issues)

        for sf in result.files:
            file_data = {
                "filepath": sf.filepath,
                "language": sf.language,
                "fps": sf.fps,
                "entry_count": len(sf.entries),
                "issues": [],
            }
            for issue in sf.issues:
                sev = issue.severity.value
                t = issue.type.value
                data["summary"]["by_severity"][sev] = data["summary"]["by_severity"].get(sev, 0) + 1
                data["summary"]["by_type"][t] = data["summary"]["by_type"].get(t, 0) + 1
                file_data["issues"].append({
                    "type": issue.type.value,
                    "type_label": issue.type_label,
                    "severity": issue.severity.value,
                    "subtitle_index": issue.subtitle_index,
                    "line_number": issue.line_number,
                    "message": issue.message,
                    "suggestion": issue.suggestion,
                    "details": issue.details,
                })
            data["files"].append(file_data)

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return data

    @staticmethod
    def generate_csv_report(result: ScanResult, output_path: str, fps: float = 24.0) -> str:
        fieldnames = [
            "文件名", "字幕编号", "开始时间", "结束时间", "开始帧", "结束帧",
            "问题类型", "严重程度", "问题描述", "建议处理方式",
        ]
        rows = []
        for sf in result.files:
            for issue in sf.issues:
                entry = None
                if issue.subtitle_index:
                    for e in sf.entries:
                        if e.index == issue.subtitle_index:
                            entry = e
                            break
                if entry:
                    start_tc = format_timecode(entry.start_time)
                    end_tc = format_timecode(entry.end_time)
                    start_fr = entry.start_frame(sf.fps)
                    end_fr = entry.end_frame(sf.fps)
                else:
                    start_tc = ""
                    end_tc = ""
                    start_fr = ""
                    end_fr = ""
                rows.append({
                    "文件名": os.path.basename(sf.filepath),
                    "字幕编号": issue.subtitle_index or "",
                    "开始时间": start_tc,
                    "结束时间": end_tc,
                    "开始帧": start_fr,
                    "结束帧": end_fr,
                    "问题类型": issue.type_label,
                    "严重程度": issue.severity.value,
                    "问题描述": issue.message,
                    "建议处理方式": issue.suggestion,
                })

        with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

        return output_path

    @staticmethod
    def print_console_summary(result: ScanResult):
        print()
        print("=" * 60)
        print("扫描结果汇总")
        print("=" * 60)

        total = result.total_issues
        print(f"文件数: {len(result.files)} | 问题总数: {total}")

        by_sev = result.stats_by_severity
        parts = []
        for sev in IssueSeverity:
            if sev in by_sev:
                label = {"error": "错误", "warning": "警告", "info": "信息"}.get(sev.value, sev.value)
                parts.append(f"{label}: {by_sev[sev]}")
        if parts:
            print(f"严重程度: {', '.join(parts)}")

        by_type = result.stats_by_type
        if by_type:
            print("问题类型分布:")
            for itype, count in sorted(by_type.items(), key=lambda x: -x[1]):
                label = ISSUE_TYPE_LABELS.get(itype, itype.value)
                print(f"  {label}: {count}")

        print()
        print("按文件:")
        for sf in result.files:
            icon = "✓" if not sf.issues else f"{len(sf.issues)}个问题"
            print(f"  {sf.filename}: {icon}")

        print("=" * 60)
