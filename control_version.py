# version_control.py
import json
import hashlib
import time
from datetime import datetime
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, asdict
from pathlib import Path
import logging
import asyncio

# Импортируем необходимые классы из telegram.ext
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler

# Класс Container из вашего оригинального кода
class Container:
    def __init__(self):
        self._services = {}
        self._factories = {}
    
    def register(self, name: str, service: Any):
        """Регистрация готового сервиса"""
        self._services[name] = service
    
    def factory(self, name: str, factory_func: Callable):
        """Регистрация фабрики"""
        self._factories[name] = factory_func
    
    def get(self, name: str) -> Any:
        """Получение сервиса"""
        if name in self._services:
            return self._services[name]
        elif name in self._factories:
            service = self._factories[name](self)
            self._services[name] = service
            return service
        raise KeyError(f"Service '{name}' not found")

# Класс TelegramBotContainer из вашего оригинального кода
class TelegramBotContainer:
    def __init__(self, token: str):
        self.container = Container()
        self.token = token
        
        # Регистрируем основные зависимости
        self._register_core_services()
        
    def _register_core_services(self):
        """Регистрация основных сервисов"""
        self.container.factory('application', self._create_application)
        
        # Логгер
        logging.basicConfig(level=logging.INFO)
        self.container.register('logger', logging.getLogger(__name__))
        
    def _create_application(self, container: Container) -> Application:
        """Фабрика для создания Application"""
        return Application.builder().token(self.token).build()
        
    def register_handler(self, handler_type: str, callback: Callable, **kwargs):
        """Регистрация обработчиков"""
        app = self.container.get('application')
        
        if handler_type == 'command':
            command = kwargs.get('command', 'start')
            app.add_handler(CommandHandler(command, callback))
        elif handler_type == 'message':
            app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, callback))
        elif handler_type == 'callback_query':
            app.add_handler(CallbackQueryHandler(callback))
            
    def register_service(self, name: str, service: Any):
        """Регистрация кастомного сервиса"""
        self.container.register(name, service)
        
    def register_factory(self, name: str, factory_func: Callable):
        """Регистрация фабрики"""
        self.container.factory(name, factory_func)
        
    async def run(self):
        """Запуск бота"""
        app = self.container.get('application')
        
        # Инициализация и запуск
        await app.initialize()
        await app.start()
        
        # Запуск polling
        await app.updater.start_polling()
        
        logger = self.container.get('logger')
        logger.info("Bot started!")
        
        # Бесконечный цикл
        try:
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            logger.info("Bot stopping...")
            await app.updater.stop()
            await app.stop()
            await app.shutdown()
        
    def run_polling(self):
        """Запуск в режиме polling"""
        try:
            asyncio.run(self.run())
        except KeyboardInterrupt:
            logger = self.container.get('logger')
            logger.info("Bot stopped by user")

# КОД КОНТРОЛЯ ВЕРСИЙ
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
        """
        Добавление нового файла в систему контроля версий
        """
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
        """
        Создание новой версии файла
        """
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
        """
        Получение содержимого файла по версии
        """
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
        """
        Список всех версий файла
        """
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
        """
        Создание новой ветки
        """
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
        """
        Переключение на указанную версию
        """
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
        """
        Сравнение двух версий файла
        """
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
        """
        Получение истории изменений
        """
        versions = self.list_versions(filepath)
        return versions[:limit]


class VersionControlBotExtension:
    """Расширение для TelegramBotContainer для работы с контролем версий"""
    
    def __init__(self, bot_container: TelegramBotContainer, vcs_service: VersionControlService):
        self.bot = bot_container
        self.vcs = vcs_service
        self.logger = bot_container.container.get('logger')
        
        bot_container.register_service('version_control', self.vcs)
        self._register_handlers()
    
    def _register_handlers(self):
        """Регистрация обработчиков команд"""
        
        async def vcs_commit_command(update, context):
            try:
                args = context.args
                if len(args) < 2:
                    await update.message.reply_text(
                        "Использование: /vcs_commit <filepath> <description>\n"
                        "Пример: /vcs_commit config.json Обновление настроек"
                    )
                    return
                
                filepath = args[0]
                description = ' '.join(args[1:])
                
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        content = f.read()
                except FileNotFoundError:
                    await update.message.reply_text(f"❌ Файл {filepath} не найден")
                    return
                
                author = update.effective_user.username or update.effective_user.first_name or "Unknown"
                
                if filepath in self.vcs.files_index:
                    version_id = self.vcs.commit(filepath, content, author, description)
                    await update.message.reply_text(
                        f"✅ Создана версия {version_id[:8]} для {filepath}"
                    )
                else:
                    version_id = self.vcs.add_file(filepath, content, author, description)
                    await update.message.reply_text(
                        f"✅ Файл {filepath} добавлен в контроль версий\n"
                        f"Версия: {version_id[:8]}"
                    )
            except Exception as e:
                await update.message.reply_text(f"❌ Ошибка: {str(e)}")
        
        async def vcs_history_command(update, context):
            try:
                args = context.args
                if not args:
                    await update.message.reply_text(
                        "Использование: /vcs_history <filepath> [limit]\n"
                        "Пример: /vcs_history config.json 5"
                    )
                    return
                
                filepath = args[0]
                limit = 10
                if len(args) > 1:
                    try:
                        limit = int(args[1])
                    except ValueError:
                        await update.message.reply_text("Лимит должен быть числом")
                        return
                
                history = self.vcs.get_history(filepath, limit)
                
                if not history:
                    await update.message.reply_text(f"Нет истории для файла {filepath}")
                    return
                
                message = f"📜 История версий для {filepath}:\n\n"
                for i, ver in enumerate(history, 1):
                    date = datetime.fromtimestamp(ver['timestamp']).strftime("%Y-%m-%d %H:%M")
                    current = " (текущая)" if ver.get('is_current') else ""
                    message += f"{i}. {ver['version_id'][:8]}{current}\n"
                    message += f"   Автор: {ver['author']}\n"
                    message += f"   Дата: {date}\n"
                    message += f"   Описание: {ver['description']}\n"
                    message += f"   Ветка: {ver['branch']}\n\n"
                
                if len(message) > 4096:
                    for i in range(0, len(message), 4096):
                        await update.message.reply_text(message[i:i+4096])
                else:
                    await update.message.reply_text(message)
            except Exception as e:
                await update.message.reply_text(f"❌ Ошибка: {str(e)}")
        
        async def vcs_checkout_command(update, context):
            try:
                args = context.args
                if len(args) < 2:
                    await update.message.reply_text(
                        "Использование: /vcs_checkout <filepath> <version_id>\n"
                        "Пример: /vcs_checkout config.json a1b2c3d4"
                    )
                    return
                
                filepath = args[0]
                version_id = args[1]
                
                content = self.vcs.get_version(filepath, version_id)
                if content is None:
                    await update.message.reply_text(f"❌ Версия {version_id} не найдена")
                    return
                
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(content)
                
                if self.vcs.checkout(filepath, version_id):
                    await update.message.reply_text(
                        f"✅ Переключено на версию {version_id[:8]} для {filepath}"
                    )
                else:
                    await update.message.reply_text("❌ Не удалось переключить версию")
            except Exception as e:
                await update.message.reply_text(f"❌ Ошибка: {str(e)}")
        
        async def vcs_branch_command(update, context):
            try:
                args = context.args
                if len(args) < 2:
                    await update.message.reply_text(
                        "Использование:\n"
                        "/vcs_branch create <filepath> <branch_name> [from_version]\n"
                        "/vcs_branch list <filepath>"
                    )
                    return
                
                action = args[0]
                
                if action == "create" and len(args) >= 3:
                    filepath = args[1]
                    branch_name = args[2]
                    from_version = args[3] if len(args) > 3 else None
                    
                    if self.vcs.create_branch(filepath, branch_name, from_version):
                        await update.message.reply_text(f"✅ Создана ветка {branch_name} для {filepath}")
                    else:
                        await update.message.reply_text("❌ Не удалось создать ветку")
                
                elif action == "list" and len(args) >= 2:
                    filepath = args[1]
                    
                    if filepath not in self.vcs.files_index:
                        await update.message.reply_text(f"❌ Файл {filepath} не найден")
                        return
                    
                    branches = self.vcs.files_index[filepath].branches
                    message = f"🌿 Ветки для {filepath}:\n\n"
                    for branch, version in branches.items():
                        current = " (текущая)" if version == self.vcs.files_index[filepath].current_version else ""
                        message += f"  • {branch}: {version[:8]}{current}\n"
                    
                    await update.message.reply_text(message)
                else:
                    await update.message.reply_text("❌ Неверные аргументы")
            except Exception as e:
                await update.message.reply_text(f"❌ Ошибка: {str(e)}")
        
        async def vcs_diff_command(update, context):
            try:
                args = context.args
                if len(args) < 3:
                    await update.message.reply_text(
                        "Использование: /vcs_diff <filepath> <version1> <version2>\n"
                        "Пример: /vcs_diff config.json a1b2c3d4 e5f6g7h8"
                    )
                    return
                
                filepath = args[0]
                version1 = args[1]
                version2 = args[2]
                
                diff = self.vcs.diff(filepath, version1, version2)
                
                if diff is None:
                    await update.message.reply_text("❌ Не удалось сравнить версии")
                    return
                
                if diff == "Files are identical":
                    await update.message.reply_text("📊 Файлы идентичны")
                    return
                
                message = f"📊 Различия между {version1[:8]} и {version2[:8]}:\n\n{diff}"
                
                if len(message) > 4096:
                    for i in range(0, len(message), 4096):
                        await update.message.reply_text(message[i:i+4096])
                else:
                    await update.message.reply_text(message)
            except Exception as e:
                await update.message.reply_text(f"❌ Ошибка: {str(e)}")
        
        async def vcs_help_command(update, context):
            help_text = """
📚 Команды контроля версий:

/vcs_commit <filepath> <description> - Сохранить новую версию файла
/vcs_history <filepath> [limit] - Показать историю версий
/vcs_checkout <filepath> <version> - Переключиться на другую версию
/vcs_branch create <filepath> <branch> [from] - Создать ветку
/vcs_branch list <filepath> - Показать ветки
/vcs_diff <filepath> <ver1> <ver2> - Сравнить версии
/vcs_help - Показать эту справку

Примеры:
/vcs_commit config.json "Обновление настроек"
/vcs_history config.json 5
/vcs_checkout config.json a1b2c3d4
            """
            await update.message.reply_text(help_text)
        
        # Регистрируем команды
        self.bot.register_handler('command', vcs_commit_command, command='vcs_commit')
        self.bot.register_handler('command', vcs_history_command, command='vcs_history')
        self.bot.register_handler('command', vcs_checkout_command, command='vcs_checkout')
        self.bot.register_handler('command', vcs_branch_command, command='vcs_branch')
        self.bot.register_handler('command', vcs_diff_command, command='vcs_diff')
        self.bot.register_handler('command', vcs_help_command, command='vcs_help')
        
        self.logger.info("Version control commands registered")


# Пример использования
async def main():
    # Создаем бота (замените на ваш реальный токен)
    bot = TelegramBotContainer("YOUR_TOKEN_HERE")
    
    # Создаем сервис контроля версий
    vcs_service = VersionControlService(storage_path="./vcs_data")
    
    # Добавляем расширение для контроля версий
    vcs_extension = VersionControlBotExtension(bot, vcs_service)
    
    # Регистрируем обработчик start
    async def start_command(update, context):
        await update.message.reply_text(
            "👋 Привет! Я бот с контролем версий.\n"
            "Используй /vcs_help для списка команд."
        )
    
    bot.register_handler('command', start_command, command='start')
    
    # Запускаем бота
    await bot.run()

if __name__ == "__main__":
    asyncio.run(main())