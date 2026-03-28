import zipfile
import pandas as pd
from io import BytesIO

def create_sample_zip():
    # Создаем Excel
    sample_data = {
        'name': ['HOOKAH 5000', 'ELF BAR 3000', 'SALT NICOTINE 30ml'],
        'description': ['Вкус: Арбуз, Крепость: 5%', 'Вкус: Манго, Крепость: 5%', 'Крепость: 20mg, Объем: 30ml'],
        'price': [1500, 1200, 800],
        'cost_price': [1000, 800, 500],
        'stock': [50, 30, 100],
        'photo_filename': ['hookah_5000.jpg', 'elf_bar_3000.jpg', 'salt_nicotine.jpg']
    }
    
    df = pd.DataFrame(sample_data)
    excel_buffer = BytesIO()
    with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Товары')
    
    # Создаем ZIP
    with zipfile.ZipFile('sample_products_with_photos.zip', 'w') as zipf:
        zipf.writestr('products.xlsx', excel_buffer.getvalue())
        
        # Создаем пустые файлы для примера
        zipf.writestr('hookah_5000.jpg', b'')
        zipf.writestr('elf_bar_3000.jpg', b'')
        zipf.writestr('salt_nicotine.jpg', b'')
    
    print("✅ Пример ZIP архива создан: sample_products_with_photos.zip")

if __name__ == "__main__":
    create_sample_zip()