import os
import csv
import json
from typing import Optional
from .models import ScanResult, IssueType, IssueSeverity, ISSUE_TYPE_LABELS, ISSUE_SUGGESTIONS, SubtitleFile, Issue, SubtitleEntry
from .utils import format_timecode, format_time_with_frames, format_frame
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
            try:
                with open(output_path, "w", encoding="utf-8-sig") as f:
                    f.write(text)
            except Exception as e:
                print(f"警告: 写入文本报告失败: {e}")
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

        try:
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"警告: 写入JSON报告失败: {e}")
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

        try:
            with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
        except Exception as e:
            print(f"警告: 写入CSV报告失败: {e}")

        return output_path

    @staticmethod
    def generate_html_report(result: ScanResult, output_path: str, fps: float = 24.0) -> str:
        all_files = [sf.filename for sf in result.files]
        all_types = []
        for it in IssueType:
            if len(result.get_issues_by_type(it)) > 0:
                all_types.append(ISSUE_TYPE_LABELS.get(it, it.value))
        all_sevs = [sev.value for sev in IssueSeverity if len(result.get_issues_by_severity(sev)) > 0]

        issues_json = []
        for sf in result.files:
            for issue in sf.issues:
                entry = sf.get_entry(issue.subtitle_index) if issue.subtitle_index else None
                context_entries = sf.get_context_entries(issue.subtitle_index, radius=2) if issue.subtitle_index else []
                context_html = []
                for ctx in context_entries:
                    is_target = ctx.index == issue.subtitle_index
                    cls = "context-line context-target" if is_target else "context-line"
                    tc = f"{format_timecode(ctx.start_time)} → {format_timecode(ctx.end_time)}"
                    frame_info = f"[{format_frame(ctx.start_time, sf.fps)}–{format_frame(ctx.end_time, sf.fps)}]"
                    lines_html = "<br>".join(_html_escape(l) if l.strip() else "&nbsp;" for l in ctx.text_lines)
                    context_html.append(
                        f'<div class="{cls}">'
                        f'<span class="ctx-idx">#{ctx.index}</span> '
                        f'<span class="ctx-tc">{tc}</span> '
                        f'<span class="ctx-frames">{frame_info}</span>'
                        f'<div class="ctx-text">{lines_html}</div>'
                        f'</div>'
                    )
                issues_json.append({
                    "file": sf.filename,
                    "filePath": sf.filepath,
                    "type": issue.type.value,
                    "typeLabel": issue.type_label,
                    "severity": issue.severity.value,
                    "subtitleIndex": issue.subtitle_index,
                    "lineNumber": issue.line_number,
                    "message": issue.message,
                    "suggestion": issue.suggestion,
                    "details": issue.details,
                    "contextHtml": "".join(context_html),
                })

        sev_labels = {"error": "错误", "warning": "警告", "info": "信息"}

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
.container {{ max-width: 1200px; margin: 0 auto; }}
header {{ background: linear-gradient(135deg, #0071e3, #00c7be); color: #fff;
    padding: 24px 28px; border-radius: 12px; margin-bottom: 20px; }}
header h1 {{ margin: 0 0 6px; font-size: 22px; }}
header .meta {{ font-size: 13px; opacity: 0.9; }}
.stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 12px; margin-bottom: 20px; }}
.stat-card {{ background: #fff; padding: 16px; border-radius: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }}
.stat-card .label {{ font-size: 12px; color: #6e6e73; margin-bottom: 4px; }}
.stat-card .value {{ font-size: 26px; font-weight: 600; color: #1d1d1f; }}
.stat-card.error .value {{ color: #ff3b30; }}
.stat-card.warning .value {{ color: #ff9500; }}
.stat-card.info .value {{ color: #0071e3; }}
.filters {{ background: #fff; padding: 16px; border-radius: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); margin-bottom: 20px; }}
.filter-row {{ display: flex; flex-wrap: wrap; gap: 12px; align-items: center; }}
.filter-group {{ display: flex; align-items: center; gap: 6px; }}
.filter-group label {{ font-size: 13px; color: #6e6e73; }}
select, input[type="text"] {{ padding: 6px 10px; border: 1px solid #d2d2d7; border-radius: 6px;
    font-size: 13px; background: #fff; }}
.issue-list {{ display: flex; flex-direction: column; gap: 10px; }}
.issue-item {{ background: #fff; border-radius: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.08);
    overflow: hidden; transition: box-shadow 0.2s; }}
.issue-item:hover {{ box-shadow: 0 2px 8px rgba(0,0,0,0.12); }}
.issue-header {{ display: flex; align-items: center; gap: 10px; padding: 12px 16px; cursor: pointer; user-select: none; }}
.issue-header:hover {{ background: #fafafa; }}
.sev-badge {{ padding: 3px 10px; border-radius: 12px; font-size: 12px; font-weight: 600;
    color: #fff; flex-shrink: 0; }}
.sev-badge.error {{ background: #ff3b30; }}
.sev-badge.warning {{ background: #ff9500; }}
.sev-badge.info {{ background: #0071e3; }}
.type-badge {{ padding: 3px 10px; border-radius: 6px; font-size: 12px; background: #e5e5ea; color: #1d1d1f; }}
.issue-msg {{ flex: 1; font-size: 14px; }}
.issue-meta {{ font-size: 12px; color: #6e6e73; flex-shrink: 0; text-align: right; }}
.chevron {{ font-size: 18px; color: #6e6e73; transition: transform 0.2s; }}
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
.no-results {{ text-align: center; padding: 60px 20px; color: #6e6e73; font-size: 15px; }}
footer {{ margin-top: 30px; text-align: center; font-size: 12px; color: #86868b; }}
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
    </div>
</header>

<div class="stats">
    <div class="stat-card">
        <div class="label">总问题数</div>
        <div class="value">{result.total_issues}</div>
    </div>
    <div class="stat-card error">
        <div class="label">错误</div>
        <div class="value">{len(result.get_issues_by_severity(IssueSeverity.ERROR))}</div>
    </div>
    <div class="stat-card warning">
        <div class="label">警告</div>
        <div class="value">{len(result.get_issues_by_severity(IssueSeverity.WARNING))}</div>
    </div>
    <div class="stat-card info">
        <div class="label">信息</div>
        <div class="value">{len(result.get_issues_by_severity(IssueSeverity.INFO))}</div>
    </div>
</div>

<div class="filters">
    <div class="filter-row">
        <div class="filter-group">
            <label>文件:</label>
            <select id="filterFile">
                <option value="">全部</option>
                {''.join(f'<option value="{_html_escape(f)}">{_html_escape(f)}</option>' for f in all_files)}
            </select>
        </div>
        <div class="filter-group">
            <label>类型:</label>
            <select id="filterType">
                <option value="">全部</option>
                {''.join(f'<option value="{_html_escape(t)}">{_html_escape(t)}</option>' for t in all_types)}
            </select>
        </div>
        <div class="filter-group">
            <label>严重程度:</label>
            <select id="filterSev">
                <option value="">全部</option>
                {''.join(f'<option value="{s}">{sev_labels.get(s, s)}</option>' for s in all_sevs)}
            </select>
        </div>
        <div class="filter-group">
            <label>搜索:</label>
            <input type="text" id="filterSearch" placeholder="输入关键词...">
        </div>
    </div>
</div>

<div id="issueList" class="issue-list"></div>
<div id="noResults" class="no-results" style="display:none;">没有符合条件的问题 ✓</div>

<footer>Generated by Subtitle Checker · {datetime.now().strftime('%Y-%m-%d')}</footer>
</div>

<script>
const ISSUES = {json.dumps(issues_json, ensure_ascii=False)};

const $f = id => document.getElementById(id);

function render() {{
    const file = $f('filterFile').value;
    const type = $f('filterType').value;
    const sev = $f('filterSev').value;
    const search = $f('filterSearch').value.toLowerCase().trim();

    const list = $f('issueList');
    const noResults = $f('noResults');
    list.innerHTML = '';

    const filtered = ISSUES.filter(it => {{
        if (file && it.file !== file) return false;
        if (type && it.typeLabel !== type) return false;
        if (sev && it.severity !== sev) return false;
        if (search) {{
            const hay = (it.message + ' ' + it.suggestion + ' ' + it.file).toLowerCase();
            if (!hay.includes(search)) return false;
        }}
        return true;
    }});

    noResults.style.display = filtered.length === 0 ? 'block' : 'none';

    for (const issue of filtered) {{
        const item = document.createElement('div');
        item.className = 'issue-item';
        const sevText = {{
            error: '错误', warning: '警告', info: '信息'
        }}[issue.severity] || issue.severity;

        let meta = '';
        if (issue.subtitleIndex) meta += `#${{issue.subtitleIndex}} `;
        meta += issue.file;

        item.innerHTML = `
            <div class="issue-header">
                <span class="chevron">▶</span>
                <span class="sev-badge ${{issue.severity}}">${{sevText}}</span>
                <span class="type-badge">${{issue.typeLabel}}</span>
                <div class="issue-msg">${{_html_escape(issue.message)}}</div>
                <div class="issue-meta">${{_html_escape(meta)}}</div>
            </div>
            <div class="issue-body">
                ${{issue.suggestion ? `<div class="issue-section"><h4>💡 建议处理方式</h4><div class="suggestion">${{_html_escape(issue.suggestion)}}</div></div>` : ''}}
                ${{issue.contextHtml ? `<div class="issue-section"><h4>📝 上下文（±2条）</h4>${{issue.contextHtml}}</div>` : ''}}
            </div>
        `;

        item.querySelector('.issue-header').addEventListener('click', () => {{
            item.classList.toggle('expanded');
        }});

        list.appendChild(item);
    }}
}}

function _html_escape(s) {{
    return String(s).replace(/[&<>"']/g, c => ({{
        '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
    }}[c]));
}}

['filterFile', 'filterType', 'filterSev', 'filterSearch'].forEach(id => {{
    $f(id).addEventListener('input', render);
    $f(id).addEventListener('change', render);
}});

render();
</script>
</body>
</html>"""
        try:
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(html)
        except Exception as e:
            print(f"警告: 写入HTML报告失败: {e}")
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


def _html_escape(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;").replace("'", "&#39;")
