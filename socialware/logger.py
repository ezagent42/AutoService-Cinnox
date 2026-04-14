"""
Conversation logger.

Log every conversation into .autoservice/database/history
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


class ConversationLogger:
    """Record conversation history to JSON files."""

    def __init__(self, base_path: Optional[str] = None):
        if base_path is None:
            base_path = str(Path.cwd())

        self.history_dir = Path(base_path) / ".autoservice" / "database" / "history"
        self.history_dir.mkdir(parents=True, exist_ok=True)

        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.session_file = self.history_dir / f"session_{self.session_id}.json"
        self.conversations = []

    def _serialize(self, obj: Any) -> Any:
        if obj is None:
            return None
        if isinstance(obj, (str, int, float, bool)):
            return obj
        if isinstance(obj, (list, tuple)):
            return [self._serialize(item) for item in obj]
        if isinstance(obj, dict):
            return {k: self._serialize(v) for k, v in obj.items()}
        if hasattr(obj, '__dict__'):
            return {
                '_type': obj.__class__.__name__,
                **{k: self._serialize(v) for k, v in vars(obj).items()}
            }
        return str(obj)

    def log_user_input(self, user_input: str):
        self.conversations.append({
            "timestamp": datetime.now().isoformat(),
            "role": "user",
            "content": user_input
        })
        self._save()

    def log_message(self, message: Any):
        self.conversations.append({
            "timestamp": datetime.now().isoformat(),
            "role": "assistant",
            "message": self._serialize(message)
        })
        self._save()

    def _save(self):
        with open(self.session_file, 'w', encoding='utf-8') as f:
            json.dump({
                "session_id": self.session_id,
                "started_at": self.conversations[0]["timestamp"] if self.conversations else None,
                "conversations": self.conversations
            }, f, ensure_ascii=False, indent=2)
