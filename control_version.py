import json
import hashlib
import time
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, asdict
import pickle
import zipfile

@dataclass
class VersionInfo:
    """Информация о версии бота"""
    version_id: str
    timestamp: float
    description: str
    author: str
    files_hash: Dict[str, str]
    dependencies: Dict[str, str]
    bot_config: Dict[str, Any]
    parent_version: Optional[str] = None

class VersionControl:
    """Система контроля версий для телеграм ботов"""
    
    def __init__(self, bot_container, versions_dir: str = "versions"):
        self.bot = bot_container
        self.versions_dir = Path(versions_dir)
        self.current_version: Optional[str] = None
        self.versions: Dict[str, VersionInfo] = {}
        
        # Создаем директорию для версий
        self.versions_dir.mkdir(exist_ok=True)
        
        # Загружаем историю версий
        self._load_versions()
        
        # Регистрируем сервис в контейнере
        self.bot.register_service('version_control', self)
        
        # Добавляем команды для управления версиями
        self._register_version_commands()
        
    def _register_version_commands(self):
        """Регистрация команд для работы с версиями"""
        
        async def version_command(update, context):
            """Показать текущую версию"""
            if self.current_version:
                version = self.versions[self.current_version]
                await update.message.reply_text(
                    f"📦 Текущая версия: {version.version_id}\n"
                    f"📝 Описание: {version.description}\n"
                    f"👤 Автор: {version.author}\n"
                    f"📅 Дата: {datetime.fromtimestamp(version.timestamp)}"
                )
            else:
                await update.message.reply_text("❌ Нет активной версии")
        
        async def versions_list_command(update, context):
            """Показать список всех версий"""
            if not self.versions:
                await update.message.reply_text("📭 Нет сохраненных версий")
                return
            
            versions_list = []
            for vid, vinfo in sorted(self.versions.items(), 
                                    key=lambda x: x[1].timestamp, reverse=True):
                marker = "✅ " if vid == self.current_version else "   "
                versions_list.append(
                    f"{marker}{vid[:8]} - {vinfo.description[:50]} "
                    f"({datetime.fromtimestamp(vinfo.timestamp).strftime('%Y-%m-%d %H:%M')})"
                )
            
            text = "📋 Доступные версии:\n" + "\n".join(versions_list[:10])
            if len(versions_list) > 10:
                text += f"\n... и еще {len(versions_list) - 10} версий"
            
            await update.message.reply_text(text)
        
        async def create_version_command(update, context):
            """Создать новую версию"""
            args = context.args
            if not args:
                await update.message.reply_text(
                    "Использование: /create_version <описание>"
                )
                return
            
            description = ' '.join(args)
            version_id = self.create_version(
                description=description,
                author=update.effective_user.username or update.effective_user.first_name
            )
            
            await update.message.reply_text(
                f"✅ Создана новая версия: {version_id[:8]}\n"
                f"📝 Описание: {description}"
            )
        
        async def rollback_command(update, context):
            """Откатиться к указанной версии"""
            args = context.args
            if not args:
                await update.message.reply_text(
                    "Использование: /rollback <version_id>"
                )
                return
            
            version_id = args[0]
            # Ищем версию по частичному совпадению
            full_version_id = self._find_version(version_id)
            
            if not full_version_id:
                await update.message.reply_text(f"❌ Версия {version_id} не найдена")
                return
            
            if self.rollback(full_version_id):
                await update.message.reply_text(
                    f"✅ Выполнен откат к версии {full_version_id[:8]}"
                )
            else:
                await update.message.reply_text(f"❌ Ошибка при откате")
        
        async def version_diff_command(update, context):
            """Показать различия между версиями"""
            args = context.args
            if len(args) < 2:
                await update.message.reply_text(
                    "Использование: /version_diff <version1> <version2>"
                )
                return
            
            v1 = self._find_version(args[0])
            v2 = self._find_version(args[1])
            
            if not v1 or not v2:
                await update.message.reply_text("❌ Одна из версий не найдена")
                return
            
            diff = self.compare_versions(v1, v2)
            
            text = f"📊 Различия между {v1[:8]} и {v2[:8]}:\n"
            text += f"Измененные файлы: {len(diff['changed'])}\n"
            text += f"Новые файлы: {len(diff['added'])}\n"
            text += f"Удаленные файлы: {len(diff['removed'])}\n"
            
            if diff['changed']:
                text += "\n📝 Измененные файлы:\n" + "\n".join(diff['changed'][:5])
            
            await update.message.reply_text(text)
        
        async def export_version_command(update, context):
            """Экспортировать версию в файл"""
            args = context.args
            version_id = args[0] if args else self.current_version
            
            if not version_id:
                await update.message.reply_text("❌ Укажите версию для экспорта")
                return
            
            full_version_id = self._find_version(version_id)
            if not full_version_id:
                await update.message.reply_text(f"❌ Версия {version_id} не найдена")
                return
            
            filename = self.export_version(full_version_id)
            if filename:
                await update.message.reply_document(
                    document=open(filename, 'rb'),
                    filename=f"version_{full_version_id[:8]}.zip",
                    caption=f"📦 Экспорт версии {full_version_id[:8]}"
                )
                os.unlink(filename)  # Удаляем временный файл
            else:
                await update.message.reply_text("❌ Ошибка при экспорте")
        
        async def import_version_command(update, context):
            """Импортировать версию из файла"""
            if not update.message.document:
                await update.message.reply_text("❌ Отправьте файл с версией")
                return
            
            file = await update.message.document.get_file()
            filename = f"temp_import_{int(time.time())}.zip"
            await file.download_to_drive(filename)
            
            version_id = self.import_version(filename)
            os.unlink(filename)
            
            if version_id:
                await update.message.reply_text(
                    f"✅ Импортирована версия {version_id[:8]}"
                )
            else:
                await update.message.reply_text("❌ Ошибка при импорте")
        
        # Регистрируем команды
        self.bot.register_handler('command', version_command, command='version')
        self.bot.register_handler('command', versions_list_command, command='versions')
        self.bot.register_handler('command', create_version_command, command='create_version')
        self.bot.register_handler('command', rollback_command, command='rollback')
        self.bot.register_handler('command', version_diff_command, command='version_diff')
        self.bot.register_handler('command', export_version_command, command='export_version')
        self.bot.register_handler('command', import_version_command, command='import_version')
    
    def _load_versions(self):
        """Загрузка информации о версиях"""
        versions_file = self.versions_dir / "versions.json"
        if versions_file.exists():
            with open(versions_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.current_version = data.get('current_version')
                self.versions = {
                    vid: VersionInfo(**vinfo) 
                    for vid, vinfo in data.get('versions', {}).items()
                }
    
    def _save_versions(self):
        """Сохранение информации о версиях"""
        versions_file = self.versions_dir / "versions.json"
        data = {
            'current_version': self.current_version,
            'versions': {
                vid: asdict(vinfo) for vid, vinfo in self.versions.items()
            }
        }
        with open(versions_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    def _calculate_file_hash(self, filepath: Path) -> str:
        """Вычисление хеша файла"""
        if not filepath.exists():
            return ""
        
        sha256 = hashlib.sha256()
        with open(filepath, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b''):
                sha256.update(chunk)
        return sha256.hexdigest()
    
    def _get_project_files(self) -> Dict[str, str]:
        """Получение всех файлов проекта с хешами"""
        files = {}
        project_root = Path.cwd()
        
        # Расширения файлов для отслеживания
        extensions = {'.py', '.json', '.yaml', '.yml', '.txt', '.md'}
        
        for filepath in project_root.rglob('*'):
            if filepath.is_file() and filepath.suffix in extensions:
                # Исключаем директорию versions
                if 'versions' not in filepath.parts:
                    rel_path = str(filepath.relative_to(project_root))
                    files[rel_path] = self._calculate_file_hash(filepath)
        
        return files
    
    def _get_dependencies(self) -> Dict[str, str]:
        """Получение зависимостей проекта"""
        deps = {}
        
        # Проверяем requirements.txt
        req_file = Path("requirements.txt")
        if req_file.exists():
            with open(req_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        if '==' in line:
                            name, version = line.split('==', 1)
                            deps[name] = version
                        else:
                            deps[line] = 'latest'
        
        return deps
    
    def _get_bot_config(self) -> Dict[str, Any]:
        """Получение конфигурации бота"""
        config = {
            'token_hash': hashlib.sha256(self.bot.token.encode()).hexdigest()[:16],
            'handlers_count': len(self.bot.container.registry.get('handlers', [])),
            'services_count': len(self.bot.container.registry)
        }
        return config
    
    def _find_version(self, partial_id: str) -> Optional[str]:
        """Поиск версии по частичному идентификатору"""
        for vid in self.versions:
            if vid.startswith(partial_id):
                return vid
        return None
    
    def create_version(self, description: str, author: str = "system") -> str:
        """Создание новой версии"""
        version_id = hashlib.sha256(
            f"{time.time()}{description}".encode()
        ).hexdigest()
        
        version_info = VersionInfo(
            version_id=version_id,
            timestamp=time.time(),
            description=description,
            author=author,
            files_hash=self._get_project_files(),
            dependencies=self._get_dependencies(),
            bot_config=self._get_bot_config(),
            parent_version=self.current_version
        )
        
        self.versions[version_id] = version_info
        self.current_version = version_id
        
        # Сохраняем состояние
        self._save_versions()
        
        # Копируем файлы в директорию версии
        version_dir = self.versions_dir / version_id[:8]
        version_dir.mkdir(exist_ok=True)
        
        # Сохраняем метаданные версии
        with open(version_dir / "metadata.json", 'w', encoding='utf-8') as f:
            json.dump(asdict(version_info), f, indent=2, ensure_ascii=False)
        
        logger = self.bot.container.get('logger')
        logger.info(f"Created version {version_id[:8]}: {description}")
        
        return version_id
    
    def rollback(self, version_id: str) -> bool:
        """Откат к указанной версии"""
        if version_id not in self.versions:
            return False
        
        version_info = self.versions[version_id]
        version_dir = self.versions_dir / version_id[:8]
        
        if not version_dir.exists():
            return False
        
        # Восстанавливаем файлы из версии
        try:
            # Сначала создаем бэкап текущего состояния
            backup_version = self.create_version(
                description=f"Auto-backup before rollback to {version_id[:8]}",
                author="system"
            )
            
            # Восстанавливаем файлы
            for filepath in Path.cwd().rglob('*'):
                if filepath.is_file() and 'versions' not in filepath.parts:
                    rel_path = str(filepath.relative_to(Path.cwd()))
                    if rel_path in version_info.files_hash:
                        # Файл существует в версии - проверяем, нужно ли восстанавливать
                        current_hash = self._calculate_file_hash(filepath)
                        if current_hash != version_info.files_hash[rel_path]:
                            # Файл изменен - восстанавливаем из версии
                            version_file = version_dir / rel_path
                            if version_file.exists():
                                shutil.copy2(version_file, filepath)
            
            self.current_version = version_id
            self._save_versions()
            
            logger = self.bot.container.get('logger')
            logger.info(f"Rolled back to version {version_id[:8]}")
            
            return True
            
        except Exception as e:
            logger = self.bot.container.get('logger')
            logger.error(f"Rollback failed: {e}")
            return False
    
    def compare_versions(self, version1: str, version2: str) -> Dict[str, List[str]]:
        """Сравнение двух версий"""
        if version1 not in self.versions or version2 not in self.versions:
            return {'changed': [], 'added': [], 'removed': []}
        
        v1 = self.versions[version1]
        v2 = self.versions[version2]
        
        files1 = set(v1.files_hash.keys())
        files2 = set(v2.files_hash.keys())
        
        changed = []
        for file in files1 & files2:
            if v1.files_hash[file] != v2.files_hash[file]:
                changed.append(file)
        
        added = list(files2 - files1)
        removed = list(files1 - files2)
        
        return {
            'changed': sorted(changed),
            'added': sorted(added),
            'removed': sorted(removed)
        }
    
    def export_version(self, version_id: str, output_file: Optional[str] = None) -> Optional[str]:
        """Экспорт версии в zip архив"""
        if version_id not in self.versions:
            return None
        
        if not output_file:
            output_file = f"version_export_{version_id[:8]}_{int(time.time())}.zip"
        
        version_info = self.versions[version_id]
        version_dir = self.versions_dir / version_id[:8]
        
        with zipfile.ZipFile(output_file, 'w', zipfile.ZIP_DEFLATED) as zf:
            # Добавляем метаданные
            zf.writestr('metadata.json', json.dumps(asdict(version_info), indent=2))
            
            # Добавляем файлы версии
            if version_dir.exists():
                for filepath in version_dir.rglob('*'):
                    if filepath.is_file() and filepath.name != 'metadata.json':
                        arcname = f"files/{filepath.relative_to(version_dir)}"
                        zf.write(filepath, arcname)
        
        return output_file
    
    def import_version(self, zip_file: str) -> Optional[str]:
        """Импорт версии из zip архива"""
        try:
            with zipfile.ZipFile(zip_file, 'r') as zf:
                # Читаем метаданные
                if 'metadata.json' not in zf.namelist():
                    return None
                
                metadata = json.loads(zf.read('metadata.json'))
                version_info = VersionInfo(**metadata)
                
                # Создаем директорию для версии
                version_dir = self.versions_dir / version_info.version_id[:8]
                version_dir.mkdir(exist_ok=True)
                
                # Извлекаем файлы
                for file in zf.namelist():
                    if file.startswith('files/'):
                        target_path = version_dir / Path(file).relative_to('files')
                        target_path.parent.mkdir(parents=True, exist_ok=True)
                        zf.extract(file, version_dir.parent)
                        
                        # Перемещаем файл в правильное место
                        extracted = version_dir.parent / file
                        if extracted.exists():
                            shutil.move(str(extracted), str(target_path))
                
                # Сохраняем метаданные
                with open(version_dir / "metadata.json", 'w', encoding='utf-8') as f:
                    json.dump(metadata, f, indent=2, ensure_ascii=False)
                
                # Добавляем в список версий
                self.versions[version_info.version_id] = version_info
                self._save_versions()
                
                return version_info.version_id
                
        except Exception as e:
            logger = self.bot.container.get('logger')
            logger.error(f"Import failed: {e}")
            return None

# Декоратор для автоматического создания версий
def auto_version(description: str = None):
    """Декоратор для автоматического создания версии при изменении функции"""
    def decorator(func: Callable):
        async def wrapper(self, *args, **kwargs):
            result = await func(self, *args, **kwargs)
            
            # Создаем версию после выполнения функции
            if hasattr(self, 'version_control'):
                func_desc = description or f"Auto-version from {func.__name__}"
                self.version_control.create_version(
                    description=func_desc,
                    author="auto"
                )
            
            return result
        return wrapper
    return decorator

# Пример использования с вашим контейнером
if __name__ == "__main__":
    from telegram.ext import Application
    
    # Создаем контейнер бота
    bot_container = TelegramBotContainer("YOUR_TOKEN", container=None)
    
    # Добавляем систему контроля версий
    vc = VersionControl(bot_container)
    
    # Пример использования с декоратором
    class MyBotHandlers:
        def __init__(self, version_control):
            self.vc = version_control
        
        @auto_version("Updated start command")
        async def start(self, update, context):
            await update.message.reply_text("Hello!")
            
        @auto_version("Added help command")
        async def help_command(self, update, context):
            await update.message.reply_text("Help message")
    
    # Регистрируем обработчики
    handlers = MyBotHandlers(vc)
    bot_container.register_handler('command', handlers.start, command='start')
    bot_container.register_handler('command', handlers.help_command, command='help')
    
    # Запускаем бота
    bot_container.run_polling()