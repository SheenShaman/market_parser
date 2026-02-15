import logging
import asyncio
import httpx

from constants import (
    DETAIL_URL,
    FAILURE_STATUS,
    HEADERS,
    SEARCH_URL,
    PARAMS_TEMPLATE,
    MAX_BASKET,
    MIN_BASKET,
)
from models import Product, DetailProduct
from logger import setup_logging
from export_to_excel import export_to_excel

setup_logging()
logger = logging.getLogger(__name__)

BASKET_CACHE: dict[int, int] = {}


def get_card_path(nm_id: int) -> tuple[int, int, str]:
    vol = nm_id // 100000
    part = nm_id // 1000
    card_path = f"/vol{vol}/part{part}/{nm_id}/info/ru/card.json"
    return vol, part, card_path


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
                wait = min(2**attempt, 8)
                await asyncio.sleep(wait)
                continue

            response.raise_for_status()
            return response.json()

        except (httpx.RequestError, httpx.HTTPStatusError):
            wait = min(2**attempt, 8)
            await asyncio.sleep(wait)
    return None


async def get_detail_data(
    client: httpx.AsyncClient, nm_id: str
) -> DetailProduct | None:
    """
    Возвращает данные товара по detail_url
    """
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
    stock = sum(s.get("qty", 0) for size in sizes_data for s in size.get("stocks", []))
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
    client: httpx.AsyncClient,
    nm_id: int,
) -> tuple[str | None, dict | None]:
    """
    Поиск basket
    """
    vol, part, card_path = get_card_path(nm_id)

    if vol in BASKET_CACHE:
        basket = BASKET_CACHE[vol]
        url = f"https://basket-{basket}.wbbasket.ru{card_path}"
        data = await safe_get_json(client, url)
        if data:
            return f"https://basket-{basket}.wbbasket.ru/vol{vol}/part{part}/{nm_id}"
        BASKET_CACHE.pop(vol, None)

    for basket in range(MIN_BASKET, MAX_BASKET):
        base_url = f"https://basket-{basket}.wbbasket.ru"
        full_url = f"{base_url}{card_path}"
        data = await safe_get_json(client, full_url)
        if data:
            BASKET_CACHE[vol] = basket
            return f"{base_url}/vol{vol}/part{part}/{nm_id}", data

    return None, None


async def get_basket_data(
    client: httpx.AsyncClient,
    nm_id: int,
) -> tuple[str | None, list[str], dict]:
    """
    Находим описание, изображения, характеристики по basket
    """
    basket_url, data = await get_basket(client, nm_id)
    if not basket_url or not data:
        return None, [], {}

    description = data.get("description")
    characteristics = {
        opt.get("name"): opt.get("value")
        for opt in data.get("options", [])
        if opt.get("name") and opt.get("value")
    }
    photo_count = data.get("media", {}).get("photo_count", 0)
    images = [
        f"{basket_url}/images/c516x688/{i}.webp" for i in range(1, photo_count + 1)
    ]
    return description, images, characteristics


async def build_product(
    client: httpx.AsyncClient, nm_id: str, semaphore: asyncio.Semaphore
) -> Product:
    """
    Сборка модели товара
    """
    async with semaphore:
        detail_data = await get_detail_data(client, nm_id)
        if not detail_data:
            logger.warning(f"Не найдена карточка {nm_id}")
            return None

        # собираем характеристики, изображения, описание
        description, images, characteristics = await get_basket_data(
            client, detail_data.id
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
    semaphore = asyncio.Semaphore(60)
    async with httpx.AsyncClient(
        headers=HEADERS,
        timeout=15,
        http2=True,
        limits=httpx.Limits(max_connections=120, max_keepalive_connections=60),
    ) as client:
        # получение товаров на странице
        page_data = await safe_get_json(
            client,
            url=SEARCH_URL,
            params=PARAMS_TEMPLATE,
        )
        # получение артикулов товаров
        data = page_data.get("products") or page_data.get("data", {}).get("products")
        product_ids = [str(product.get("id")) for product in data]
        tasks = [
            build_product(client, product_id, semaphore) for product_id in product_ids
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        products = [p for p in results if isinstance(p, Product)]
        export_to_excel(products)


if __name__ == "__main__":
    asyncio.run(main())
