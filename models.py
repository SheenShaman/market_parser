from pydantic import BaseModel


class Product(BaseModel):
    url: str
    article: int
    name: str
    price: float
    description: str | None = None
    images: list[str]
    characteristics: dict
    seller_name: str
    seller_url: str
    sizes: list[str]
    stock: int
    rating: float
    feedbacks: int


class DetailProduct(BaseModel):
    id: int
    name: str
    price: float
    supplier: str
    supplierId: int
    reviewRating: float
    feedbacks: int
    sizes: list[str]
    stock: int
