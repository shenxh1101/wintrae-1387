import re
from typing import List, Dict, Set, Optional
from .models import (
    SubtitleFile,
    SubtitleEntry,
    Issue,
    IssueType,
    IssueSeverity,
    ScanResult,
)
from .config import Config
from .utils import format_timecode, format_frame, format_time_with_frames


class SubtitleScanner:
    def __init__(self, config: Config, fps: Optional[float] = None, use_ignore_list: bool = True):
        self.config = config
        self.fps = fps if fps is not None else config.get_fps()
        self.use_ignore_list = use_ignore_list
        self.ignore_list = config.ignore_list if use_ignore_list else None

    def scan_file(self, subtitle_file: SubtitleFile) -> SubtitleFile:
        subtitle_file.fps = self.fps
        raw_issues: List[Issue] = []
        raw_issues.extend(self._check_invalid_timecodes(subtitle_file))
        raw_issues.extend(self._check_duplicate_numbers(subtitle_file))
        raw_issues.extend(self._check_number_gaps(subtitle_file))
        raw_issues.extend(self._check_time_overlap(subtitle_file))
        raw_issues.extend(self._check_empty_entries(subtitle_file))
        raw_issues.extend(self._check_blank_lines(subtitle_file))
        raw_issues.extend(self._check_line_length(subtitle_file))
        raw_issues.extend(self._check_reading_speed(subtitle_file))
        raw_issues.extend(self._check_missing_punctuation(subtitle_file))
        raw_issues.extend(self._check_terminology(subtitle_file))

        filtered = self._filter_ignored(subtitle_file.filepath, raw_issues)
        subtitle_file.issues = sorted(
            filtered,
            key=lambda i: (i.subtitle_index or 0, i.type.value),
        )
        return subtitle_file

    def scan_directory(self, files: List[SubtitleFile]) -> ScanResult:
        result = ScanResult()
        for f in files:
            result.files.append(self.scan_file(f))
        return result

    def _filter_ignored(self, filepath: str, issues: List[Issue]) -> List[Issue]:
        if not self.ignore_list or len(self.ignore_list) == 0:
            return issues
        result = []
        for issue in issues:
            start_ms = issue.details.get("start_ms") if issue.subtitle_index else None
            text_snippet = issue.details.get("text")
            canonical = issue.details.get("canonical")
            variant = None
            used = issue.details.get("used_variants")
            if canonical and used:
                other = [v for v in used if v != canonical]
                variant = other[0] if other else used[0]
            if self.ignore_list.is_ignored(
                filepath=filepath,
                issue_type=issue.type.value,
                subtitle_index=issue.subtitle_index,
                line_number=issue.line_number,
                start_ms=start_ms,
                text=text_snippet,
                canonical=canonical,
                variant=variant,
            ):
                issue._ignored = True
                continue
            result.append(issue)
        return result

    def _check_invalid_timecodes(self, sf: SubtitleFile) -> List[Issue]:
        issues = []
        fps = sf.fps
        for i, entry in enumerate(sf.entries):
            if entry.start_time >= entry.end_time:
                issues.append(
                    Issue(
                        type=IssueType.INVALID_TIMECODE,
                        severity=IssueSeverity.ERROR,
                        message=f"时间轴无效 #{entry.index}：开始≥结束",
                        subtitle_index=entry.index,
                        details={
                            "start": format_time_with_frames(entry.start_time, fps),
                            "end": format_time_with_frames(entry.end_time, fps),
                            "start_ms": entry.start_time,
                            "end_ms": entry.end_time,
                            "start_frame": entry.start_frame(fps),
                            "end_frame": entry.end_frame(fps),
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
                        details={"first_at": seen[entry.index] + 1, "start_ms": entry.start_time},
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
                            details={
                                "expected": expected,
                                "actual": entry.index,
                                "start_ms": entry.start_time,
                            },
                        )
                    )
                expected = entry.index
            expected += 1
        return issues

    def _check_time_overlap(self, sf: SubtitleFile) -> List[Issue]:
        issues = []
        fps = sf.fps
        for i in range(1, len(sf.entries)):
            prev = sf.entries[i - 1]
            curr = sf.entries[i]
            if prev.end_time > curr.start_time:
                overlap = prev.end_time - curr.start_time
                overlap_frames = int(overlap * fps / 1000)
                issues.append(
                    Issue(
                        type=IssueType.OVERLAP,
                        severity=IssueSeverity.ERROR,
                        message=f"时间轴重叠 #{prev.index}→#{curr.index}，重叠 {overlap}ms/{overlap_frames}帧@{fps}fps",
                        subtitle_index=curr.index,
                        details={
                            "prev_index": prev.index,
                            "prev_end": format_time_with_frames(prev.end_time, fps),
                            "curr_start": format_time_with_frames(curr.start_time, fps),
                            "overlap_ms": overlap,
                            "overlap_frames": overlap_frames,
                            "fps": fps,
                            "start_ms": curr.start_time,
                        },
                    )
                )
        return issues

    def _check_empty_entries(self, sf: SubtitleFile) -> List[Issue]:
        issues = []
        fps = sf.fps
        for i, entry in enumerate(sf.entries):
            if not entry.text_lines:
                issues.append(
                    Issue(
                        type=IssueType.EMPTY_LINE,
                        severity=IssueSeverity.WARNING,
                        message=f"空字幕 #{entry.index}",
                        subtitle_index=entry.index,
                        details={
                            "start": format_time_with_frames(entry.start_time, fps),
                            "end": format_time_with_frames(entry.end_time, fps),
                            "start_ms": entry.start_time,
                        },
                    )
                )
            elif all(not line.strip() for line in entry.text_lines):
                issues.append(
                    Issue(
                        type=IssueType.EMPTY_LINE,
                        severity=IssueSeverity.WARNING,
                        message=f"空字幕 #{entry.index}（仅含空白行）",
                        subtitle_index=entry.index,
                        details={
                            "start": format_time_with_frames(entry.start_time, fps),
                            "end": format_time_with_frames(entry.end_time, fps),
                            "blank_count": len(entry.text_lines),
                            "start_ms": entry.start_time,
                        },
                    )
                )
        return issues

    def _check_blank_lines(self, sf: SubtitleFile) -> List[Issue]:
        issues = []
        for i, entry in enumerate(sf.entries):
            if not entry.text_lines:
                continue
            if all(not line.strip() for line in entry.text_lines):
                continue
            blank_indices = entry.blank_line_indices
            if blank_indices:
                issues.append(
                    Issue(
                        type=IssueType.BLANK_LINE,
                        severity=IssueSeverity.WARNING,
                        message=f"正文含空白行 #{entry.index}：第 {','.join(str(b + 1) for b in blank_indices)} 行为空",
                        subtitle_index=entry.index,
                        details={
                            "blank_line_positions": [b + 1 for b in blank_indices],
                            "total_lines": len(entry.text_lines),
                            "start_ms": entry.start_time,
                            "text": entry.full_text[:50],
                        },
                    )
                )
        return issues

    def _check_line_length(self, sf: SubtitleFile) -> List[Issue]:
        issues = []
        max_len = self.config.get_max_line_length(sf.language)
        for i, entry in enumerate(sf.entries):
            for j, line in enumerate(entry.text_lines):
                stripped = line.strip()
                if not stripped:
                    continue
                if len(stripped) > max_len:
                    issues.append(
                        Issue(
                            type=IssueType.LINE_TOO_LONG,
                            severity=IssueSeverity.WARNING,
                            message=f"单行过长 #{entry.index} 第{j + 1}行：{len(stripped)}字 > {max_len}字",
                            subtitle_index=entry.index,
                            line_number=j + 1,
                            details={
                                "length": len(stripped),
                                "max": max_len,
                                "line": j + 1,
                                "text": stripped,
                                "start_ms": entry.start_time,
                            },
                        )
                    )
        return issues

    def _check_reading_speed(self, sf: SubtitleFile) -> List[Issue]:
        issues = []
        min_duration = self.config.get_min_duration(sf.language)
        fps = sf.fps
        for i, entry in enumerate(sf.entries):
            non_blank = entry.non_blank_lines
            if not non_blank:
                continue
            num_lines = len(non_blank)
            min_needed = min_duration * num_lines
            if entry.duration < min_needed:
                duration_frames = int(entry.duration * fps / 1000)
                issues.append(
                    Issue(
                        type=IssueType.FAST_READING,
                        severity=IssueSeverity.WARNING,
                        message=f"阅读速度过快 #{entry.index}：{entry.duration}ms/{duration_frames}帧@{fps}fps < {min_needed}ms",
                        subtitle_index=entry.index,
                        details={
                            "duration_ms": entry.duration,
                            "duration_frames": duration_frames,
                            "fps": fps,
                            "min_needed_ms": min_needed,
                            "char_count": entry.char_count,
                            "lines": num_lines,
                            "start_ms": entry.start_time,
                            "text": entry.full_text[:50],
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
                                line_number=j + 1,
                                details={
                                    "line": j + 1,
                                    "text": stripped,
                                    "start_ms": entry.start_time,
                                },
                            )
                        )
        return issues

    def _is_sentence_end(self, text: str, lang: str) -> bool:
        if lang == "zh":
            if re.search(r"[\u4e00-\u9fff0-9]$", text):
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
        first_seen: Dict[str, Dict[str, Dict]] = {}
        for i, entry in enumerate(sf.entries):
            text = entry.full_text
            for canonical, variants in terms_map.items():
                for v in variants:
                    if v in text:
                        usage[canonical].add(v)
                        if canonical not in first_seen:
                            first_seen[canonical] = {}
                        if v not in first_seen[canonical]:
                            first_seen[canonical][v] = {
                                "start_ms": entry.start_time,
                                "entry_idx": entry.index,
                                "text": text,
                            }
        for canonical, used in usage.items():
            if len(used) > 1:
                earliest = None
                earliest_v = None
                for v in used:
                    info = first_seen.get(canonical, {}).get(v)
                    if info and (earliest is None or info["start_ms"] < earliest["start_ms"]):
                        earliest = info
                        earliest_v = v
                other_variants = sorted([v for v in used if v != canonical])
                sample_text = earliest["text"] if earliest else ""
                issues.append(
                    Issue(
                        type=IssueType.TERM_INCONSISTENCY,
                        severity=IssueSeverity.WARNING,
                        message=f"术语不统一：{canonical}，实际使用：{', '.join(sorted(used))}",
                        subtitle_index=earliest["entry_idx"] if earliest else None,
                        details={
                            "canonical": canonical,
                            "variant": other_variants[0] if other_variants else earliest_v,
                            "used_variants": list(used),
                            "start_ms": earliest["start_ms"] if earliest else None,
                            "text": sample_text[:200],
                        },
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
