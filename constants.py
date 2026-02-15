QUERY = "пальто из натуральной шерсти"

SEARCH_URL = "https://search.wb.ru/exactmatch/ru/common/v18/search"
DETAIL_URL = "https://card.wb.ru/cards/v4/detail"

HEADERS = {
    "accept": "*/*",
    "accept-language": "ru-RU,ru;q=0.9,en;q=0.8",
    "referer": "https://www.wildberries.ru/",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36",
    "x-requested-with": "XMLHttpRequest",
    "x-spa-version": "13.19.4",
    "x-userid": "0",
}

PARAMS_TEMPLATE = {
    "ab_testing": "false",
    "appType": "1",
    "curr": "rub",
    "dest": "-1257786",
    "f14177451": "15000203",
    "frating": "1",
    "hide_vflags": "4294967296",
    "inheritFilters": "false",
    "lang": "ru",
    "page": "1",
    "priceU": "73400;1000000",
    "query": QUERY,
    "resultset": "catalog",
    "sort": "popular",
    "spp": "30",
    "suppressSpellcheck": "false",
}

FAILURE_STATUS = (429, 500, 502, 503, 504)
MAX_BASKET = 30
MIN_BASKET = 20
