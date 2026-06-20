import os
import re
from typing import List, Optional
from .models import SubtitleFile, SubtitleEntry
from .parser import SubtitleParser
from .utils import parse_timecode, detect_language, get_output_path


class SubtitleMerger:
    @staticmethod
    def merge(files: List[SubtitleFile], gap_ms: int = 0) -> SubtitleFile:
        if not files:
            raise ValueError("No files to merge")

        all_entries: List[SubtitleEntry] = []
        current_offset = 0
        reference_lang = files[0].language

        for sf in files:
            for entry in sf.entries:
                new_entry = SubtitleEntry(
                    index=len(all_entries) + 1,
                    start_time=entry.start_time + current_offset,
                    end_time=entry.end_time + current_offset,
                    text_lines=entry.text_lines.copy(),
                )
                all_entries.append(new_entry)
            if sf.entries:
                current_offset += sf.entries[-1].end_time + gap_ms

        merged = SubtitleFile(
            filepath="",
            language=reference_lang,
            entries=all_entries,
        )
        return merged

    @staticmethod
    def merge_files(file_paths: List[str], language: Optional[str] = None,
                    gap_ms: int = 0, output_path: Optional[str] = None) -> SubtitleFile:
        parsed_files = []
        for fp in file_paths:
            sf = SubtitleParser.parse(fp, language)
            if sf:
                parsed_files.append(sf)

        if not parsed_files:
            raise ValueError("No valid subtitle files found")

        merged = SubtitleMerger.merge(parsed_files, gap_ms)
        if not output_path:
            first_dir = os.path.dirname(file_paths[0])
            output_path = os.path.join(first_dir, "merged.srt")
        merged.filepath = output_path
        SubtitleParser.write_srt(merged, output_path)
        return merged

    @staticmethod
    def find_segment_files(directory: str, pattern: str = None) -> List[str]:
        if pattern is None:
            pattern = r"(_part\d+|\.\d+\.|seg\d+)"
        result = []
        for f in sorted(os.listdir(directory)):
            if f.lower().endswith(".srt") and re.search(pattern, f):
                result.append(os.path.join(directory, f))
        if not result:
            for f in sorted(os.listdir(directory)):
                if f.lower().endswith(".srt"):
                    result.append(os.path.join(directory, f))
        return result
