from dataclasses import dataclass, field
from typing import List, Optional, Dict
from enum import Enum
import hashlib
import os


class IssueSeverity(Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class IssueStatus(Enum):
    UNRESOLVED = "unresolved"
    CONFIRMED = "confirmed"
    FIXED = "fixed"
    REJECTED = "rejected"


ISSUE_STATUS_LABELS = {
    IssueStatus.UNRESOLVED: "待处理",
    IssueStatus.CONFIRMED: "已确认",
    IssueStatus.FIXED: "已修复",
    IssueStatus.REJECTED: "不予处理",
}


class DiffStatus(Enum):
    NEW = "new"
    RESOLVED = "resolved"
    REMAINING = "remaining"


class IssueType(Enum):
    OVERLAP = "overlap"
    EMPTY_LINE = "empty_line"
    BLANK_LINE = "blank_line"
    NUMBER_GAP = "number_gap"
    LINE_TOO_LONG = "line_too_long"
    FAST_READING = "fast_reading"
    MISSING_PUNCTUATION = "missing_punctuation"
    TERM_INCONSISTENCY = "term_inconsistency"
    INVALID_TIMECODE = "invalid_timecode"
    DUPLICATE_NUMBER = "duplicate_number"


ISSUE_TYPE_LABELS = {
    IssueType.OVERLAP: "时间轴重叠",
    IssueType.EMPTY_LINE: "空字幕",
    IssueType.BLANK_LINE: "正文空白行",
    IssueType.NUMBER_GAP: "编号断裂",
    IssueType.LINE_TOO_LONG: "单行过长",
    IssueType.FAST_READING: "阅读速度过快",
    IssueType.MISSING_PUNCTUATION: "缺失标点",
    IssueType.TERM_INCONSISTENCY: "术语不统一",
    IssueType.INVALID_TIMECODE: "无效时间码",
    IssueType.DUPLICATE_NUMBER: "重复编号",
}

ISSUE_SUGGESTIONS = {
    IssueType.OVERLAP: "调整时间轴，消除重叠部分",
    IssueType.EMPTY_LINE: "删除空字幕条目或补充内容",
    IssueType.BLANK_LINE: "删除正文中的空白行",
    IssueType.NUMBER_GAP: "使用 fix 命令重新编号",
    IssueType.LINE_TOO_LONG: "拆分为多行或精简文字",
    IssueType.FAST_READING: "延长显示时间或精简文字",
    IssueType.MISSING_PUNCTUATION: "补充句末标点符号",
    IssueType.TERM_INCONSISTENCY: "统一术语译法，参照术语表",
    IssueType.INVALID_TIMECODE: "修正开始/结束时间",
    IssueType.DUPLICATE_NUMBER: "使用 fix 命令重新编号",
}


@dataclass
class Issue:
    type: IssueType
    severity: IssueSeverity
    message: str
    line_number: Optional[int] = None
    subtitle_index: Optional[int] = None
    details: Dict = field(default_factory=dict)
    status: IssueStatus = IssueStatus.UNRESOLVED
    note: str = ""
    _ignored: bool = False

    @property
    def suggestion(self) -> str:
        return ISSUE_SUGGESTIONS.get(self.type, "")

    @property
    def type_label(self) -> str:
        return ISSUE_TYPE_LABELS.get(self.type, self.type.value)

    @property
    def status_label(self) -> str:
        return ISSUE_STATUS_LABELS.get(self.status, self.status.value)

    def get_key(self, filepath: str) -> str:
        parts = [os.path.abspath(filepath), self.type.value]
        if self.subtitle_index is not None:
            parts.append(f"idx:{self.subtitle_index}")
        if self.line_number is not None:
            parts.append(f"line:{self.line_number}")
        if "start_ms" in self.details:
            parts.append(f"start:{self.details['start_ms']}")
        elif "start_frame" in self.details:
            parts.append(f"sf:{self.details['start_frame']}")
        if "text" in self.details:
            parts.append(f"text:{str(self.details['text']).strip()[:50]}")
        raw = "|".join(parts)
        return hashlib.md5(raw.encode("utf-8")).hexdigest()

    def get_term_key(self, filepath: str) -> Optional[str]:
        if self.type != IssueType.TERM_INCONSISTENCY:
            return None
        text = self.details.get("text", "")
        canon = self.details.get("canonical", "")
        variant = self.details.get("variant", "")
        if not (canon and variant and text):
            return None
        parts = [os.path.abspath(filepath), "term", canon.lower(), variant.lower()]
        raw = "|".join(parts)
        return hashlib.md5(raw.encode("utf-8")).hexdigest()


@dataclass
class SubtitleEntry:
    index: int
    start_time: int
    end_time: int
    text_lines: List[str]

    @property
    def duration(self) -> int:
        return self.end_time - self.start_time

    @property
    def full_text(self) -> str:
        return "\n".join(self.text_lines)

    @property
    def char_count(self) -> int:
        return sum(len(line) for line in self.text_lines if line.strip())

    @property
    def reading_speed(self) -> float:
        if self.duration <= 0:
            return float("inf")
        return (self.char_count / self.duration) * 1000

    @property
    def non_blank_lines(self) -> List[str]:
        return [l for l in self.text_lines if l.strip()]

    @property
    def blank_line_indices(self) -> List[int]:
        return [i for i, l in enumerate(self.text_lines) if l.strip() == ""]

    def start_frame(self, fps: float) -> int:
        return int(self.start_time * fps / 1000)

    def end_frame(self, fps: float) -> int:
        return int(self.end_time * fps / 1000)

    def align_to_frames(self, fps: float) -> "SubtitleEntry":
        self.start_time = int(round(self.start_time * fps / 1000) * 1000 / fps)
        self.end_time = int(round(self.end_time * fps / 1000) * 1000 / fps)
        if self.end_time <= self.start_time:
            self.end_time = self.start_time + int(round(1000 / fps))
        return self


@dataclass
class SubtitleFile:
    filepath: str
    language: str
    fps: float = 24.0
    entries: List[SubtitleEntry] = field(default_factory=list)
    issues: List[Issue] = field(default_factory=list)

    @property
    def duration(self) -> int:
        if not self.entries:
            return 0
        return self.entries[-1].end_time - self.entries[0].start_time

    @property
    def filename(self) -> str:
        return os.path.basename(self.filepath)

    def get_entry(self, index: int) -> Optional[SubtitleEntry]:
        for e in self.entries:
            if e.index == index:
                return e
        return None

    def get_context_entries(self, index: int, radius: int = 1) -> List[SubtitleEntry]:
        result = []
        for offset in range(-radius, radius + 1):
            target = index + offset
            entry = self.get_entry(target)
            if entry:
                result.append(entry)
        return result


@dataclass
class ScanResult:
    files: List[SubtitleFile] = field(default_factory=list)

    @property
    def total_issues(self) -> int:
        return sum(len(f.issues) for f in self.files)

    def get_issues_by_type(self, issue_type: IssueType) -> List[Issue]:
        result = []
        for f in self.files:
            result.extend([i for i in f.issues if i.type == issue_type])
        return result

    def get_issues_by_severity(self, severity: IssueSeverity) -> List[Issue]:
        result = []
        for f in self.files:
            result.extend([i for i in f.issues if i.severity == severity])
        return result

    @property
    def stats_by_type(self) -> Dict[IssueType, int]:
        from collections import Counter
        counter = Counter()
        for f in self.files:
            for i in f.issues:
                counter[i.type] += 1
        return dict(counter)

    @property
    def stats_by_severity(self) -> Dict[IssueSeverity, int]:
        from collections import Counter
        counter = Counter()
        for f in self.files:
            for i in f.issues:
                counter[i.severity] += 1
        return dict(counter)

    @property
    def stats_by_file(self) -> Dict[str, int]:
        return {f.filepath: len(f.issues) for f in self.files}


@dataclass
class BatchDiff:
    new_issues: List = field(default_factory=list)
    resolved_issues: List = field(default_factory=list)
    remaining_issues: List = field(default_factory=list)

    @property
    def new_count(self) -> int:
        return len(self.new_issues)

    @property
    def resolved_count(self) -> int:
        return len(self.resolved_issues)

    @property
    def remaining_count(self) -> int:
        return len(self.remaining_issues)
