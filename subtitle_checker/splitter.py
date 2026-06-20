import os
from typing import Tuple, List
from copy import deepcopy
from .models import SubtitleFile, SubtitleEntry
from .utils import (
    split_dual_language_lines,
    detect_dual_language,
    get_output_path,
    is_chinese,
    is_english,
)
from .parser import SubtitleParser


class DualLanguageSplitter:
    @staticmethod
    def split(subtitle_file: SubtitleFile) -> Tuple[SubtitleFile, SubtitleFile]:
        zh_entries: List[SubtitleEntry] = []
        en_entries: List[SubtitleEntry] = []

        for entry in subtitle_file.entries:
            if not entry.text_lines:
                continue
            zh_lines, en_lines = split_dual_language_lines(entry.text_lines)
            if zh_lines:
                zh_entries.append(
                    SubtitleEntry(
                        index=len(zh_entries) + 1,
                        start_time=entry.start_time,
                        end_time=entry.end_time,
                        text_lines=zh_lines,
                    )
                )
            if en_lines:
                en_entries.append(
                    SubtitleEntry(
                        index=len(en_entries) + 1,
                        start_time=entry.start_time,
                        end_time=entry.end_time,
                        text_lines=en_lines,
                    )
                )

        base, ext = os.path.splitext(subtitle_file.filepath)

        zh_file = SubtitleFile(
            filepath=base + ".zh" + ext,
            language="zh",
            entries=zh_entries,
        )
        en_file = SubtitleFile(
            filepath=base + ".en" + ext,
            language="en",
            entries=en_entries,
        )
        return zh_file, en_file

    @staticmethod
    def split_and_save(subtitle_file: SubtitleFile, output_dir: str = None) -> Tuple[str, str]:
        zh_file, en_file = DualLanguageSplitter.split(subtitle_file)

        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
            zh_name = os.path.basename(zh_file.filepath)
            en_name = os.path.basename(en_file.filepath)
            zh_path = os.path.join(output_dir, zh_name)
            en_path = os.path.join(output_dir, en_name)
        else:
            zh_path = zh_file.filepath
            en_path = en_file.filepath

        SubtitleParser.write_srt(zh_file, zh_path)
        SubtitleParser.write_srt(en_file, en_path)
        return zh_path, en_path
