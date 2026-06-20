import os
import json
from typing import Dict, List, Optional, Set


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
}


class Config:
    def __init__(self, config_path: Optional[str] = None):
        self.data = dict(DEFAULT_CONFIG)
        self.terms = dict(DEFAULT_TERMS)
        if config_path and os.path.exists(config_path):
            self._load(config_path)

    def _load(self, path: str):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if "max_line_length" in data:
                self.data["max_line_length"].update(data["max_line_length"])
            if "reading_speed" in data:
                self.data["reading_speed"].update(data["reading_speed"])
            if "min_duration_per_line" in data:
                self.data["min_duration_per_line"].update(data["min_duration_per_line"])
            if "punctuation_end" in data:
                self.data["punctuation_end"] = data["punctuation_end"]
            if "terms" in data:
                for lang, terms in data["terms"].items():
                    if lang not in self.terms:
                        self.terms[lang] = {}
                    self.terms[lang].update(terms)
        except (json.JSONDecodeError, IOError):
            pass

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
