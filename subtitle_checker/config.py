import os
import json
import hashlib
from typing import Dict, List, Optional, Set, Any
from datetime import datetime


DEFAULT_TERMS: Dict[str, Dict[str, List[str]]] = {
    "zh": {
        "人工智能": ["AI", "A.I.", "人工智慧"],
        "机器学习": ["ML", "Machine Learning"],
        "深度学习": ["Deep Learning", "深度學習"],
        "神经网络": ["Neural Network", "NN", "類神經網路"],
        "算法": ["Algorithm", "演算法"],
        "数据": ["資料"],
        "模型": ["Model"],
        "训练": ["Training", "訓練"],
        "推理": ["Inference", "推論"],
        "计算机": ["电脑", "Computer"],
        "软件": ["軟體", "Software"],
        "硬件": ["硬體", "Hardware"],
        "用户": ["使用者", "User"],
        "界面": ["介面", "Interface", "UI"],
        "应用": ["應用", "Application", "App"],
        "程序": ["程式", "Program"],
        "代码": ["程式碼", "Code"],
        "数据库": ["資料庫", "Database", "DB"],
        "服务器": ["伺服器", "Server"],
        "客户端": ["客戶端", "Client"],
    },
    "en": {},
}

DEFAULT_CONFIG = {
    "language": None,
    "fps": 24.0,
    "output_dir": None,
    "align_to_frames": True,
    "max_line_length": {
        "zh": 20,
        "en": 42,
    },
    "reading_speed": {
        "zh": 8,
        "en": 15,
    },
    "min_duration_per_line": {
        "zh": 600,
        "en": 500,
    },
    "punctuation_end": ["。", "！", "？", ".", "!", "?", "…", "...", "」", "”", "』"],
    "terms": DEFAULT_TERMS,
    "ignored_issues": [],
}

PROJECT_CONFIG_FILENAME = "subtitle_config.json"
IGNORE_LIST_FILENAME = "subtitle_ignores.json"


class IgnoreList:
    def __init__(self, ignore_path: Optional[str] = None):
        self.path = ignore_path
        self.entries: List[Dict[str, Any]] = []
        self._content_hashes: Dict[str, str] = {}
        if ignore_path and os.path.exists(ignore_path):
            self._load(ignore_path)

    def _load(self, path: str):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.entries = data.get("ignored_issues", [])
            for e in self.entries:
                if "content_hash" in e and "file" in e:
                    self._content_hashes[e["file"]] = e.get("content_hash", "")
        except (json.JSONDecodeError, IOError):
            pass

    def save(self, path: Optional[str] = None):
        out = path or self.path or IGNORE_LIST_FILENAME
        data = {
            "generated_at": datetime.now().isoformat(),
            "ignored_issues": self.entries,
        }
        with open(out, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    @staticmethod
    def compute_content_hash(filepath: str) -> str:
        try:
            with open(filepath, "rb") as f:
                return hashlib.md5(f.read()).hexdigest()
        except IOError:
            return ""

    @staticmethod
    def compute_issue_key(
        filepath: str,
        issue_type: str,
        subtitle_index: Optional[int],
        line_number: Optional[int],
        start_ms: Optional[int] = None,
        text: Optional[str] = None,
    ) -> str:
        parts = [os.path.abspath(filepath), issue_type]
        if subtitle_index is not None:
            parts.append(f"idx:{subtitle_index}")
        if line_number is not None:
            parts.append(f"line:{line_number}")
        if start_ms is not None:
            parts.append(f"start:{start_ms}")
        if text:
            parts.append(f"text:{text.strip()[:50]}")
        raw = "|".join(parts)
        return hashlib.md5(raw.encode("utf-8")).hexdigest()

    def is_ignored(
        self,
        filepath: str,
        issue_type: str,
        subtitle_index: Optional[int],
        line_number: Optional[int] = None,
        start_ms: Optional[int] = None,
        text: Optional[str] = None,
    ) -> bool:
        abs_path = os.path.abspath(filepath)
        current_hash = self.compute_content_hash(abs_path)
        key = self.compute_issue_key(abs_path, issue_type, subtitle_index, line_number, start_ms, text)
        for entry in self.entries:
            if entry.get("key") == key:
                if entry.get("file") == abs_path:
                    stored_hash = entry.get("content_hash", "")
                    if stored_hash and stored_hash == current_hash:
                        return True
        return False

    def add_ignore(
        self,
        filepath: str,
        issue_type: str,
        subtitle_index: Optional[int],
        line_number: Optional[int] = None,
        start_ms: Optional[int] = None,
        text: Optional[str] = None,
        reason: str = "",
    ) -> str:
        abs_path = os.path.abspath(filepath)
        key = self.compute_issue_key(abs_path, issue_type, subtitle_index, line_number, start_ms, text)
        content_hash = self.compute_content_hash(abs_path)
        for entry in self.entries:
            if entry.get("key") == key and entry.get("file") == abs_path:
                entry["content_hash"] = content_hash
                entry["reason"] = reason
                entry["updated_at"] = datetime.now().isoformat()
                return key
        self.entries.append({
            "key": key,
            "file": abs_path,
            "issue_type": issue_type,
            "subtitle_index": subtitle_index,
            "line_number": line_number,
            "start_ms": start_ms,
            "text_snippet": (text or "")[:50],
            "content_hash": content_hash,
            "reason": reason,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        })
        return key

    def clear(self):
        self.entries = []

    def __len__(self) -> int:
        return len(self.entries)


class Config:
    def __init__(self, config_path: Optional[str] = None):
        self.data = {k: v for k, v in DEFAULT_CONFIG.items() if k not in ("terms", "ignored_issues")}
        self.data["language"] = None
        self.data["fps"] = 24.0
        self.data["output_dir"] = None
        self.data["align_to_frames"] = True
        self.terms: Dict[str, Dict[str, List[str]]] = {}
        for lang, terms in DEFAULT_TERMS.items():
            self.terms[lang] = dict(terms)
        self.ignore_list = IgnoreList()
        self.config_path = config_path
        self.ignore_path: Optional[str] = None
        if config_path and os.path.exists(config_path):
            self._load(config_path)
            cfg_dir = os.path.dirname(os.path.abspath(config_path))
            candidate_ignore = os.path.join(cfg_dir, IGNORE_LIST_FILENAME)
            if os.path.exists(candidate_ignore):
                self.ignore_path = candidate_ignore
                self.ignore_list = IgnoreList(candidate_ignore)

    def _load(self, path: str):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for key in ("language", "fps", "output_dir", "align_to_frames"):
                if key in data:
                    self.data[key] = data[key]
            for key in ("max_line_length", "reading_speed", "min_duration_per_line"):
                if key in data:
                    self.data[key].update(data[key])
            if "punctuation_end" in data:
                self.data["punctuation_end"] = data["punctuation_end"]
            if "terms" in data:
                for lang, terms in data["terms"].items():
                    if lang not in self.terms:
                        self.terms[lang] = {}
                    self.terms[lang].update(terms)
        except (json.JSONDecodeError, IOError) as e:
            print(f"警告: 无法加载配置文件 {path}: {e}")

    def get_language(self) -> Optional[str]:
        return self.data.get("language")

    def get_fps(self) -> float:
        return self.data.get("fps", 24.0)

    def get_output_dir(self) -> Optional[str]:
        return self.data.get("output_dir")

    def should_align_frames(self) -> bool:
        return self.data.get("align_to_frames", True)

    def get_max_line_length(self, lang: str) -> int:
        return self.data["max_line_length"].get(lang, self.data["max_line_length"]["en"])

    def get_reading_speed(self, lang: str) -> float:
        return self.data["reading_speed"].get(lang, self.data["reading_speed"]["en"])

    def get_min_duration(self, lang: str) -> int:
        return self.data["min_duration_per_line"].get(lang, self.data["min_duration_per_line"]["en"])

    def get_terms_for_language(self, lang: str) -> Dict[str, List[str]]:
        return self.terms.get(lang, {})

    def get_all_term_variants(self, lang: str) -> Dict[str, Set[str]]:
        result = {}
        terms = self.get_terms_for_language(lang)
        for canonical, variants in terms.items():
            all_variants = set(variants)
            all_variants.add(canonical)
            result[canonical] = all_variants
        return result

    def to_dict(self) -> dict:
        d = {k: v for k, v in self.data.items()}
        d["terms"] = {lang: dict(t) for lang, t in self.terms.items()}
        return d

    def save_ignore_list(self):
        if self.ignore_path:
            self.ignore_list.save(self.ignore_path)
        else:
            self.ignore_list.save(IGNORE_LIST_FILENAME)

    @staticmethod
    def generate_template(output_path: str) -> str:
        template = {k: v for k, v in DEFAULT_CONFIG.items() if k != "ignored_issues"}
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(template, f, ensure_ascii=False, indent=2)
        return output_path

    @staticmethod
    def find_project_config(start_dir: str = ".") -> Optional[str]:
        current = os.path.abspath(start_dir)
        while True:
            candidate = os.path.join(current, PROJECT_CONFIG_FILENAME)
            if os.path.exists(candidate):
                return candidate
            parent = os.path.dirname(current)
            if parent == current:
                break
            current = parent
        return None
