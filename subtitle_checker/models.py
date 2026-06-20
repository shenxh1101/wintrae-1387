from dataclasses import dataclass, field
from typing import List, Optional, Dict
from enum import Enum


class IssueSeverity(Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class IssueType(Enum):
    OVERLAP = "overlap"
    EMPTY_LINE = "empty_line"
    NUMBER_GAP = "number_gap"
    LINE_TOO_LONG = "line_too_long"
    FAST_READING = "fast_reading"
    MISSING_PUNCTUATION = "missing_punctuation"
    TERM_INCONSISTENCY = "term_inconsistency"
    INVALID_TIMECODE = "invalid_timecode"
    DUPLICATE_NUMBER = "duplicate_number"


@dataclass
class Issue:
    type: IssueType
    severity: IssueSeverity
    message: str
    line_number: Optional[int] = None
    subtitle_index: Optional[int] = None
    details: Dict = field(default_factory=dict)


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
        return sum(len(line) for line in self.text_lines)

    @property
    def reading_speed(self) -> float:
        if self.duration <= 0:
            return float("inf")
        return (self.char_count / self.duration) * 1000


@dataclass
class SubtitleFile:
    filepath: str
    language: str
    entries: List[SubtitleEntry] = field(default_factory=list)
    issues: List[Issue] = field(default_factory=list)

    @property
    def duration(self) -> int:
        if not self.entries:
            return 0
        return self.entries[-1].end_time - self.entries[0].start_time


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
