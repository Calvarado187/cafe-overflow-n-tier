"""Use cases: the sole owner of discounts, stock decisions and loyalty."""
import re
from datetime import datetime, timezone
from uuid import uuid4
from typing import Callable
from .modelos import Product, Client, Order, OrderLine, OrderRequest, Snapshot, BusinessError
from .puertos import UnitOfWork
from .reglas import integer, calculate, level_for, next_state, STATES

def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')

def text(value, label, limit=100):
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > limit:
        raise BusinessError(f'{label}: ingresa texto entre 1 y {limit} caracteres.')
    return value.strip()

class CafeService:
    def __init__(self, uow_factory: Callable[[], UnitOfWork]):
        self.uow_factory = uow_factory

    def snapshot(self):
        with self.uow_factory() as u:
            orders = u.repo.orders()
            for order in orders:
                order.next_state = next_state(order.state)
            return Snapshot(u.repo.products(), u.repo.clients(), orders)

    def register_client(self, name, email):
        name = text(name, 'Nombre')
        email = text(email, 'Correo', 254).lower()
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email):
            raise BusinessError('El correo electrónico no tiene un formato válido.')
        with self.uow_factory() as u:
            if u.repo.client_by_email(email):
                raise BusinessError('Ya existe un cliente con ese correo.')
            client = Client(str(uuid4()), name, email)
            u.repo.save_client(client)
            return client

    def save_product(self, name, price_cents, stock, product_id=None):
        name = text(name, 'Producto')
        integer(price_cents, 'Precio en centavos', 1, 100_000_000)
        integer(stock, 'Stock', 0, 1_000_000)
        with self.uow_factory() as u:
            if product_id and not u.repo.product(product_id):
                raise BusinessError('El producto no existe.')
            product = Product(product_id or str(uuid4()), name, price_cents, stock)
            u.repo.save_product(product)
            return product

    def seed_menu(self):
        with self.uow_factory() as u:
            if not u.repo.products():
                for pid, name, price, stock in [
                    ('espresso','Espresso StackTrace',800_000,30),
                    ('combo','Combo BugHunter',2_400_000,25),
                    ('te','Té Async/Await',700_000,35),
                    ('latte','Latte Code Review',1_200_000,30),
                    ('brownie','Brownie Dark Mode',900_000,20),
                    ('sandwich','Sándwich Full Stack',1_800_000,20)]:
                    u.repo.save_product(Product(pid,name,price,stock))

    def _quote(self, repo, request):
        client = repo.client(request.client_id)
        if not client:
            raise BusinessError('Selecciona un cliente registrado.')
        if request.mode not in ('Mesa', 'Para llevar'):
            raise BusinessError('Selecciona Mesa o Para llevar.')
        if request.mode == 'Mesa':
            text(request.table, 'Número o nombre de mesa', 20)
        if any(o.client_id == client.id and o.state == STATES[0] for o in repo.orders()):
            raise BusinessError('Tienes un pedido pendiente de pago. Págalo antes de crear otro.')
        if not request.items or len(request.items) > 100:
            raise BusinessError('El pedido debe contener entre 1 y 100 líneas.')
        quantities = {}
        for item in request.items:
            text(item.product_id, 'Identificador de producto')
            integer(item.quantity, 'Cantidad', 1, 10_000)
            quantities[item.product_id] = quantities.get(item.product_id, 0) + item.quantity
        lines = []
        for key, qty in sorted(quantities.items()):
            product = repo.product(key)
            if not product:
                raise BusinessError('Uno de los productos ya no existe.')
            if qty > product.stock:
                raise BusinessError(f'Stock insuficiente para {product.name}: disponibles {product.stock}.')
            lines.append(OrderLine(key, product.name, qty, product.price_cents, qty * product.price_cents))
        return client, calculate(lines, client.level, client.points, request.redeem_points)

    def quote(self, request: OrderRequest):
        with self.uow_factory() as u:
            return self._quote(u.repo, request)[1]

    def create_order(self, request: OrderRequest):
        text(request.request_key, 'Clave de solicitud', 100)
        with self.uow_factory() as u:
            previous = u.repo.order_by_request(request.client_id, request.request_key)
            if previous:
                quantities = {}
                for line in request.items:
                    integer(line.quantity, 'Cantidad', 1, 10_000)
                    quantities[line.product_id] = quantities.get(line.product_id, 0) + line.quantity
                expected = {line.product_id: line.quantity for line in previous.items}
                if (quantities != expected or request.redeem_points != previous.redeemed_points
                        or request.mode != previous.mode or request.table.strip() != previous.table):
                    raise BusinessError('La clave de solicitud ya pertenece a otro pedido.')
                previous.next_state = next_state(previous.state)
                return previous
            client, quote = self._quote(u.repo, request)
            # Decisions live here; the repository only persists their result.
            for line in quote.items:
                product = u.repo.product(line.product_id)
                product.stock -= line.quantity
                u.repo.save_product(product)
            client.points -= quote.redeemed_points
            u.repo.save_client(client)
            order = Order(str(uuid4()), client.id, quote.items, STATES[0], now(), quote.level,
                          quote.discount_percent, quote.subtotal_cents, quote.level_discount_cents,
                          quote.redeemed_points, quote.points_discount_cents, quote.total_cents,
                          quote.points_to_earn, request.mode, request.table.strip(), request.request_key)
            u.repo.save_order(order)
            order.next_state = next_state(order.state)
            return order

    def change_state(self, order_id, target):
        with self.uow_factory() as u:
            order = u.repo.order(order_id)
            if not order:
                raise BusinessError('El pedido no existe.')
            if target == order.state:  # retry: no duplicate points or accumulated spend
                order.next_state = next_state(order.state)
                return order
            if target != next_state(order.state) or not target:
                raise BusinessError('Transición inválida: debes respetar el orden de los estados.')
            order.state = target
            if target == STATES[-1]:
                client = u.repo.client(order.client_id)
                client.accumulated_cents += order.total_cents
                client.points += order.points_to_earn
                client.level = level_for(client.accumulated_cents)
                order.completed_at = now()
                u.repo.save_client(client)
            u.repo.save_order(order)
            order.next_state = next_state(order.state)
            return order
