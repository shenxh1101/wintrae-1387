import re
from typing import List
from copy import deepcopy
from .models import SubtitleFile, SubtitleEntry, Issue, IssueType
from .utils import format_timecode
from .config import Config


class SubtitleFixer:
    def __init__(self, config: Config, fps: float = None):
        self.config = config
        self.fps = fps if fps is not None else config.get_fps()

    def fix_file(self, subtitle_file: SubtitleFile) -> SubtitleFile:
        fixed = deepcopy(subtitle_file)
        fixed.fps = self.fps
        fixed = self._fix_invalid_timecodes(fixed)
        fixed = self._fix_time_overlap(fixed)
        fixed = self._remove_blank_lines_from_text(fixed)
        fixed = self._remove_empty_entries(fixed)
        fixed = self._renumber_entries(fixed)
        fixed = self._fix_trailing_whitespace(fixed)
        return fixed

    def _renumber_entries(self, sf: SubtitleFile) -> SubtitleFile:
        for i, entry in enumerate(sf.entries):
            entry.index = i + 1
        return sf

    def _fix_invalid_timecodes(self, sf: SubtitleFile) -> SubtitleFile:
        for entry in sf.entries:
            if entry.end_time <= entry.start_time:
                entry.end_time = entry.start_time + 1000
        return sf

    def _fix_time_overlap(self, sf: SubtitleFile) -> SubtitleFile:
        fps = sf.fps
        for i in range(1, len(sf.entries)):
            prev = sf.entries[i - 1]
            curr = sf.entries[i]
            if prev.end_time > curr.start_time:
                curr.start_time = prev.end_time
                if curr.end_time <= curr.start_time:
                    curr.end_time = curr.start_time + 500
        return sf

    def _remove_blank_lines_from_text(self, sf: SubtitleFile) -> SubtitleFile:
        for entry in sf.entries:
            entry.text_lines = [l for l in entry.text_lines if l.strip()]
        return sf

    def _remove_empty_entries(self, sf: SubtitleFile) -> SubtitleFile:
        sf.entries = [
            e for e in sf.entries
            if e.text_lines and any(l.strip() for l in e.text_lines)
        ]
        return sf

    def _fix_trailing_whitespace(self, sf: SubtitleFile) -> SubtitleFile:
        for entry in sf.entries:
            entry.text_lines = [l.rstrip() for l in entry.text_lines]
        return sf

    def normalize_spacing(self, sf: SubtitleFile) -> SubtitleFile:
        for entry in sf.entries:
            new_lines = []
            for line in entry.text_lines:
                line = re.sub(r"\s+", " ", line.strip())
                new_lines.append(line)
            entry.text_lines = new_lines
        return sf
