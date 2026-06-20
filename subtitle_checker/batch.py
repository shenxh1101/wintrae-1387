import os
import json
import hashlib
from typing import Dict, List, Optional, Any
from datetime import datetime
from .models import (
    ScanResult,
    SubtitleFile,
    Issue,
    IssueType,
    BatchDiff,
    DiffStatus,
)


BATCH_DIRNAME = ".subtitle_batches"
REVIEW_STATE_SUFFIX = "_review_state.json"


class ReviewState:
    def __init__(self, report_path: Optional[str] = None):
        self.path = self._derive_state_path(report_path) if report_path else None
        self._states: Dict[str, Dict[str, Any]] = {}
        if self.path and os.path.exists(self.path):
            self._load()

    @staticmethod
    def _derive_state_path(report_path: str) -> str:
        base, ext = os.path.splitext(report_path)
        return base + REVIEW_STATE_SUFFIX

    def _load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._states = data.get("states", {})
        except (json.JSONDecodeError, IOError):
            pass

    def save(self, path: Optional[str] = None):
        out = path or self.path
        if not out:
            return
        parent = os.path.dirname(out)
        if parent:
            os.makedirs(parent, exist_ok=True)
        data = {
            "generated_at": datetime.now().isoformat(),
            "states": self._states,
        }
        with open(out, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def get(self, issue_key: str) -> Dict[str, Any]:
        return self._states.get(issue_key, {"status": "unresolved", "note": ""})

    def set(self, issue_key: str, status: str, note: str = ""):
        self._states[issue_key] = {
            "status": status,
            "note": note,
            "updated_at": datetime.now().isoformat(),
        }

    def apply_to_result(self, result: ScanResult) -> int:
        count = 0
        for sf in result.files:
            for issue in sf.issues:
                key = issue.get_key(sf.filepath)
                saved = self.get(key)
                from .models import IssueStatus
                status_str = saved.get("status", "unresolved")
                try:
                    issue.status = IssueStatus(status_str)
                except ValueError:
                    issue.status = IssueStatus.UNRESOLVED
                issue.note = saved.get("note", "")
                if issue.status.value != "unresolved":
                    count += 1
        return count


class BatchManager:
    def __init__(self, root_dir: str = "."):
        self.root_dir = os.path.abspath(root_dir)
        self.batch_dir = os.path.join(self.root_dir, BATCH_DIRNAME)
        os.makedirs(self.batch_dir, exist_ok=True)

    def _list_batches(self) -> List[str]:
        if not os.path.isdir(self.batch_dir):
            return []
        return sorted([
            f for f in os.listdir(self.batch_dir)
            if f.startswith("batch_") and f.endswith(".json")
        ])

    def latest_batch_path(self) -> Optional[str]:
        batches = self._list_batches()
        if not batches:
            return None
        return os.path.join(self.batch_dir, batches[-1])

    def save_batch(
        self,
        batch_name: str,
        result: ScanResult,
        review_state: Optional[ReviewState] = None,
    ) -> str:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in batch_name) or "unnamed"
        filename = f"batch_{timestamp}_{safe_name}.json"
        path = os.path.join(self.batch_dir, filename)
        snapshot = self._serialize_result(result)
        data = {
            "batch_name": batch_name,
            "created_at": datetime.now().isoformat(),
            "timestamp": timestamp,
            "snapshot": snapshot,
            "review_states": review_state._states if review_state else {},
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return path

    @staticmethod
    def _serialize_result(result: ScanResult) -> Dict[str, Any]:
        file_snapshots = {}
        for sf in result.files:
            issues = []
            for issue in sf.issues:
                issues.append({
                    "key": issue.get_key(sf.filepath),
                    "term_key": issue.get_term_key(sf.filepath),
                    "type": issue.type.value,
                    "severity": issue.severity.value,
                    "subtitle_index": issue.subtitle_index,
                    "line_number": issue.line_number,
                    "start_ms": issue.details.get("start_ms"),
                    "text": issue.details.get("text", ""),
                    "canonical": issue.details.get("canonical"),
                    "variant": issue.details.get("variant"),
                    "status": issue.status.value,
                    "note": issue.note,
                    "message": issue.message,
                })
            content_hash = ""
            try:
                with open(sf.filepath, "rb") as f:
                    content_hash = hashlib.md5(f.read()).hexdigest()
            except IOError:
                pass
            file_snapshots[sf.filepath] = {
                "filepath": sf.filepath,
                "filename": sf.filename,
                "content_hash": content_hash,
                "issue_count": len(issues),
                "issues": issues,
            }
        return {
            "files": file_snapshots,
            "total_issues": result.total_issues,
        }

    def compare_with_previous(
        self,
        current_result: ScanResult,
        previous_path: Optional[str] = None,
    ) -> BatchDiff:
        if not previous_path:
            previous_path = self.latest_batch_path()
        if not previous_path or not os.path.exists(previous_path):
            return BatchDiff(new_issues=[], resolved_issues=[], remaining_issues=[])

        try:
            with open(previous_path, "r", encoding="utf-8") as f:
                prev_data = json.load(f)
        except (json.JSONDecodeError, IOError):
            return BatchDiff(new_issues=[], resolved_issues=[], remaining_issues=[])

        prev_snapshot = prev_data.get("snapshot", {}).get("files", {})
        prev_keys: Dict[str, Dict] = {}
        prev_term_keys: Dict[str, Dict] = {}
        for fp, fdata in prev_snapshot.items():
            for issue in fdata.get("issues", []):
                if issue.get("key"):
                    prev_keys[issue["key"]] = {**issue, "filepath": fp}
                if issue.get("term_key"):
                    prev_term_keys[issue["term_key"]] = {**issue, "filepath": fp}

        current_keys: set = set()
        diff = BatchDiff()

        for sf in current_result.files:
            for issue in sf.issues:
                key = issue.get_key(sf.filepath)
                current_keys.add(key)
                wrapped = {
                    "key": key,
                    "diff_status": DiffStatus.REMAINING.value,
                    "issue": issue,
                    "filepath": sf.filepath,
                    "filename": sf.filename,
                }
                if key in prev_keys:
                    diff.remaining_issues.append(wrapped)
                    prev_keys.pop(key, None)
                else:
                    wrapped["diff_status"] = DiffStatus.NEW.value
                    diff.new_issues.append(wrapped)

        for key, info in prev_keys.items():
            diff.resolved_issues.append({
                "key": key,
                "diff_status": DiffStatus.RESOLVED.value,
                "filepath": info.get("filepath"),
                "filename": os.path.basename(info.get("filepath", "")),
                "issue_type": info.get("type"),
                "subtitle_index": info.get("subtitle_index"),
                "message": info.get("message", ""),
            })

        return diff
