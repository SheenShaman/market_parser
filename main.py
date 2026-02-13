import logging
import asyncio
import httpx

from constants import HEADERS, SEARCH_URL, QUERY
from models import Product
from logger import setup_logging


setup_logging()
logger = logging.getLogger(__name__)


async def safe_get(client: httpx.AsyncClient, params):
    for attempt in range(5):
        try:
            response = await client.get(SEARCH_URL, params=params)
            if response.status_code == 429:
                wait = 2 ** attempt
                print(f"429, ждём {wait} сек...")
                await asyncio.sleep(wait)
                continue

            response.raise_for_status()
            return response.json()

        except httpx.RequestError:
            wait = 2 ** attempt
            await asyncio.sleep(wait)

    raise Exception("Слишком много 429")


async def get_page(client: httpx.AsyncClient, page: int):
    params = {
        "appType": 1,
        "curr": "rub",
        "dest": -1257786,
        "query": QUERY,
        "page": page,
        "resultset": "catalog",
        "sort": "popular",
    }

    return await safe_get(client, params)


async def get_card_json(client: httpx.AsyncClient, nm_id: int) -> tuple[dict, str] | None:
    vol = nm_id // 100000
    part = nm_id // 1000

    tasks = []
    urls = []

    for basket in range(1, 30):
        basket_url = (
            f"https://basket-{basket}.wbbasket.ru/"
            f"vol{vol}/part{part}/{nm_id}"
        )
        urls.append(basket_url)
        tasks.append(client.get(basket_url + "/info/ru/card.json", timeout=2))

    responses = await asyncio.gather(*tasks, return_exceptions=True)

    for response, basket_url in zip(responses, urls):
        if isinstance(response, Exception):
            continue
        if response.status_code == 200:
            return response.json(), basket_url

    return None, None


async def build_product(client, search_item, semaphore) -> Product:
    async with semaphore:
        nm_id = search_item["id"]
        card_data, basket_url = await get_card_json(client, nm_id)

        if not card_data:
            logger.warning(f"Не найдена карточка {nm_id}")
            return None

        url = f"https://www.wildberries.ru/catalog/{nm_id}/detail.aspx"
        name = search_item.get("name")
        rating = search_item.get("reviewRating", 0)
        feedbacks = search_item.get("feedbacks", 0)
        seller_name = search_item.get("supplier")
        seller_url = f"https://www.wildberries.ru/seller/{search_item.get('supplierId')}"
        description = card_data.get("description")

        # считаем среднюю цену по размерам
        sizes_data = search_item.get("sizes", [])
        prices = []
        for size in sizes_data:
            price_info = size.get("price", {})
            product_price = price_info.get("product")
            if product_price:
                prices.append(product_price)
        if prices:
            price = (sum(prices) / len(prices)) / 100
        else:
            price = 0

        # считаем кол-во остатков по размерам
        sizes = []
        stock = 0
        for size in search_item.get("sizes", []):
            size_name = size.get("name")
            sizes.append(size_name)
            if size.get("stocks"):
                for stock_item in size["stocks"]:
                    stock += stock_item.get("qty", 0)

        # собираем характеристики
        characteristics = {}
        for option in card_data.get("options", []):
            key = option.get("name")
            value = option.get("value")
            characteristics[key] = value

        photo_count = card_data.get("media", {}).get("photo_count", 0)
        images = [
            f"{basket_url}/images/c516x688/{i}.webp"
            for i in range(1, photo_count + 1)
        ]

        return Product(
            url=url,
            article=nm_id,
            name=name,
            price=price,
            description=description,
            images=images,
            characteristics=characteristics,
            seller_name=seller_name,
            seller_url=seller_url,
            sizes=sizes,
            stock=stock,
            rating=rating,
            feedbacks=feedbacks,
        )


async def main():
    semaphore = asyncio.Semaphore(10)
    async with httpx.AsyncClient(
        headers=HEADERS,
        timeout=20,
    ) as client:
        page_data = await get_page(client,1)
        items = page_data["products"][:5]
        tasks = [
            build_product(client, item, semaphore)
            for item in items
        ]
        results = await asyncio.gather(*tasks)
        products = [p for p in results if p]
        logger.info(f"Собрано товаров: {len(products)}")
        logger.info(f"Товары: {[p for p in results if p]}")
        return products


if __name__ == "__main__":
    products = asyncio.run(main())
