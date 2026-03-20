import asyncio
import logging
from typing import Any, Callable
import os
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler
import sys


# Импортируем созданные модули
from control_version import VersionControlService
from cus_exp import VersionControlBotExtension
from scripts import check_environment, interactive_menu, test_file_format, show_info


class Container:
    """Контейнер для внедрения зависимостей"""
    def __init__(self):
        self._services = {}
        self._factories = {}

    def register(self, name: str, service: Any):
        self._services[name] = service

    def factory(self, name: str, factory_func: Callable):
        self._factories[name] = factory_func

    def get(self, name: str) -> Any:
        if name in self._services:
            return self._services[name]
        elif name in self._factories:
            service = self._factories[name](self)
            self._services[name] = service
            return service
        raise KeyError(f"Service '{name}' not found")


class TelegramBotContainer:
    """Контейнер для Telegram бота"""
    def __init__(self, token: str):
        self.container = Container()
        self.token = token
        self._register_core_services()

    def _register_core_services(self):
        self.container.factory('application', self._create_application)
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        self.container.register('logger', logging.getLogger(__name__))

    def _create_application(self, container: Container) -> Application:
        return Application.builder().token(self.token).build()

    def register_handler(self, handler_type: str, callback: Callable, **kwargs):
        app = self.container.get('application')
        if handler_type == 'command':
            command = kwargs.get('command', 'start')
            app.add_handler(CommandHandler(command, callback))
        elif handler_type == 'message':
            app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, callback))
        elif handler_type == 'callback_query':
            app.add_handler(CallbackQueryHandler(callback))

    def register_service(self, name: str, service: Any):
        self.container.register(name, service)

    def register_factory(self, name: str, factory_func: Callable):
        self.container.factory(name, factory_func)

    async def run(self):
        app = self.container.get('application')
        logger = self.container.get('logger')

        await app.initialize()
        await app.start()
        await app.updater.start_polling()

        logger.info("Bot started!")

        try:
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            logger.info("Bot stopping...")
            await app.updater.stop()
            await app.stop()
            await app.shutdown()

    def run_polling(self):
        try:
            asyncio.run(self.run())
        except KeyboardInterrupt:
            logger = self.container.get('logger')
            logger.info("Bot stopped by user")


async def run_bot(token: str):
    """Запуск бота с контролем версий"""
    bot = TelegramBotContainer(token)
    vcs_service = VersionControlService(storage_path="./vcs_data")
    vcs_extension = VersionControlBotExtension(bot, vcs_service)

    async def start_command(update, context):
        await update.message.reply_text(
            "👋 Привет! Я бот с контролем версий.\n"
            "Используй /vcs_help для списка команд."
        )

    bot.register_handler('command', start_command, command='start')
    await bot.run()


async def async_main():
    """Асинхронная главная функция с меню"""
    while True:
        mode = interactive_menu()

        if mode == "run_bot":
            token = check_environment()
            if token:
                print("\n🚀 Запуск бота...\n")
                try:
                    await run_bot(token)
                except KeyboardInterrupt:
                    print("\n🛑 Бот остановлен пользователем")
                except Exception as e:
                    print(f"\n❌ Ошибка при запуске бота: {e}")
            else:
                print("\n⚠️  Невозможно запустить бота без токена")
                token_input = input("Введите токен бота (или Enter для выхода): ").strip()
                if token_input:
                    os.environ["TELEGRAM_BOT_TOKEN"] = token_input
                    continue

        elif mode == "test_format":
            print("\n🧪 Тестирование MyFileFormat...")
            result = test_file_format()
            print("\n✅ Тест завершен")
            input("\nНажмите Enter для продолжения...")

        elif mode == "info":
            show_info()

        elif mode == "exit":
            print("\n👋 До свидания!")
            break

        elif mode == "invalid":
            continue


def main():
    """Синхронная точка входа"""
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        print("\n\n👋 Программа завершена пользователем")
    except Exception as e:
        print(f"\n❌ Непредвиденная ошибка: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()