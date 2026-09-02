import os
from abc import ABC, abstractmethod
from typing import Dict, List, Optional
from pathlib import Path

class BaseBackend(ABC):
    @abstractmethod
    def read_file(self, filename: str) -> str:
        pass

    @abstractmethod
    def write_file(self, filename: str, content: str) -> str:
        pass

    @abstractmethod
    def list_files(self) -> List[str]:
        pass

    @abstractmethod
    def get_files(self) -> Dict[str, str]:
        pass


class StateBackend(BaseBackend):
    """In-Memory RAM Virtual File System for Deep Agent."""
    def __init__(self, initial_files: Optional[Dict[str, str]] = None):
        self._files: Dict[str, str] = initial_files or {}

    def read_file(self, filename: str) -> str:
        if filename not in self._files:
            return f"Error: File '{filename}' not found."
        return self._files[filename]

    def write_file(self, filename: str, content: str) -> str:
        self._files[filename] = content
        return f"Successfully wrote {len(content)} bytes to '{filename}'."

    def list_files(self) -> List[str]:
        return list(self._files.keys())

    def get_files(self) -> Dict[str, str]:
        return dict(self._files)


class FileSystemBackend(BaseBackend):
    """Local Disk Virtual File System mapped to a physical directory."""
    def __init__(self, root_dir: str = "./agent_workspace"):
        self.root_dir = Path(root_dir)
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def _resolve(self, filename: str) -> Path:
        safe_path = (self.root_dir / filename).resolve()
        if not str(safe_path).startswith(str(self.root_dir.resolve())):
            raise ValueError("Directory traversal attempt detected.")
        return safe_path

    def read_file(self, filename: str) -> str:
        try:
            path = self._resolve(filename)
            if not path.exists():
                return f"Error: File '{filename}' not found on disk."
            return path.read_text(encoding="utf-8")
        except Exception as e:
            return f"Error reading file '{filename}': {str(e)}"

    def write_file(self, filename: str, content: str) -> str:
        try:
            path = self._resolve(filename)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            return f"Successfully wrote {len(content)} bytes to disk file '{filename}'."
        except Exception as e:
            return f"Error writing file '{filename}': {str(e)}"

    def list_files(self) -> List[str]:
        if not self.root_dir.exists():
            return []
        return [str(p.relative_to(self.root_dir)) for p in self.root_dir.rglob("*") if p.is_file()]

    def get_files(self) -> Dict[str, str]:
        result = {}
        for rel_path in self.list_files():
            result[rel_path] = self.read_file(rel_path)
        return result


class StoreBackend(BaseBackend):
    """LangGraph BaseStore backed cross-thread Virtual File System."""
    def __init__(self, store=None, namespace: tuple = ("agent", "files")):
        self.store = store
        self.namespace = namespace
        self._local_cache: Dict[str, str] = {}

    def read_file(self, filename: str) -> str:
        if self.store:
            try:
                item = self.store.get(self.namespace, filename)
                if item and "content" in item.value:
                    return item.value["content"]
            except Exception:
                pass
        return self._local_cache.get(filename, f"Error: File '{filename}' not found in store.")

    def write_file(self, filename: str, content: str) -> str:
        self._local_cache[filename] = content
        if self.store:
            try:
                self.store.put(self.namespace, filename, {"content": content})
            except Exception as e:
                return f"Warning: Failed to put to store ({str(e)}), saved to local cache."
        return f"Successfully stored '{filename}' ({len(content)} bytes)."

    def list_files(self) -> List[str]:
        if self.store:
            try:
                items = self.store.search(self.namespace)
                return [item.key for item in items]
            except Exception:
                pass
        return list(self._local_cache.keys())

    def get_files(self) -> Dict[str, str]:
        files = {}
        for f in self.list_files():
            files[f] = self.read_file(f)
        return files
