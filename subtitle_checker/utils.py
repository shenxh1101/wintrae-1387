import os
import re
from typing import List, Optional, Tuple


def format_timecode(ms: int) -> str:
    if ms < 0:
        ms = 0
    hours = ms // 3600000
    ms = ms % 3600000
    minutes = ms // 60000
    ms = ms % 60000
    seconds = ms // 1000
    milliseconds = ms % 1000
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"


def parse_timecode(tc: str) -> Optional[int]:
    pattern = r"(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})"
    m = re.match(pattern, tc.strip())
    if not m:
        return None
    try:
        h, mi, s, ms = map(int, m.groups())
        if len(str(ms)) == 1:
            ms *= 100
        elif len(str(ms)) == 2:
            ms *= 10
        return h * 3600000 + mi * 60000 + s * 1000 + ms
    except ValueError:
        return None


def timecode_to_ms(timecode: str) -> Optional[int]:
    return parse_timecode(timecode)


def ms_to_frames(ms: int, fps: float) -> int:
    return int(ms * fps / 1000)


def frames_to_ms(frames: int, fps: float) -> int:
    return int(frames * 1000 / fps)


def find_subtitle_files(directory: str, recursive: bool = True) -> List[str]:
    extensions = (".srt", ".vtt", ".ass")
    result = []
    if recursive:
        for root, dirs, files in os.walk(directory):
            for f in files:
                if f.lower().endswith(extensions):
                    result.append(os.path.join(root, f))
    else:
        for f in os.listdir(directory):
            fp = os.path.join(directory, f)
            if os.path.isfile(fp) and f.lower().endswith(extensions):
                result.append(fp)
    return sorted(result)


def is_chinese(text: str) -> bool:
    for ch in text:
        if "\u4e00" <= ch <= "\u9fff":
            return True
    return False


def is_english(text: str) -> bool:
    return bool(re.search(r"[a-zA-Z]", text))


def detect_language(text: str) -> str:
    chinese_chars = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    english_chars = sum(1 for ch in text if "a" <= ch.lower() <= "z")
    if chinese_chars > english_chars:
        return "zh"
    return "en"


def get_output_path(original_path: str, suffix: str = "_fixed") -> str:
    base, ext = os.path.splitext(original_path)
    return base + suffix + ext


def detect_dual_language(lines: List[str]) -> bool:
    if len(lines) < 2:
        return False
    lang_set = set()
    for line in lines:
        if is_chinese(line):
            lang_set.add("zh")
        if is_english(line):
            lang_set.add("en")
    return "zh" in lang_set and "en" in lang_set


def split_dual_language_lines(lines: List[str]) -> Tuple[List[str], List[str]]:
    zh_lines = []
    en_lines = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if is_chinese(line):
            zh_lines.append(line)
        elif is_english(line):
            en_lines.append(line)
        else:
            zh_lines.append(line)
            en_lines.append(line)
    return zh_lines, en_lines


def ensure_directory(path: str):
    os.makedirs(path, exist_ok=True)
