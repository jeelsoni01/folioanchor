"""Local answer cache for this immutable assessment snapshot."""

import hashlib
import json
import sqlite3
import threading
from pathlib import Path


class AnswerCache:
    def __init__(self, path: Path, dataset_fingerprint: str, model: str):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.prefix = f"v1:{dataset_fingerprint}:{model}:"
        self.memory: dict[str, str] = {}
        self.lock = threading.RLock()
        self.connection = sqlite3.connect(path, check_same_thread=False)
        self.connection.execute("CREATE TABLE IF NOT EXISTS answers (key TEXT PRIMARY KEY, payload TEXT NOT NULL)")

    def key(self, question: str) -> str:
        normalized = " ".join(question.casefold().split())
        return hashlib.sha256((self.prefix + normalized).encode()).hexdigest()

    def get(self, question: str) -> tuple[dict, str] | None:
        key = self.key(question)
        with self.lock:
            if key in self.memory:
                return json.loads(self.memory[key]), "memory"
            row = self.connection.execute("SELECT payload FROM answers WHERE key=?", (key,)).fetchone()
            if row:
                self.memory[key] = row[0]
                return json.loads(row[0]), "disk"
        return None

    def put(self, question: str, answer: dict):
        key = self.key(question)
        payload = json.dumps(answer, ensure_ascii=False, separators=(",", ":"))
        with self.lock:
            self.memory[key] = payload
            self.connection.execute("INSERT OR REPLACE INTO answers VALUES (?, ?)", (key, payload))
            self.connection.commit()

    def close(self):
        with self.lock:
            self.connection.close()
