import logging
import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

# Импортируем сервис контроля версий
from control_version import VersionControlService


class VersionControlBotExtension:
    """Расширение для TelegramBotContainer для работы с контролем версий"""

    def __init__(self, bot_container, vcs_service: VersionControlService):
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

class MyFileFormat:
    """Класс для работы с кастомным форматом файлов"""
    def __init__(self, extension=".con"):
        self.extension = extension

    def save_data(self, data, filename):
        """Сохраняет данные в файл с кастомным расширением"""
        if not filename.endswith(self.extension):
            filename += self.extension

        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print(f"Файл сохранен как: {filename}")
        return filename

    def load_data(self, filename):
        """Загружает данные из файла с кастомным расширением"""
        if not filename.endswith(self.extension):
            filename += self.extension

        try:
            with open(filename, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data
        except FileNotFoundError:
            print(f"Файл {filename} не найден")
            return None