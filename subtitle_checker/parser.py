import os
import re
from typing import List, Optional, Tuple
from .models import SubtitleEntry, SubtitleFile
from .utils import parse_timecode, detect_language, format_timecode


ENTRY_HEADER_RE = re.compile(
    r"^(\d+)\s*\n"
    r"(\d{1,2}:\d{2}:\d{2}[,.]\d{1,3})\s*-->\s*(\d{1,2}:\d{2}:\d{2}[,.]\d{1,3})",
    re.MULTILINE,
)

TIMECODE_LINE_RE = re.compile(
    r"^(\d{1,2}:\d{2}:\d{2}[,.]\d{1,3})\s*-->\s*(\d{1,2}:\d{2}:\d{2}[,.]\d{1,3})",
)


class SubtitleParser:
    @staticmethod
    def parse_srt(filepath: str, language: Optional[str] = None, fps: float = 24.0) -> SubtitleFile:
        with open(filepath, "r", encoding="utf-8-sig") as f:
            content = f.read()

        entries: List[SubtitleEntry] = []
        matches = list(ENTRY_HEADER_RE.finditer(content))

        for i, m in enumerate(matches):
            try:
                entry_index = int(m.group(1))
            except ValueError:
                entry_index = len(entries) + 1

            start_ms = parse_timecode(m.group(2))
            end_ms = parse_timecode(m.group(3))
            if start_ms is None:
                start_ms = entries[-1].end_time if entries else 0
            if end_ms is None:
                end_ms = start_ms + 1000

            header_end = m.end()
            if i + 1 < len(matches):
                body_end = matches[i + 1].start()
            else:
                body_end = len(content)

            body = content[header_end:body_end].lstrip("\r\n").rstrip()
            raw_lines = body.split("\n")
            text_lines: List[str] = []
            seen_first_nonempty = False
            for line in raw_lines:
                stripped = line.rstrip()
                if stripped == "":
                    if seen_first_nonempty:
                        text_lines.append(stripped)
                else:
                    seen_first_nonempty = True
                    text_lines.append(stripped)
            while text_lines and text_lines[-1] == "":
                text_lines.pop()

            if not text_lines and not seen_first_nonempty:
                text_lines = []

            entry = SubtitleEntry(
                index=entry_index,
                start_time=start_ms,
                end_time=end_ms,
                text_lines=text_lines,
            )
            entries.append(entry)

        if not entries:
            for block in re.split(r"\n\s*\n", content.strip()):
                block = block.strip()
                if not block:
                    continue
                lines = block.split("\n")
                idx = 0
                entry_index = len(entries) + 1
                if lines and lines[0].strip().isdigit():
                    try:
                        entry_index = int(lines[0].strip())
                        idx = 1
                    except ValueError:
                        pass
                if idx < len(lines):
                    tm = TIMECODE_LINE_RE.match(lines[idx].strip())
                    if tm:
                        idx += 1
                        start_ms = parse_timecode(tm.group(1)) or 0
                        end_ms = parse_timecode(tm.group(2)) or start_ms + 1000
                    else:
                        prev_end = entries[-1].end_time if entries else 0
                        start_ms, end_ms = prev_end, prev_end + 1000
                else:
                    prev_end = entries[-1].end_time if entries else 0
                    start_ms, end_ms = prev_end, prev_end + 1000
                text_lines = [l.rstrip() for l in lines[idx:]]
                entries.append(SubtitleEntry(
                    index=entry_index,
                    start_time=start_ms,
                    end_time=end_ms,
                    text_lines=text_lines,
                ))

        if not language:
            all_text = "\n".join(e.full_text for e in entries)
            language = detect_language(all_text)

        return SubtitleFile(filepath=filepath, language=language, fps=fps, entries=entries)

    @staticmethod
    def parse(filepath: str, language: Optional[str] = None, fps: float = 24.0) -> Optional[SubtitleFile]:
        ext = os.path.splitext(filepath)[1].lower()
        if ext == ".srt":
            return SubtitleParser.parse_srt(filepath, language, fps)
        return None

    @staticmethod
    def write_srt(subtitle_file: SubtitleFile, output_path: str):
        lines = []
        for entry in subtitle_file.entries:
            lines.append(str(entry.index))
            time_str = f"{format_timecode(entry.start_time)} --> {format_timecode(entry.end_time)}"
            lines.append(time_str)
            lines.extend(entry.text_lines)
            lines.append("")

        content = "\n".join(lines)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)
