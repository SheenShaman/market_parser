import logging
import asyncio
import httpx

from constants import DETAIL_URL, FAILURE_STATUS, HEADERS, SEARCH_URL, \
    PARAMS_TEMPLATE, MAX_BASKET
from models import Product, DetailProduct
from logger import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

BASKET_CACHE = {}


async def safe_get_json(
        client: httpx.AsyncClient,
        url: str,
        params: dict | None = None,
) -> dict | None:
    """
    Делает запрос, если падает ошибка - делает повторный запрос
    """
    for attempt in range(5):
        try:
            response = await client.get(url, params=params)
            if response.status_code in FAILURE_STATUS:
                wait = min(2 ** attempt, 8)
                logger.warning(
                    f"{url} | {response.status_code} | retry in {wait}s"
                )
                await asyncio.sleep(wait)
                continue

            response.raise_for_status()
            return response.json()

        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            wait = min(2 ** attempt, 8)
            await asyncio.sleep(wait)
    return None


async def get_detail_data(
        client: httpx.AsyncClient, nm_id: str, semaphore: asyncio.Semaphore
) -> DetailProduct | None:
    """
    Возвращает данные товара по detail_url
    """
    async with semaphore:
        params = {
            "appType": 1,
            "curr": "rub",
            "dest": -1257786,
            "nm": str(nm_id),
        }
        data = await safe_get_json(client, DETAIL_URL, params=params)
        if not data:
            return None
        products = data.get("products") or data.get("data", {}).get("products")
        if not products:
            return None
        product = products[0]
        # считаем среднюю цену по размера
        sizes_data = product.get("sizes", [])
        stock = 0
        for size in sizes_data:
            for s in size.get("stocks", []):
                stock += s.get("qty", 0)
        if stock == 0:
            return None
        prices = [
            size.get("price", {}).get("product")
            for size in sizes_data
            if size.get("price", {}).get("product")
        ]
        price = (sum(prices) / len(prices)) / 100 if prices else 0

        return DetailProduct(
            id=product.get("id"),
            name=product.get("name"),
            price=price,
            supplier=product.get("supplier"),
            supplierId=product.get("supplierId"),
            reviewRating=product.get("reviewRating"),
            feedbacks=product.get("feedbacks"),
            sizes=[size.get("name") for size in sizes_data],
            stock=stock,
        )


async def get_basket(
        client: httpx.AsyncClient, nm_id: int, semaphore: asyncio.Semaphore
) -> tuple[str | None, dict | None]:
    async with semaphore:
        vol = nm_id // 100000
        part = nm_id // 1000
        card_path = f"/vol{vol}/part{part}/{nm_id}/info/ru/card.json"

        if vol in BASKET_CACHE:
            basket = BASKET_CACHE[vol]
            url = f"https://basket-{basket}.wbbasket.ru{card_path}"
            data = await safe_get_json(client, url)
            if data:
                return f"https://basket-{basket}.wbbasket.ru/vol{vol}/part{part}/{nm_id}"
            BASKET_CACHE.pop(vol, None)

        for basket in range(1, MAX_BASKET):
            base_url = f"https://basket-{basket}.wbbasket.ru"
            full_url = f"{base_url}{card_path}"
            data = await safe_get_json(client, full_url)
            if data:
                BASKET_CACHE[vol] = basket
                return f"{base_url}/vol{vol}/part{part}/{nm_id}", data

        logger.warning(f"Не найден basket для {nm_id}")
        return None


async def get_basket_data(
        client: httpx.AsyncClient,
        nm_id: int,
        semaphore: asyncio.Semaphore
) -> tuple[str | None, list[str], dict]:
    basket_url, data = await get_basket(client, nm_id, semaphore)
    if not basket_base or not data:
        return None, [], {}

    description = data.get("description")
    characteristics = {
        opt.get("name"): opt.get("value")
        for opt in data.get("options", [])
        if opt.get("name") and opt.get("value")
    }
    photo_count = data.get("media", {}).get("photo_count", 0)
    images = [
        f"{basket_base}/images/c516x688/{i}.webp"
        for i in range(1, photo_count + 1)
    ]
    return description, images, characteristics


async def build_product(
        client: httpx.AsyncClient,
        nm_id: str,
        semaphore: asyncio.Semaphore
) -> Product:
    async with semaphore:
        detail_data = await get_detail_data(client, nm_id, semaphore)
        if not detail_data:
            logger.warning(f"Не найдена карточка {nm_id}")
            return None

        # собираем характеристики, изображения, описание
        description, images, characteristics = await get_basket_data(
            client,
            detail_data.id,
            semaphore
        )

        return Product(
            url=f"https://www.wildberries.ru/catalog/{detail_data.id}/detail.aspx",
            article=detail_data.id,
            name=detail_data.name,
            price=detail_data.price,
            description=description,
            images=images,
            characteristics=characteristics,
            seller_name=detail_data.supplier,
            seller_url=f"https://www.wildberries.ru/seller/{detail_data.supplierId}",
            sizes=detail_data.sizes,
            stock=detail_data.stock,
            rating=detail_data.reviewRating,
            feedbacks=detail_data.feedbacks,
        )


async def main():
    semaphore = asyncio.Semaphore(15)
    async with httpx.AsyncClient(
            headers=HEADERS,
            timeout=20,
            http2=True,
            limits=httpx.Limits(
                max_connections=50,
                max_keepalive_connections=20
            )
    ) as client:
        # получение товаров на странице
        page_data = await safe_get_json(
            client,
            url=SEARCH_URL,
            params=PARAMS_TEMPLATE,

        )
        # получение артикулов товаров
        data = page_data.get("products") or page_data.get("data", {}).get(
            "products")
        product_ids = [
            str(product.get('id')) for product in data
        ]
        tasks = [
            build_product(client, product_id, semaphore)
            for product_id in product_ids
        ]
        results = await asyncio.gather(*tasks)
        products = [p for p in results if p]
        logger.info(f"Собрано товаров: {len(products)}")
        logger.info(f"Товары: {[p for p in results if p]}")
        return products


if __name__ == "__main__":
    products = asyncio.run(main())
