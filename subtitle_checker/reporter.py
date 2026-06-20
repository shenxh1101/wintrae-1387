import os
import csv
import json
from typing import Optional, Dict, List
from .models import (
    ScanResult, IssueType, IssueSeverity, IssueStatus,
    ISSUE_TYPE_LABELS, ISSUE_SUGGESTIONS, ISSUE_STATUS_LABELS,
    SubtitleFile, Issue, SubtitleEntry, BatchDiff, DiffStatus,
)
from .utils import format_timecode, format_time_with_frames, format_frame
from datetime import datetime
from .batch import ReviewState


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

        status_counts = {"unresolved": 0, "confirmed": 0, "fixed": 0, "rejected": 0}
        for sf in result.files:
            for i in sf.issues:
                status_counts[i.status.value] = status_counts.get(i.status.value, 0) + 1
        lines.append("处理状态:")
        for k, label in [("unresolved", "待处理"), ("confirmed", "已确认"), ("fixed", "已修复"), ("rejected", "不予处理")]:
            if status_counts.get(k, 0):
                lines.append(f"  {label}: {status_counts[k]}")
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
                        status_tag = f"[{issue.status_label}]" if issue.status != IssueStatus.UNRESOLVED else ""
                        lines.append(f"    [{sev.value.upper():5s}] {idx} {issue.message} {status_tag}")
                        if issue.suggestion:
                            lines.append(f"           建议: {issue.suggestion}")
                        if issue.note:
                            lines.append(f"           备注: {issue.note}")
            lines.append("")

        text = "\n".join(lines)
        if output_path:
            try:
                parent = os.path.dirname(output_path)
                if parent:
                    os.makedirs(parent, exist_ok=True)
                with open(output_path, "w", encoding="utf-8-sig") as f:
                    f.write(text)
            except Exception as e:
                print(f"警告: 写入文本报告失败: {e}")
        return text

    @staticmethod
    def generate_json_report(result: ScanResult, output_path: Optional[str] = None, fps: float = 24.0) -> dict:
        data = {
            "generated_at": datetime.now().isoformat(),
            "fps": fps,
            "total_files": len(result.files),
            "total_issues": result.total_issues,
            "stats": {
                "by_type": {k.value: v for k, v in result.stats_by_type.items()},
                "by_severity": {k.value: v for k, v in result.stats_by_severity.items()},
                "by_file": result.stats_by_file,
            },
            "files": [],
        }
        for sf in result.files:
            fdata = {
                "filepath": sf.filepath,
                "filename": sf.filename,
                "language": sf.language,
                "fps": sf.fps,
                "entry_count": len(sf.entries),
                "issue_count": len(sf.issues),
                "issues": [],
            }
            for issue in sf.issues:
                fdata["issues"].append({
                    "key": issue.get_key(sf.filepath),
                    "type": issue.type.value,
                    "type_label": issue.type_label,
                    "severity": issue.severity.value,
                    "status": issue.status.value,
                    "status_label": issue.status_label,
                    "subtitle_index": issue.subtitle_index,
                    "line_number": issue.line_number,
                    "message": issue.message,
                    "suggestion": issue.suggestion,
                    "note": issue.note,
                    "details": issue.details,
                    "start_frame": format_frame(issue.details.get("start_ms"), fps) if issue.details.get("start_ms") is not None else None,
                })
            data["files"].append(fdata)
        if output_path:
            try:
                parent = os.path.dirname(output_path)
                if parent:
                    os.makedirs(parent, exist_ok=True)
                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            except Exception as e:
                print(f"警告: 写入 JSON 报告失败: {e}")
        return data

    @staticmethod
    def generate_csv_report(result: ScanResult, output_path: Optional[str] = None, fps: float = 24.0) -> str:
        rows = []
        header = [
            "文件名", "完整路径", "字幕编号", "行号", "开始时间", "开始帧",
            "问题类型", "严重程度", "处理状态", "问题描述", "建议", "备注",
        ]
        rows.append(header)
        for sf in result.files:
            for issue in sf.issues:
                start_ms = issue.details.get("start_ms")
                start_tc = format_timecode(start_ms) if start_ms is not None else ""
                start_f = format_frame(start_ms, fps) if start_ms is not None else ""
                rows.append([
                    sf.filename,
                    sf.filepath,
                    issue.subtitle_index if issue.subtitle_index is not None else "",
                    issue.line_number if issue.line_number is not None else "",
                    start_tc,
                    start_f,
                    issue.type_label,
                    {"error": "错误", "warning": "警告", "info": "信息"}.get(issue.severity.value, issue.severity.value),
                    issue.status_label,
                    issue.message,
                    issue.suggestion,
                    issue.note,
                ])
        csv_text = ""
        if output_path:
            try:
                parent = os.path.dirname(output_path)
                if parent:
                    os.makedirs(parent, exist_ok=True)
                with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerows(rows)
            except Exception as e:
                print(f"警告: 写入 CSV 报告失败: {e}")
        return "\n".join([",".join([str(c) for c in r]) for r in rows])

    @staticmethod
    def _build_issue_json(
        sf: SubtitleFile,
        issue: Issue,
        fps: float,
        base_dir: str,
        show_full_path: bool = False,
        batch_diff: Optional[BatchDiff] = None,
        diff_map: Optional[Dict[str, str]] = None,
    ) -> dict:
        abs_fp = os.path.abspath(sf.filepath)
        rel_fp = os.path.relpath(abs_fp, base_dir) if base_dir else sf.filename
        display_file = abs_fp if show_full_path else (rel_fp if base_dir else sf.filename)

        ctx_entries = sf.get_context_entries(issue.subtitle_index or 0, radius=2)
        ctx_html = ""
        for e in ctx_entries:
            is_target = e.index == issue.subtitle_index
            cls = "context-line context-target" if is_target else "context-line"
            sf_fps = sf.fps or fps
            start_f = format_frame(e.start_time, sf_fps)
            end_f = format_frame(e.end_time, sf_fps)
            lines_html = "<br>".join([
                ("&nbsp;" if not l.strip() else issue._html_escape if False else ReportGenerator._html_escape(l))
                for l in e.text_lines
            ])
            ctx_html += (
                f'<div class="{cls}"><span class="ctx-idx">#{e.index}</span> '
                f'<span class="ctx-tc">{format_timecode(e.start_time)} → {format_timecode(e.end_time)}</span> '
                f'<span class="ctx-frames">[{start_f}–{end_f}]</span>'
                f'<div class="ctx-text">{lines_html}</div></div>'
            )

        item = {
            "key": issue.get_key(sf.filepath),
            "file": sf.filename,
            "fileDisplay": display_file,
            "filePath": abs_fp,
            "fileRelPath": rel_fp,
            "type": issue.type.value,
            "typeLabel": issue.type_label,
            "severity": issue.severity.value,
            "status": issue.status.value,
            "statusLabel": issue.status_label,
            "subtitleIndex": issue.subtitle_index,
            "lineNumber": issue.line_number,
            "message": issue.message,
            "suggestion": issue.suggestion,
            "note": issue.note or "",
            "details": issue.details,
            "contextHtml": ctx_html,
            "diffStatus": "",
            "diffLabel": "",
        }
        if diff_map and item["key"] in diff_map:
            ds = diff_map[item["key"]]
            item["diffStatus"] = ds
            label_map = {"new": "🆕 新增", "resolved": "✅ 已解决", "remaining": "🔄 仍存在"}
            item["diffLabel"] = label_map.get(ds, "")
        return item

    @staticmethod
    def _html_escape(s) -> str:
        return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;").replace("'", "&#39;")

    @staticmethod
    def generate_html_report(
        result: ScanResult,
        output_path: Optional[str] = None,
        fps: float = 24.0,
        batch_diff: Optional[BatchDiff] = None,
        base_dir: Optional[str] = None,
    ) -> str:
        _base_dir = base_dir or (os.path.commonpath([
            os.path.abspath(sf.filepath) for sf in result.files
        ]) if result.files else ".")

        diff_map: Dict[str, str] = {}
        if batch_diff:
            for it in batch_diff.new_issues:
                diff_map[it["key"]] = "new"
            for it in batch_diff.remaining_issues:
                diff_map[it["key"]] = "remaining"

        issues_json = []
        status_options = [
            {"value": s.value, "label": ISSUE_STATUS_LABELS.get(s, s.value)}
            for s in IssueStatus
        ]
        for sf in result.files:
            for issue in sf.issues:
                issues_json.append(
                    ReportGenerator._build_issue_json(
                        sf, issue, fps, _base_dir, show_full_path=False, diff_map=diff_map
                    )
                )

        new_count = len(batch_diff.new_issues) if batch_diff else 0
        resolved_count = len(batch_diff.resolved_issues) if batch_diff else 0
        remaining_count = len(batch_diff.remaining_issues) if batch_diff else 0

        file_options = set()
        file_full_map: Dict[str, List[str]] = {}
        for it in issues_json:
            file_options.add(it["fileRelPath"])
            file_options.add(it["filePath"])
            abs_p = it["filePath"]
            rel_p = it["fileRelPath"]
            file_full_map.setdefault(rel_p, []).append(abs_p)

        type_options = sorted({it["typeLabel"] for it in issues_json})
        sev_options = [
            {"value": s.value, "label": {"error": "错误", "warning": "警告", "info": "信息"}.get(s.value, s.value)}
            for s in IssueSeverity
        ]
        status_opts_labeled = [
            {"value": s.value, "label": ISSUE_STATUS_LABELS.get(s, s.value)}
            for s in IssueStatus
        ]

        resolved_html = ""
        if batch_diff and batch_diff.resolved_issues:
            items_html = ""
            for it in batch_diff.resolved_issues:
                sev_label = {"error": "错误", "warning": "警告", "info": "信息"}.get("warning", "警告")
                t = ISSUE_TYPE_LABELS.get(
                    IssueType(it.get("issue_type", "")),
                    it.get("issue_type", "")
                ) if it.get("issue_type") else ""
                idx = f"#{it.get('subtitle_index', '?')}" if it.get("subtitle_index") else ""
                items_html += (
                    f'<div class="issue-item"><div class="issue-body" style="display:block;padding:12px 16px;">'
                    f'<span class="sev-badge resolved-badge">已解决</span>'
                    f'<span class="type-badge">{ReportGenerator._html_escape(t)}</span>'
                    f'<span class="issue-msg">{ReportGenerator._html_escape(idx)} {ReportGenerator._html_escape(it.get("message", ""))}</span>'
                    f'<span class="issue-meta">{ReportGenerator._html_escape(it.get("filename", ""))}</span>'
                    f'</div></div>'
                )
            resolved_html = f"""
<div class="diff-section">
  <div class="diff-header resolved-header">
    <span class="chevron" id="resolvedToggle" style="transform:rotate(90deg);">▶</span>
    <h3>✅ 已解决问题 <span class="diff-count">({resolved_count})</span></h3>
  </div>
  <div id="resolvedList" class="issue-list">{items_html}</div>
</div>"""

        status_summary = {s.value: 0 for s in IssueStatus}
        for it in issues_json:
            status_summary[it["status"]] = status_summary.get(it["status"], 0) + 1

        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>字幕翻译质量检查报告</title>
<style>
* {{ box-sizing: border-box; }}
body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
    margin: 0; padding: 20px; background: #f5f5f7; color: #1d1d1f;
}}
.container {{ max-width: 1280px; margin: 0 auto; }}
header {{ background: linear-gradient(135deg, #0071e3, #00c7be); color: #fff;
    padding: 24px 28px; border-radius: 12px; margin-bottom: 20px; }}
header h1 {{ margin: 0 0 6px; font-size: 22px; }}
header .meta {{ font-size: 13px; opacity: 0.9; }}
.stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 12px; margin-bottom: 20px; }}
.stat-card {{ background: #fff; padding: 16px; border-radius: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }}
.stat-card .label {{ font-size: 12px; color: #6e6e73; margin-bottom: 4px; }}
.stat-card .value {{ font-size: 26px; font-weight: 600; color: #1d1d1f; }}
.stat-card.error .value {{ color: #ff3b30; }}
.stat-card.warning .value {{ color: #ff9500; }}
.stat-card.info .value {{ color: #0071e3; }}
.stat-card.new-card .value {{ color: #34c759; }}
.stat-card.resolved-card .value {{ color: #30b0c7; }}
.stat-card.remaining-card .value {{ color: #af52de; }}
.filters {{ background: #fff; padding: 16px; border-radius: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); margin-bottom: 20px; }}
.filter-row {{ display: flex; flex-wrap: wrap; gap: 12px; align-items: center; }}
.filter-group {{ display: flex; align-items: center; gap: 6px; }}
.filter-group label {{ font-size: 13px; color: #6e6e73; }}
select, input[type="text"], textarea {{ padding: 6px 10px; border: 1px solid #d2d2d7; border-radius: 6px;
    font-size: 13px; background: #fff; font-family: inherit; }}
input[type="checkbox"] {{ cursor: pointer; }}
.issue-list {{ display: flex; flex-direction: column; gap: 10px; }}
.issue-item {{ background: #fff; border-radius: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.08);
    overflow: hidden; transition: box-shadow 0.2s; }}
.issue-item:hover {{ box-shadow: 0 2px 8px rgba(0,0,0,0.12); }}
.issue-item.diff-new {{ border-left: 4px solid #34c759; }}
.issue-item.diff-remaining {{ border-left: 4px solid #af52de; }}
.issue-header {{ display: flex; align-items: center; gap: 10px; padding: 12px 16px; cursor: pointer; user-select: none; }}
.issue-header:hover {{ background: #fafafa; }}
.sev-badge {{ padding: 3px 10px; border-radius: 12px; font-size: 12px; font-weight: 600;
    color: #fff; flex-shrink: 0; }}
.sev-badge.error {{ background: #ff3b30; }}
.sev-badge.warning {{ background: #ff9500; }}
.sev-badge.info {{ background: #0071e3; }}
.sev-badge.resolved-badge {{ background: #30b0c7; }}
.diff-badge {{ padding: 3px 8px; border-radius: 12px; font-size: 11px; font-weight: 600;
    color: #fff; flex-shrink: 0; }}
.diff-badge.new {{ background: #34c759; }}
.diff-badge.remaining {{ background: #af52de; }}
.type-badge {{ padding: 3px 10px; border-radius: 6px; font-size: 12px; background: #e5e5ea; color: #1d1d1f; }}
.status-badge {{ padding: 3px 8px; border-radius: 10px; font-size: 11px; font-weight: 600; flex-shrink: 0; }}
.status-badge.unresolved {{ background: #f2f2f7; color: #6e6e73; border: 1px solid #d2d2d7; }}
.status-badge.confirmed {{ background: #ffedd5; color: #9a3412; border: 1px solid #fdba74; }}
.status-badge.fixed {{ background: #dcfce7; color: #166534; border: 1px solid #86efac; }}
.status-badge.rejected {{ background: #fee2e2; color: #991b1b; border: 1px solid #fca5a5; }}
.issue-msg {{ flex: 1; font-size: 14px; }}
.issue-meta {{ font-size: 12px; color: #6e6e73; flex-shrink: 0; text-align: right; }}
.chevron {{ font-size: 18px; color: #6e6e73; transition: transform 0.2s; flex-shrink: 0; }}
.issue-item.expanded .chevron {{ transform: rotate(90deg); }}
.issue-body {{ display: none; padding: 0 16px 16px; border-top: 1px solid #f0f0f0; }}
.issue-item.expanded .issue-body {{ display: block; }}
.issue-section {{ margin-top: 12px; }}
.issue-section h4 {{ font-size: 13px; color: #6e6e73; margin: 0 0 6px; }}
.suggestion {{ background: #f0f9ff; border-left: 3px solid #0071e3; padding: 10px 12px;
    border-radius: 0 6px 6px 0; font-size: 13px; }}
.context-line {{ padding: 8px 10px; border-radius: 6px; margin-bottom: 4px; font-size: 13px; background: #fafafa; }}
.context-line.context-target {{ background: #fff4e5; border-left: 3px solid #ff9500; }}
.ctx-idx {{ font-weight: 600; color: #0071e3; margin-right: 6px; }}
.ctx-tc {{ color: #6e6e73; font-family: "SF Mono", Menlo, Consolas, monospace; margin-right: 8px; }}
.ctx-frames {{ color: #86868b; font-family: "SF Mono", Menlo, Consolas, monospace; font-size: 11px; }}
.ctx-text {{ margin-top: 4px; padding-left: 22px; color: #1d1d1f; line-height: 1.5; }}
.review-row {{ display: flex; flex-wrap: wrap; gap: 12px; align-items: flex-start; margin-top: 10px; }}
.review-row label {{ font-size: 12px; color: #6e6e73; margin-right: 4px; }}
.review-note {{ flex: 1; min-width: 200px; resize: vertical; min-height: 48px; }}
.review-actions {{ display: flex; gap: 8px; align-items: center; }}
.btn {{ padding: 6px 14px; border-radius: 6px; border: none; cursor: pointer;
    font-size: 13px; font-weight: 500; transition: all 0.15s; }}
.btn-primary {{ background: #0071e3; color: #fff; }}
.btn-primary:hover {{ background: #0077ed; }}
.btn-secondary {{ background: #e5e5ea; color: #1d1d1f; }}
.btn-secondary:hover {{ background: #d8d8dd; }}
.save-banner {{ position: fixed; bottom: 24px; right: 24px; background: #1d1d1f; color: #fff;
    padding: 10px 16px; border-radius: 8px; box-shadow: 0 4px 14px rgba(0,0,0,0.25);
    font-size: 13px; opacity: 0; transform: translateY(10px); transition: all 0.3s; pointer-events: none; z-index: 999; }}
.save-banner.show {{ opacity: 1; transform: translateY(0); }}
.diff-section {{ margin-bottom: 24px; }}
.diff-header {{ background: #fff; padding: 12px 16px; border-radius: 10px 10px 0 0;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08); cursor: pointer; display: flex; align-items: center; gap: 10px; }}
.diff-header h3 {{ margin: 0; font-size: 15px; }}
.diff-header.resolved-header {{ background: #e0f5f7; }}
.diff-count {{ font-weight: 400; font-size: 13px; color: #6e6e73; }}
.no-results {{ text-align: center; padding: 60px 20px; color: #6e6e73; font-size: 15px; }}
footer {{ margin-top: 30px; text-align: center; font-size: 12px; color: #86868b; }}
.toolbar {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; flex-wrap: wrap; gap: 10px; }}
.path-toggle {{ display: flex; align-items: center; gap: 6px; font-size: 13px; color: #6e6e73; }}
</style>
</head>
<body>
<div class="container">
<header>
    <h1>🎬 字幕翻译质量检查报告</h1>
    <div class="meta">
        生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ·
        帧率: {fps} fps ·
        文件: {len(result.files)} ·
        问题: {result.total_issues}
        {(f' · 🆕 新增 {new_count} ✅ 已解决 {resolved_count} 🔄 仍存在 {remaining_count}') if batch_diff else ''}
    </div>
</header>

<div class="stats">
    <div class="stat-card"><div class="label">总问题数</div><div class="value">{result.total_issues}</div></div>
    <div class="stat-card error"><div class="label">错误</div><div class="value">{len(result.get_issues_by_severity(IssueSeverity.ERROR))}</div></div>
    <div class="stat-card warning"><div class="label">警告</div><div class="value">{len(result.get_issues_by_severity(IssueSeverity.WARNING))}</div></div>
    <div class="stat-card info"><div class="label">信息</div><div class="value">{len(result.get_issues_by_severity(IssueSeverity.INFO))}</div></div>
    {f'<div class="stat-card new-card"><div class="label">新增</div><div class="value">{new_count}</div></div>' if batch_diff else ''}
    {f'<div class="stat-card resolved-card"><div class="label">已解决</div><div class="value">{resolved_count}</div></div>' if batch_diff else ''}
    {f'<div class="stat-card remaining-card"><div class="label">仍存在</div><div class="value">{remaining_count}</div></div>' if batch_diff else ''}
    <div class="stat-card"><div class="label">待处理</div><div class="value" style="color:#6e6e73">{status_summary.get("unresolved", 0)}</div></div>
    <div class="stat-card"><div class="label">已确认</div><div class="value" style="color:#ff9500">{status_summary.get("confirmed", 0)}</div></div>
    <div class="stat-card"><div class="label">已修复</div><div class="value" style="color:#34c759">{status_summary.get("fixed", 0)}</div></div>
</div>

<div class="filters">
    <div class="filter-row">
        <div class="filter-group"><label>文件:</label><select id="filterFile">
            <option value="">全部</option>
            {''.join(f'<option value="{ReportGenerator._html_escape(f)}">{ReportGenerator._html_escape(f)}</option>' for f in sorted(file_options))}
        </select></div>
        <div class="filter-group"><label>类型:</label><select id="filterType">
            <option value="">全部</option>
            {''.join(f'<option value="{ReportGenerator._html_escape(t)}">{ReportGenerator._html_escape(t)}</option>' for t in type_options)}
        </select></div>
        <div class="filter-group"><label>严重程度:</label><select id="filterSev">
            <option value="">全部</option>
            {''.join(f'<option value="{s["value"]}">{s["label"]}</option>' for s in sev_options)}
        </select></div>
        <div class="filter-group"><label>处理状态:</label><select id="filterStatus">
            <option value="">全部</option>
            {''.join(f'<option value="{s["value"]}">{s["label"]}</option>' for s in status_opts_labeled)}
        </select></div>
        <div class="filter-group"><label>搜索:</label><input type="text" id="filterSearch" placeholder="输入关键词..."></div>
    </div>
    <div class="toolbar" style="margin-top:12px;">
        <label class="path-toggle">
            <input type="checkbox" id="toggleFullPath"> 显示完整路径（区分同名字幕）
        </label>
        <div>
            <button class="btn btn-secondary" id="btnExportState">💾 导出备注/状态</button>
            <button class="btn btn-secondary" id="btnImportState">📂 导入备注/状态</button>
            <input type="file" id="fileImport" style="display:none;" accept=".json">
            <button class="btn btn-primary" id="btnSaveAll">✅ 保存到旁路文件</button>
        </div>
    </div>
</div>

{resolved_html}

<div id="issueList" class="issue-list"></div>
<div id="noResults" class="no-results" style="display:none;">没有符合条件的问题 ✓</div>

<footer>Generated by Subtitle Checker · {datetime.now().strftime('%Y-%m-%d')}</footer>
</div>
<div id="saveBanner" class="save-banner">✓ 已保存到旁路文件</div>

<script>
const ISSUES = {json.dumps(issues_json, ensure_ascii=False)};
const STATUS_OPTIONS = {json.dumps(status_options, ensure_ascii=False)};
const REPORT_OUTPUT_PATH = {json.dumps(output_path or "", ensure_ascii=False)};

const $f = id => document.getElementById(id);
const $html = ReportGenerator._html_escape.toString().includes("replace") ? null : null;
const statePath = (() => {{
    if (!REPORT_OUTPUT_PATH) return null;
    const i = REPORT_OUTPUT_PATH.lastIndexOf(".");
    return i > 0 ? REPORT_OUTPUT_PATH.slice(0, i) + "_review_state.json" : REPORT_OUTPUT_PATH + "_review_state.json";
}})();

let states = {{}};
let pendingTimeout = null;
let showFullPath = false;

function loadInitialStates() {{
    ISSUES.forEach(it => {{
        if (it.status !== "unresolved" || it.note) {{
            states[it.key] = {{ status: it.status, note: it.note || "" }};
        }}
    }});
}}
loadInitialStates();

function render() {{
    const file = $f('filterFile').value;
    const type = $f('filterType').value;
    const sev = $f('filterSev').value;
    const statusFilter = $f('filterStatus').value;
    const search = $f('filterSearch').value.toLowerCase().trim();
    showFullPath = $f('toggleFullPath').checked;

    const list = $f('issueList');
    const noResults = $f('noResults');
    list.innerHTML = '';

    const filtered = ISSUES.filter(it => {{
        const fileValue = showFullPath ? it.filePath : it.fileRelPath;
        if (file && fileValue !== file && it.file !== file) return false;
        if (type && it.typeLabel !== type) return false;
        if (sev && it.severity !== sev) return false;
        if (statusFilter && it.status !== statusFilter) return false;
        if (search) {{
            const hay = (it.message + ' ' + it.suggestion + ' ' + it.file + ' ' + it.fileRelPath + ' ' + it.statusLabel + ' ' + (it.note || '')).toLowerCase();
            if (!hay.includes(search)) return false;
        }}
        return true;
    }});

    noResults.style.display = filtered.length === 0 ? 'block' : 'none';

    for (const it of filtered) {{
        const st = states[it.key] || {{ status: "unresolved", note: "" }};
        const statusBadgeCls = `status-badge ${{st.status}}`;
        const statusLabel = (STATUS_OPTIONS.find(o => o.value === st.status) || {{}}).label || st.status;
        const fileDisplay = showFullPath ? it.filePath : it.fileRelPath;

        const diffClasses = [];
        if (it.diffStatus === "new") diffClasses.push("diff-new");
        if (it.diffStatus === "remaining") diffClasses.push("diff-remaining");
        const item = document.createElement('div');
        item.className = 'issue-item ' + diffClasses.join(' ');

        item.innerHTML = `
            <div class="issue-header">
                <span class="chevron">▶</span>
                ${{it.diffStatus === "new" ? '<span class="diff-badge new">新增</span>' : ''}}
                ${{it.diffStatus === "remaining" ? '<span class="diff-badge remaining">仍存在</span>' : ''}}
                <span class="sev-badge ${{it.severity}}">${{({{error:'错误',warning:'警告',info:'信息'}})[it.severity]}}</span>
                <span class="type-badge">${{_escape(it.typeLabel)}}</span>
                <span class="${{statusBadgeCls}}">${{statusLabel}}</span>
                <div class="issue-msg">${{_escape(it.message)}}</div>
                <div class="issue-meta">${{it.subtitleIndex ? '#'+it.subtitleIndex+' ' : ''}}${{_escape(fileDisplay)}}</div>
            </div>
            <div class="issue-body">
                ${{it.suggestion ? `<div class="issue-section"><h4>💡 建议处理方式</h4><div class="suggestion">${{_escape(it.suggestion)}}</div></div>` : ''}}
                <div class="issue-section">
                    <h4>📝 校对处理</h4>
                    <div class="review-row">
                        <label>状态:</label>
                        <select class="statusSelect" data-key="${{it.key}}">
                            ${{STATUS_OPTIONS.map(o => `<option value="${{o.value}}" ${{o.value === st.status ? 'selected' : ''}}>${{o.label}}</option>`).join('')}}
                        </select>
                        <button class="btn btn-secondary quickBtn" data-action="confirm" data-key="${{it.key}}">确认</button>
                        <button class="btn btn-secondary quickBtn" data-action="fix" data-key="${{it.key}}">已修</button>
                        <button class="btn btn-secondary quickBtn" data-action="reject" data-key="${{it.key}}">驳回</button>
                    </div>
                    <div class="review-row" style="margin-top:8px;">
                        <label style="align-self:flex-start;padding-top:8px;">备注:</label>
                        <textarea class="review-note" data-key="${{it.key}}" placeholder="输入校对备注，点击保存按钮或自动保存...">${{_escape(st.note || '')}}</textarea>
                    </div>
                </div>
                ${{it.contextHtml ? `<div class="issue-section"><h4>📝 上下文（±2条）</h4>${{it.contextHtml}}</div>` : ''}}
            </div>
        `;

        item.querySelector('.issue-header').addEventListener('click', (e) => {{
            if (e.target.tagName === 'SELECT' || e.target.tagName === 'BUTTON' || e.target.tagName === 'INPUT') return;
            item.classList.toggle('expanded');
        }});
        item.querySelectorAll('.statusSelect').forEach(sel => {{
            sel.addEventListener('click', e => e.stopPropagation());
            sel.addEventListener('change', e => {{
                const key = e.target.dataset.key;
                states[key] = {{ ...(states[key] || {{}}), status: e.target.value }};
                scheduleSave();
                render();
            }});
        }});
        item.querySelectorAll('.quickBtn').forEach(btn => {{
            btn.addEventListener('click', e => {{
                e.stopPropagation();
                const key = e.target.dataset.key;
                const action = e.target.dataset.action;
                const map = {{ confirm: "confirmed", fix: "fixed", reject: "rejected" }};
                states[key] = {{ ...(states[key] || {{}}), status: map[action] }};
                scheduleSave();
                render();
            }});
        }});
        item.querySelectorAll('.review-note').forEach(ta => {{
            ta.addEventListener('click', e => e.stopPropagation());
            ta.addEventListener('input', e => {{
                const key = e.target.dataset.key;
                states[key] = {{ ...(states[key] || {{}}), note: e.target.value }};
                scheduleSave();
            }});
        }});

        list.appendChild(item);
    }}
}}

function _escape(s) {{
    return String(s == null ? '' : s).replace(/[&<>"']/g, c => ({{
        '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
    }}[c]));
}}

function scheduleSave() {{
    if (pendingTimeout) clearTimeout(pendingTimeout);
    pendingTimeout = setTimeout(saveStates, 1200);
}}

function buildPayload() {{
    return {{
        generated_at: new Date().toISOString(),
        report_path: REPORT_OUTPUT_PATH,
        states: states,
    }};
}}

function saveStates() {{
    localStorage.setItem("subtitle_checker_state_last", JSON.stringify(buildPayload()));
    $f('saveBanner').classList.add('show');
    setTimeout(() => $f('saveBanner').classList.remove('show'), 1800);
}}

$F = id => document.getElementById(id);

['filterFile','filterType','filterSev','filterStatus','filterSearch'].forEach(id => {{
    $F(id).addEventListener('input', render);
    $F(id).addEventListener('change', render);
}});
$F('toggleFullPath').addEventListener('change', render);
$F('btnSaveAll').addEventListener('click', () => {{ saveStates(); }});
$F('btnExportState').addEventListener('click', () => {{
    const blob = new Blob([JSON.stringify(buildPayload(), null, 2)], {{ type: 'application/json' }});
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    const ts = new Date().toISOString().replace(/[:.]/g, '-');
    a.download = 'review_state_' + ts + '.json';
    a.click();
    URL.revokeObjectURL(url);
}});
$F('btnImportState').addEventListener('click', () => $F('fileImport').click());
$F('fileImport').addEventListener('change', (e) => {{
    const f = e.target.files[0]; if (!f) return;
    const reader = new FileReader();
    reader.onload = ev => {{
        try {{
            const data = JSON.parse(ev.target.result);
            if (data.states) {{
                Object.assign(states, data.states);
                scheduleSave();
                render();
                alert('已导入 ' + Object.keys(data.states).length + ' 条状态/备注');
            }}
        }} catch (e) {{ alert('导入失败: ' + e.message); }}
    }};
    reader.readAsText(f);
    e.target.value = '';
}});

if (document.getElementById('resolvedList')) {{
    const el = document.getElementById('resolvedToggle');
    const listEl = document.getElementById('resolvedList');
    let collapsed = false;
    if (el && el.parentElement) {{
        el.parentElement.addEventListener('click', () => {{
            collapsed = !collapsed;
            listEl.style.display = collapsed ? 'none' : 'flex';
            el.style.transform = collapsed ? '' : 'rotate(90deg)';
        }});
    }}
}}

render();
</script>
</body>
</html>"""
        if output_path:
            try:
                parent = os.path.dirname(output_path)
                if parent:
                    os.makedirs(parent, exist_ok=True)
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write(html)
            except Exception as e:
                print(f"警告: 写入 HTML 报告失败: {e}")
        return html

    @staticmethod
    def print_console_summary(result: ScanResult):
        print("=" * 60)
        print("扫描结果汇总")
        print("=" * 60)
        print(f"文件数: {len(result.files)} | 问题总数: {result.total_issues}")
        sev_stats = result.stats_by_severity
        label_map = {"error": "错误", "warning": "警告", "info": "信息"}
        parts = []
        for k, v in sev_stats.items():
            if v:
                parts.append(f"{label_map.get(k.value, k.value)}: {v}")
        print("严重程度: " + ", ".join(parts))

        print("问题类型分布:")
        type_stats = result.stats_by_type
        for k, v in type_stats.items():
            label = ISSUE_TYPE_LABELS.get(k, k.value)
            if v:
                print(f"  {label}: {v}")

        print("\n按文件:")
        for sf in result.files:
            print(f"  {sf.filename}: {len(sf.issues)}个问题")
        print("=" * 60)
