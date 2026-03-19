import json
import hashlib
import time
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from pathlib import Path


@dataclass
class Version:
    """Класс для представления версии"""
    version_id: str
    timestamp: float
    author: str
    description: str
    file_hash: str
    parent_version: Optional[str] = None
    branch: str = "main"
    tags: List[str] = None
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.tags is None:
            self.tags = []
        if self.metadata is None:
            self.metadata = {}


@dataclass
class VersionedFile:
    """Класс для представления файла с версиями"""
    filepath: str
    filename: str
    current_version: Optional[str]
    versions: Dict[str, Version]
    branches: Dict[str, str]
    created_at: float
    updated_at: float


class VersionControlService:
    """Сервис контроля версий для файлов"""

    def __init__(self, storage_path: str = "version_storage", secret_key: str = None):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(exist_ok=True)
        self.files_path = self.storage_path / "files"
        self.files_path.mkdir(exist_ok=True)
        self.secret_key = secret_key or "change-this-key-in-production"
        self.files_index: Dict[str, VersionedFile] = {}
        self.logger = logging.getLogger(__name__)
        self._load_index()

    def _load_index(self):
        """Загрузка индекса файлов"""
        index_file = self.storage_path / "index.json"
        if index_file.exists():
            try:
                with open(index_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for filepath, file_data in data.items():
                        versions = {}
                        for ver_id, ver_data in file_data.get('versions', {}).items():
                            versions[ver_id] = Version(**ver_data)

                        self.files_index[filepath] = VersionedFile(
                            filepath=filepath,
                            filename=file_data.get('filename', Path(filepath).name),
                            current_version=file_data.get('current_version'),
                            versions=versions,
                            branches=file_data.get('branches', {"main": file_data.get('current_version')}),
                            created_at=file_data.get('created_at', time.time()),
                            updated_at=file_data.get('updated_at', time.time())
                        )
            except Exception as e:
                self.logger.error(f"Error loading index: {e}")

    def _save_index(self):
        """Сохранение индекса файлов"""
        index_file = self.storage_path / "index.json"
        data = {}

        for filepath, versioned_file in self.files_index.items():
            versions_data = {}
            for ver_id, version in versioned_file.versions.items():
                versions_data[ver_id] = asdict(version)

            data[filepath] = {
                'filename': versioned_file.filename,
                'current_version': versioned_file.current_version,
                'versions': versions_data,
                'branches': versioned_file.branches,
                'created_at': versioned_file.created_at,
                'updated_at': versioned_file.updated_at
            }

        with open(index_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _calculate_hash(self, content: str) -> str:
        """Вычисление хеша содержимого"""
        return hashlib.sha256(content.encode('utf-8')).hexdigest()

    def _generate_version_id(self, filepath: str, timestamp: float) -> str:
        """Генерация ID версии"""
        data = f"{filepath}:{timestamp}:{self.secret_key}"
        return hashlib.sha256(data.encode('utf-8')).hexdigest()[:12]

    def _get_version_path(self, filepath: str, version_id: str) -> Path:
        """Получение пути к файлу версии"""
        safe_path = filepath.replace('/', '_').replace('\\', '_').replace(':', '_').replace('.', '_')
        return self.files_path / f"{safe_path}__{version_id}.txt"

    def add_file(self, filepath: str, content: str, author: str,
                 description: str = "Initial version", branch: str = "main") -> str:
        """Добавление нового файла в систему контроля версий"""
        filename = Path(filepath).name

        if filepath in self.files_index:
            raise ValueError(f"File {filepath} already exists in version control")

        timestamp = time.time()
        file_hash = self._calculate_hash(content)
        version_id = self._generate_version_id(filepath, timestamp)

        version = Version(
            version_id=version_id,
            timestamp=timestamp,
            author=author,
            description=description,
            file_hash=file_hash,
            branch=branch
        )

        version_path = self._get_version_path(filepath, version_id)
        with open(version_path, 'w', encoding='utf-8') as f:
            f.write(content)

        versioned_file = VersionedFile(
            filepath=filepath,
            filename=filename,
            current_version=version_id,
            versions={version_id: version},
            branches={branch: version_id},
            created_at=timestamp,
            updated_at=timestamp
        )

        self.files_index[filepath] = versioned_file
        self._save_index()

        self.logger.info(f"File {filepath} added to version control with version {version_id}")
        return version_id

    def commit(self, filepath: str, content: str, author: str,
               description: str = "Update", branch: Optional[str] = None) -> str:
        """Создание новой версии файла"""
        if filepath not in self.files_index:
            raise ValueError(f"File {filepath} not found in version control")

        versioned_file = self.files_index[filepath]

        if branch is None:
            current_ver = versioned_file.current_version
            branch = "main"
            for b, v in versioned_file.branches.items():
                if v == current_ver:
                    branch = b
                    break

        parent_version = versioned_file.branches.get(branch)
        file_hash = self._calculate_hash(content)

        if parent_version and versioned_file.versions[parent_version].file_hash == file_hash:
            self.logger.info(f"No changes detected for {filepath}")
            return parent_version

        timestamp = time.time()
        version_id = self._generate_version_id(filepath, timestamp)

        version = Version(
            version_id=version_id,
            timestamp=timestamp,
            author=author,
            description=description,
            file_hash=file_hash,
            parent_version=parent_version,
            branch=branch
        )

        version_path = self._get_version_path(filepath, version_id)
        with open(version_path, 'w', encoding='utf-8') as f:
            f.write(content)

        versioned_file.versions[version_id] = version
        versioned_file.branches[branch] = version_id
        versioned_file.current_version = version_id
        versioned_file.updated_at = timestamp

        self._save_index()

        self.logger.info(f"Committed version {version_id} for {filepath}")
        return version_id

    def get_version(self, filepath: str, version_id: Optional[str] = None) -> Optional[str]:
        """Получение содержимого файла по версии"""
        if filepath not in self.files_index:
            return None

        versioned_file = self.files_index[filepath]

        if version_id is None:
            version_id = versioned_file.current_version

        if version_id not in versioned_file.versions:
            return None

        version_path = self._get_version_path(filepath, version_id)
        if not version_path.exists():
            return None

        with open(version_path, 'r', encoding='utf-8') as f:
            return f.read()

    def list_versions(self, filepath: str, branch: Optional[str] = None) -> List[Dict]:
        """Список всех версий файла"""
        if filepath not in self.files_index:
            return []

        versioned_file = self.files_index[filepath]
        versions = []

        for ver_id, version in versioned_file.versions.items():
            if branch is None or version.branch == branch:
                version_dict = asdict(version)
                version_dict['is_current'] = (ver_id == versioned_file.current_version)
                versions.append(version_dict)

        versions.sort(key=lambda x: x['timestamp'], reverse=True)
        return versions

    def create_branch(self, filepath: str, branch_name: str,
                     from_version: Optional[str] = None) -> bool:
        """Создание новой ветки"""
        if filepath not in self.files_index:
            return False

        versioned_file = self.files_index[filepath]

        if branch_name in versioned_file.branches:
            return False

        if from_version is None:
            from_version = versioned_file.current_version

        if from_version not in versioned_file.versions:
            return False

        versioned_file.branches[branch_name] = from_version
        self._save_index()

        self.logger.info(f"Created branch {branch_name} for {filepath}")
        return True

    def checkout(self, filepath: str, version_id: str) -> bool:
        """Переключение на указанную версию"""
        if filepath not in self.files_index:
            return False

        versioned_file = self.files_index[filepath]

        if version_id not in versioned_file.versions:
            return False

        versioned_file.current_version = version_id
        versioned_file.updated_at = time.time()
        self._save_index()

        self.logger.info(f"Checked out version {version_id} for {filepath}")
        return True

    def diff(self, filepath: str, version1: str, version2: str) -> Optional[str]:
        """Сравнение двух версий файла"""
        content1 = self.get_version(filepath, version1)
        content2 = self.get_version(filepath, version2)

        if content1 is None or content2 is None:
            return None

        lines1 = content1.splitlines()
        lines2 = content2.splitlines()

        diff_lines = []
        max_len = max(len(lines1), len(lines2))

        for i in range(max_len):
            line1 = lines1[i] if i < len(lines1) else ""
            line2 = lines2[i] if i < len(lines2) else ""

            if line1 != line2:
                diff_lines.append(f"Line {i+1}:")
                if line1:
                    diff_lines.append(f"  - {line1}")
                if line2:
                    diff_lines.append(f"  + {line2}")

        return "\n".join(diff_lines) if diff_lines else "Files are identical"

    def get_history(self, filepath: str, limit: int = 10) -> List[Dict]:
        """Получение истории изменений"""
        versions = self.list_versions(filepath)
        return versions[:limit]