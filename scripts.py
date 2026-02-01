from telegram.ext import Application, CommandHandler, MessageHandler, filters
import logging
import asyncio

class TelegramBotContainer:
    def __init__(self, token: str, container):
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
            from telegram.ext import CallbackQueryHandler
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
        await app.initialize()
        await app.start()
        await app.updater.start_polling()  # Для polling
        
        logger = self.container.get('logger')
        logger.info("Bot started!")
        
        # Бесконечный цикл
        await asyncio.Event().wait()
        
    def run_polling(self):
        """Запуск в режиме polling"""
        asyncio.run(self.run())