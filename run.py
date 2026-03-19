#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Файл для запуска Telegram бота с системой контроля версий
Импортирует все необходимые классы из модулей и запускает бота через интерактивное меню
"""

import asyncio
import sys
import os
from pathlib import Path


# Добавляем текущую директорию в путь для импорта
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Импортируем главную функцию из main.py
from main import main

if __name__ == "__main__":
    main()