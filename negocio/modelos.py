from dataclasses import dataclass

@dataclass
class Product:
    id: str
    name: str
    price_cents: int
    stock: int

@dataclass
class Client:
    id: str
    name: str
    email: str
    level: str = 'Junior'
    points: int = 0
    accumulated_cents: int = 0

@dataclass
class ItemRequest:
    product_id: str
    quantity: int

@dataclass
class OrderRequest:
    client_id: str
    items: list[ItemRequest]
    redeem_points: int = 0
    mode: str = 'Para llevar'
    table: str = ''
    request_key: str = ''

@dataclass
class OrderLine:
    product_id: str
    name: str
    quantity: int
    unit_price_cents: int
    subtotal_cents: int

@dataclass
class Quote:
    items: list[OrderLine]
    level: str
    discount_percent: int
    subtotal_cents: int
    level_discount_cents: int
    redeemed_points: int
    points_discount_cents: int
    total_cents: int
    points_to_earn: int

@dataclass
class Order:
    id: str
    client_id: str
    items: list[OrderLine]
    state: str
    created_at: str
    level: str
    discount_percent: int
    subtotal_cents: int
    level_discount_cents: int
    redeemed_points: int
    points_discount_cents: int
    total_cents: int
    points_to_earn: int
    mode: str
    table: str
    request_key: str
    completed_at: str = ''
    next_state: str = ''

@dataclass
class Snapshot:
    products: list[Product]
    clients: list[Client]
    orders: list[Order]

class BusinessError(Exception):
    """A domain error that presentation can translate to an HTTP response."""
