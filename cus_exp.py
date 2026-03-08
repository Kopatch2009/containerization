import json
import pickle

class MyFileFormat:
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

# Использование
app = MyFileFormat(".con")

# Сохранение данных
my_data = {
    "name": "Мой проект",
    "version": 1.0,
    "items": [1, 2, 3, 4, 5]
}
app.save_data(my_data, "project")

# Загрузка данных
loaded_data = app.load_data("project.mydata")
print(loaded_data)