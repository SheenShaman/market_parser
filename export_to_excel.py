import pandas as pd

from models import Product


def export_to_excel(products: list[Product], filename: str = "products.xlsx"):
    """
    Экспорт списка Product в XLSX
    """
    rows = []

    for p in products:
        rows.append(
            {
                "URL": p.url,
                "Артикул": p.article,
                "Название": p.name,
                "Цена": p.price,
                "Описание": p.description,
                "Продавец": p.seller_name,
                "URL продавца": p.seller_url,
                "Размеры": ", ".join(p.sizes) if p.sizes else "",
                "Остаток": p.stock,
                "Рейтинг": p.rating,
                "Отзывы": p.feedbacks,
                "Изображения": ", ".join(p.images) if p.images else "",
                "Характеристики": (
                    "; ".join(f"{k}: {v}" for k, v in p.characteristics.items())
                    if p.characteristics
                    else ""
                ),
            }
        )

    df = pd.DataFrame(rows)
    df.to_excel(filename, index=False, engine="openpyxl")
