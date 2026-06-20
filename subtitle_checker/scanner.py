import re
from typing import List, Dict, Set
from .models import (
    SubtitleFile,
    SubtitleEntry,
    Issue,
    IssueType,
    IssueSeverity,
    ScanResult,
)
from .config import Config
from .utils import is_chinese, format_timecode


class SubtitleScanner:
    def __init__(self, config: Config):
        self.config = config

    def scan_file(self, subtitle_file: SubtitleFile) -> SubtitleFile:
        subtitle_file.issues = []
        subtitle_file.issues.extend(self._check_invalid_timecodes(subtitle_file))
        subtitle_file.issues.extend(self._check_duplicate_numbers(subtitle_file))
        subtitle_file.issues.extend(self._check_number_gaps(subtitle_file))
        subtitle_file.issues.extend(self._check_time_overlap(subtitle_file))
        subtitle_file.issues.extend(self._check_empty_lines(subtitle_file))
        subtitle_file.issues.extend(self._check_line_length(subtitle_file))
        subtitle_file.issues.extend(self._check_reading_speed(subtitle_file))
        subtitle_file.issues.extend(self._check_missing_punctuation(subtitle_file))
        subtitle_file.issues.extend(self._check_terminology(subtitle_file))
        subtitle_file.issues.sort(key=lambda i: (i.subtitle_index or 0))
        return subtitle_file

    def scan_directory(self, files: List[SubtitleFile]) -> ScanResult:
        result = ScanResult()
        for f in files:
            result.files.append(self.scan_file(f))
        return result

    def _check_invalid_timecodes(self, sf: SubtitleFile) -> List[Issue]:
        issues = []
        for i, entry in enumerate(sf.entries):
            if entry.start_time >= entry.end_time:
                issues.append(
                    Issue(
                        type=IssueType.INVALID_TIMECODE,
                        severity=IssueSeverity.ERROR,
                        message=f"时间轴无效：开始时间大于或等于结束时间",
                        subtitle_index=entry.index,
                        details={
                            "start": format_timecode(entry.start_time),
                            "end": format_timecode(entry.end_time),
                        },
                    )
                )
        return issues

    def _check_duplicate_numbers(self, sf: SubtitleFile) -> List[Issue]:
        issues = []
        seen = {}
        for i, entry in enumerate(sf.entries):
            if entry.index in seen:
                issues.append(
                    Issue(
                        type=IssueType.DUPLICATE_NUMBER,
                        severity=IssueSeverity.WARNING,
                        message=f"重复的编号 #{entry.index}",
                        subtitle_index=entry.index,
                        details={"first_at": seen[entry.index] + 1},
                    )
                )
            else:
                seen[entry.index] = i
        return issues

    def _check_number_gaps(self, sf: SubtitleFile) -> List[Issue]:
        issues = []
        expected = 1
        for i, entry in enumerate(sf.entries):
            if entry.index != expected:
                if entry.index > expected:
                    issues.append(
                        Issue(
                            type=IssueType.NUMBER_GAP,
                            severity=IssueSeverity.WARNING,
                            message=f"编号断裂：期望 #{expected}，实际 #{entry.index}",
                            subtitle_index=entry.index,
                            details={"expected": expected, "actual": entry.index},
                        )
                    )
                expected = entry.index
            expected += 1
        return issues

    def _check_time_overlap(self, sf: SubtitleFile) -> List[Issue]:
        issues = []
        for i in range(1, len(sf.entries)):
            prev = sf.entries[i - 1]
            curr = sf.entries[i]
            if prev.end_time > curr.start_time:
                overlap = prev.end_time - curr.start_time
                issues.append(
                    Issue(
                        type=IssueType.OVERLAP,
                        severity=IssueSeverity.ERROR,
                        message=f"时间轴重叠 #{prev.index} 与 #{curr.index}，重叠 {overlap}ms",
                        subtitle_index=curr.index,
                        details={
                            "prev_index": prev.index,
                            "prev_end": format_timecode(prev.end_time),
                            "curr_start": format_timecode(curr.start_time),
                            "overlap_ms": overlap,
                        },
                    )
                )
        return issues

    def _check_empty_lines(self, sf: SubtitleFile) -> List[Issue]:
        issues = []
        for i, entry in enumerate(sf.entries):
            if not entry.text_lines or all(not line.strip() for line in entry.text_lines):
                issues.append(
                    Issue(
                        type=IssueType.EMPTY_LINE,
                        severity=IssueSeverity.WARNING,
                        message=f"空字幕 #{entry.index}",
                        subtitle_index=entry.index,
                    )
                )
        return issues

    def _check_line_length(self, sf: SubtitleFile) -> List[Issue]:
        issues = []
        max_len = self.config.get_max_line_length(sf.language)
        for i, entry in enumerate(sf.entries):
            for j, line in enumerate(entry.text_lines):
                stripped = line.strip()
                if len(stripped) > max_len:
                    issues.append(
                        Issue(
                            type=IssueType.LINE_TOO_LONG,
                            severity=IssueSeverity.WARNING,
                            message=f"单行过长 #{entry.index} 第{j + 1}行：{len(stripped)}字 > {max_len}字",
                            subtitle_index=entry.index,
                            details={"length": len(stripped), "max": max_len, "line": j + 1, "text": stripped},
                        )
                    )
        return issues

    def _check_reading_speed(self, sf: SubtitleFile) -> List[Issue]:
        issues = []
        speed_limit = self.config.get_reading_speed(sf.language)
        min_duration = self.config.get_min_duration(sf.language)
        for i, entry in enumerate(sf.entries):
            if not entry.text_lines:
                continue
            num_lines = len([l for l in entry.text_lines if l.strip()])
            min_needed = min_duration * max(1, num_lines)
            if entry.duration < min_needed:
                issues.append(
                    Issue(
                        type=IssueType.FAST_READING,
                        severity=IssueSeverity.WARNING,
                        message=f"阅读速度过快 #{entry.index}：{entry.duration}ms < {min_needed}ms",
                        subtitle_index=entry.index,
                        details={
                            "duration_ms": entry.duration,
                            "min_needed_ms": min_needed,
                            "char_count": entry.char_count,
                            "lines": num_lines,
                        },
                    )
                )
        return issues

    def _check_missing_punctuation(self, sf: SubtitleFile) -> List[Issue]:
        issues = []
        punct = self.config.data["punctuation_end"]
        for i, entry in enumerate(sf.entries):
            for j, line in enumerate(entry.text_lines):
                stripped = line.strip()
                if not stripped:
                    continue
                if len(stripped) < 3:
                    continue
                if stripped[-1] not in punct:
                    if self._is_sentence_end(stripped, sf.language):
                        issues.append(
                            Issue(
                                type=IssueType.MISSING_PUNCTUATION,
                                severity=IssueSeverity.INFO,
                                message=f"可能缺失标点 #{entry.index} 第{j + 1}行",
                                subtitle_index=entry.index,
                                details={"line": j + 1, "text": stripped},
                            )
                        )
        return issues

    def _is_sentence_end(self, text: str, lang: str) -> bool:
        if lang == "zh":
            if re.search(r"[。！？\u4e00-\u9fff0-9]$", text):
                return True
        else:
            if re.search(r"[a-zA-Z0-9]$", text):
                return True
        return False

    def _check_terminology(self, sf: SubtitleFile) -> List[Issue]:
        issues = []
        terms_map = self.config.get_all_term_variants(sf.language)
        if not terms_map:
            return issues
        usage: Dict[str, Set[str]] = {canonical: set() for canonical in terms_map}
        for i, entry in enumerate(sf.entries):
            text = entry.full_text
            for canonical, variants in terms_map.items():
                for v in variants:
                    if v in text:
                        usage[canonical].add(v)
        for canonical, used in usage.items():
            if len(used) > 1:
                issues.append(
                    Issue(
                        type=IssueType.TERM_INCONSISTENCY,
                        severity=IssueSeverity.WARNING,
                        message=f"术语不统一：{canonical}，实际使用：{', '.join(sorted(used))}",
                        details={"canonical": canonical, "used_variants": list(used)},
                    )
                )
        return issues

    def preview_range(
        self,
        subtitle_file: SubtitleFile,
        start_ms: int,
        end_ms: int,
    ) -> List[SubtitleEntry]:
        result = []
        for entry in subtitle_file.entries:
            if entry.end_time < start_ms:
                continue
            if entry.start_time > end_ms:
                break
            result.append(entry)
        return result
