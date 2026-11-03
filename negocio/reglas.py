"""Pure policies. Monetary amounts are integer cents, never binary floats."""
from .modelos import BusinessError, Quote, OrderLine

DISCOUNTS = {'Junior': 5, 'Mid': 10, 'Senior': 15}
STATES = ('Pendiente de pago', 'En Preparación', 'Listo', 'Entregado')
POINT_VALUE = 20_000  # cents = $200
POINT_SPEND = 2_000_000  # cents = $20,000

def integer(value, label, minimum=0, maximum=1_000_000_000):
    if type(value) is not int or not minimum <= value <= maximum:
        raise BusinessError(f'{label}: debe ser un entero entre {minimum} y {maximum}.')
    return value

def level_for(accumulated_cents):
    if accumulated_cents >= 150_000_000:
        return 'Senior'
    if accumulated_cents >= 50_000_000:
        return 'Mid'
    return 'Junior'

def calculate(lines: list[OrderLine], level: str, balance: int, redeem: int) -> Quote:
    integer(redeem, 'DevPoints a redimir')
    if redeem > balance:
        raise BusinessError('No tienes suficientes DevPoints para esta redención.')
    subtotal = sum(line.subtotal_cents for line in lines)
    percent = DISCOUNTS[level]
    discount = (subtotal * percent + 50) // 100  # half-up, to one cent
    points_discount = redeem * POINT_VALUE
    if points_discount > subtotal - discount:
        raise BusinessError('La redención excede el valor del pedido después del descuento de nivel.')
    total = subtotal - discount - points_discount
    return Quote(lines, level, percent, subtotal, discount, redeem, points_discount,
                 total, total // POINT_SPEND)

def next_state(state):
    pos = STATES.index(state)
    return STATES[pos + 1] if pos + 1 < len(STATES) else ''
