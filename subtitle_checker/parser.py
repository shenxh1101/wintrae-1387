import os
import re
from typing import List, Optional
from .models import SubtitleEntry, SubtitleFile
from .utils import parse_timecode, detect_language, format_timecode


class SubtitleParser:
    @staticmethod
    def parse_srt(filepath: str, language: Optional[str] = None) -> SubtitleFile:
        with open(filepath, "r", encoding="utf-8-sig") as f:
            content = f.read()

        entries: List[SubtitleEntry] = []
        blocks = re.split(r"\n\s*\n", content.strip())

        for block in blocks:
            block = block.strip()
            if not block:
                continue
            lines = block.split("\n")

            idx = 0
            entry_index = None
            if lines and lines[0].strip().isdigit():
                try:
                    entry_index = int(lines[0].strip())
                    idx = 1
                except ValueError:
                    entry_index = len(entries) + 1
            else:
                entry_index = len(entries) + 1

            if idx >= len(lines):
                continue

            time_line = lines[idx].strip()
            idx += 1
            time_match = re.match(
                r"(\d{1,2}:\d{2}:\d{2}[,.]\d{1,3})\s*-->\s*(\d{1,2}:\d{2}:\d{2}[,.]\d{1,3})",
                time_line,
            )
            if not time_match:
                continue

            start_ms = parse_timecode(time_match.group(1))
            end_ms = parse_timecode(time_match.group(2))
            if start_ms is None or end_ms is None:
                continue

            text_lines = [line.rstrip() for line in lines[idx:] if line.strip() or True]
            text_lines = [line for line in text_lines if line.strip() != ""]

            entry = SubtitleEntry(
                index=entry_index,
                start_time=start_ms,
                end_time=end_ms,
                text_lines=text_lines,
            )
            entries.append(entry)

        if not language:
            all_text = "\n".join(e.full_text for e in entries)
            language = detect_language(all_text)

        return SubtitleFile(filepath=filepath, language=language, entries=entries)

    @staticmethod
    def parse(filepath: str, language: Optional[str] = None) -> Optional[SubtitleFile]:
        ext = os.path.splitext(filepath)[1].lower()
        if ext == ".srt":
            return SubtitleParser.parse_srt(filepath, language)
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
