import os
import sys
import asyncio
from pathlib import Path
from datetime import datetime

# Импортируем утилиты из custom_expansion
from cus_exp import MyFileFormat


def test_file_format():
    """Тестирование класса MyFileFormat"""
    print("\n" + "="*50)
    print("Тестирование MyFileFormat")
    print("="*50)

    app = MyFileFormat(".mydata")

    # Сохранение данных
    my_data = {
        "name": "Мой проект",
        "version": 1.0,
        "items": [1, 2, 3, 4, 5],
        "created": datetime.now().isoformat()
    }

    filename = app.save_data(my_data, "project_test")
    print(f"Данные сохранены в {filename}")

    # Загрузка данных
    loaded_data = app.load_data("project_test.mydata")
    print("Загруженные данные:", loaded_data)

    return loaded_data


def check_environment():
    """Проверка окружения перед запуском бота"""
    print("🔍 Проверка окружения...")

    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        print("❌ Токен бота не найден в переменных окружения!")
        print("   Установите переменную TELEGRAM_BOT_TOKEN или укажите токен в коде")
        return None

    print("✅ Токен найден")

    Path("./vcs_data").mkdir(exist_ok=True)
    Path("./vcs_data/files").mkdir(exist_ok=True)
    print("✅ Директории созданы")

    return token


def show_info():
    """Показать информацию о системе"""
    print("\n" + "="*50)
    print("📊 ИНФОРМАЦИЯ О СИСТЕМЕ")
    print("="*50)
    print("\nКоманды бота:")
    print("  /start - Приветственное сообщение")
    print("  /vcs_commit <filepath> <description> - Сохранить версию файла")
    print("  /vcs_history <filepath> [limit] - Показать историю версий")
    print("  /vcs_checkout <filepath> <version> - Переключиться на версию")
    print("  /vcs_branch create <filepath> <branch> [from] - Создать ветку")
    print("  /vcs_branch list <filepath> - Показать ветки")
    print("  /vcs_diff <filepath> <ver1> <ver2> - Сравнить версии")
    print("  /vcs_help - Показать справку")

    print("\n📁 Структура директорий:")
    print("  ./vcs_data/ - Хранилище данных контроля версий")
    print("  ./vcs_data/files/ - Файлы версий")
    print("  ./vcs_data/index.json - Индекс всех файлов")

    print("\n🔧 Классы системы:")
    print("  • TelegramBotContainer - Контейнер для бота")
    print("  • VersionControlService - Сервис контроля версий")
    print("  • VersionControlBotExtension - Расширение для бота")
    print("  • MyFileFormat - Работа с кастомными файлами")

    input("\nНажмите Enter для продолжения...")


def interactive_menu():
    """Интерактивное меню для выбора режима запуска"""
    print("\n" + "="*50)
    print("🤖 TELEGRAM БОТ С КОНТРОЛЕМ ВЕРСИЙ")
    print("="*50)
    print("\nВыберите режим запуска:")
    print("  1. Запустить Telegram бота")
    print("  2. Протестировать MyFileFormat")
    print("  3. Показать информацию о системе")
    print("  4. Выход")

    choice = input("\nВаш выбор (1-4): ").strip()

    if choice == "1":
        return "run_bot"
    elif choice == "2":
        return "test_format"
    elif choice == "3":
        return "info"
    elif choice == "4":
        return "exit"
    else:
        print("❌ Неверный выбор!")
        return "invalid"