"""Tagi i kolekcje — organizacja plików z tagami i kolekcjami."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class Tag:
    name: str
    color: str = "#888888"
    count: int = 0
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class Collection:
    name: str
    description: str = ""
    tags: List[str] = field(default_factory=list)
    items: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)


class TagManager:
    """Menadżer tagów — zarządza tagami i przypisania do plików."""

    def __init__(self, storage_path: Optional[Path] = None):
        self.storage_path = storage_path or Path.home() / ".filemanager" / "tags.json"
        self.tags: Dict[str, Tag] = {}
        self.file_tags: Dict[str, List[str]] = {}
        self._load()

    def _load(self) -> None:
        if self.storage_path.exists():
            data = json.loads(self.storage_path.read_text())
            for name, data_tag in data.get("tags", {}).items():
                self.tags[name] = Tag(**data_tag)
            self.file_tags = data.get("file_tags", {})

    def _save(self) -> None:
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "tags": {name: {"name": t.name, "color": t.color, "count": t.count} for name, t in self.tags.items()},
            "file_tags": self.file_tags,
        }
        self.storage_path.write_text(json.dumps(data, indent=2, default=str))

    def add_tag(self, name: str, color: str = "#888888") -> Tag:
        if name not in self.tags:
            self.tags[name] = Tag(name=name, color=color)
        return self.tags[name]

    def assign_tag(self, file_path: str, tag_name: str) -> None:
        if tag_name not in self.tags:
            self.add_tag(tag_name)
        if file_path not in self.file_tags:
            self.file_tags[file_path] = []
        if tag_name not in self.file_tags[file_path]:
            self.file_tags[file_path].append(tag_name)
            self.tags[tag_name].count += 1
        self._save()

    def remove_tag(self, file_path: str, tag_name: str) -> None:
        if file_path in self.file_tags and tag_name in self.file_tags[file_path]:
            self.file_tags[file_path].remove(tag_name)
            if tag_name in self.tags:
                self.tags[tag_name].count -= 1
            self._save()

    def get_tags_for_file(self, file_path: str) -> List[str]:
        return self.file_tags.get(file_path, [])

    def get_files_with_tag(self, tag_name: str) -> List[str]:
        return [path for path, tags in self.file_tags.items() if tag_name in tags]

    def search_by_tags(self, tags: List[str], match_all: bool = True) -> List[str]:
        if not tags:
            return list(self.file_tags.keys())
        result = []
        for path, file_tags in self.file_tags.items():
            matches = all(t in file_tags for t in tags) if match_all else any(t in file_tags for t in tags)
            if matches:
                result.append(path)
        return result


class CollectionManager:
    """Menadżer kolekcji — grupuje pliki w kolekcje (albumy)."""

    def __init__(self, storage_path: Optional[Path] = None):
        self.storage_path = storage_path or Path.home() / ".filemanager" / "collections.json"
        self.collections: Dict[str, Collection] = {}
        self._load()

    def _load(self) -> None:
        if self.storage_path.exists():
            data = json.loads(self.storage_path.read_text())
            for name, data_col in data.get("collections", {}).items():
                self.collections[name] = Collection(**data_col)

    def _save(self) -> None:
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "collections": {name: {"name": c.name, "description": c.description, "tags": c.tags, "items": c.items}
                           for name, c in self.collections.items()},
        }
        self.storage_path.write_text(json.dumps(data, indent=2, default=str))

    def create_collection(self, name: str, description: str = "") -> Collection:
        if name not in self.collections:
            self.collections[name] = Collection(name=name, description=description)
            self._save()
        return self.collections[name]

    def add_to_collection(self, collection_name: str, item_path: str) -> None:
        if collection_name not in self.collections:
            self.create_collection(collection_name)
        if item_path not in self.collections[collection_name].items:
            self.collections[collection_name].items.append(item_path)
            self._save()

    def remove_from_collection(self, collection_name: str, item_path: str) -> None:
        if collection_name in self.collections and item_path in self.collections[collection_name].items:
            self.collections[collection_name].items.remove(item_path)
            self._save()

    def add_tag_to_collection(self, collection_name: str, tag_name: str) -> None:
        if collection_name not in self.collections:
            self.create_collection(collection_name)
        if tag_name not in self.collections[collection_name].tags:
            self.collections[collection_name].tags.append(tag_name)
            self._save()

    def get_collection(self, name: str) -> Optional[Collection]:
        return self.collections.get(name)

    def list_collections(self) -> List[Collection]:
        return list(self.collections.values())