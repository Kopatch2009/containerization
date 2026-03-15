from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler
import logging
import asyncio
from typing import Any, Callable, Optional

# Предполагаем, что класс Container существует
# Если нет, добавим простую реализацию
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
            # Используем asyncio.sleep для бесконечного цикла
            while True:
                await asyncio.sleep(3600)  # Спим час
        except asyncio.CancelledError:
            # Корректное завершение при отмене
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

# Пример использования:
async def main():
    # Создаем бота
    bot = TelegramBotContainer("YOUR_TOKEN_HERE")
    
    # Регистрируем обработчики
    async def start_command(update, context):
        await update.message.reply_text("Hello!")
    
    async def echo_message(update, context):
        await update.message.reply_text(update.message.text)
    
    bot.register_handler('command', start_command, command='start')
    bot.register_handler('message', echo_message)
    
    # Запускаем
    await bot.run()

if __name__ == "__main__":
    asyncio.run(main())