import sqlite3
from contextlib import closing
from pathlib import Path
from negocio.modelos import Product, Client, Order, OrderLine

SCHEMA = '''
CREATE TABLE IF NOT EXISTS products (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, price_cents INTEGER NOT NULL, stock INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS clients (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL UNIQUE,
 level TEXT NOT NULL, points INTEGER NOT NULL, accumulated_cents INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS orders (
 id TEXT PRIMARY KEY, client_id TEXT NOT NULL REFERENCES clients(id), state TEXT NOT NULL,
 created_at TEXT NOT NULL, level TEXT NOT NULL, discount_percent INTEGER NOT NULL,
 subtotal_cents INTEGER NOT NULL, level_discount_cents INTEGER NOT NULL,
 redeemed_points INTEGER NOT NULL, points_discount_cents INTEGER NOT NULL,
 total_cents INTEGER NOT NULL, points_to_earn INTEGER NOT NULL,
 mode TEXT NOT NULL, table_label TEXT NOT NULL, request_key TEXT NOT NULL,
 completed_at TEXT NOT NULL, UNIQUE(client_id, request_key));
CREATE TABLE IF NOT EXISTS order_lines (
 order_id TEXT NOT NULL REFERENCES orders(id), product_id TEXT NOT NULL REFERENCES products(id),
 name TEXT NOT NULL, quantity INTEGER NOT NULL, unit_price_cents INTEGER NOT NULL,
 subtotal_cents INTEGER NOT NULL, PRIMARY KEY(order_id, product_id));
'''

def initialize(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as connection:
        connection.executescript(SCHEMA)

class SQLiteRepository:
    def __init__(self, connection):
        self.connection = connection

    def products(self):
        return [Product(**dict(r)) for r in self.connection.execute('SELECT * FROM products ORDER BY name')]

    def product(self, key):
        row = self.connection.execute('SELECT * FROM products WHERE id=?',(key,)).fetchone()
        return Product(**dict(row)) if row else None

    def save_product(self, p):
        self.connection.execute('INSERT INTO products VALUES (?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name, price_cents=excluded.price_cents, stock=excluded.stock', (p.id,p.name,p.price_cents,p.stock))

    def clients(self):
        return [Client(**dict(r)) for r in self.connection.execute('SELECT * FROM clients ORDER BY name')]

    def client(self, key):
        row = self.connection.execute('SELECT * FROM clients WHERE id=?',(key,)).fetchone()
        return Client(**dict(row)) if row else None

    def client_by_email(self, email):
        row = self.connection.execute('SELECT * FROM clients WHERE email=?',(email,)).fetchone()
        return Client(**dict(row)) if row else None

    def save_client(self, c):
        self.connection.execute('INSERT INTO clients VALUES (?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,email=excluded.email,level=excluded.level,points=excluded.points,accumulated_cents=excluded.accumulated_cents', (c.id,c.name,c.email,c.level,c.points,c.accumulated_cents))

    def _order(self, row):
        if row is None:
            return None
        fields = dict(row)
        fields['table'] = fields.pop('table_label')
        fields['items'] = [OrderLine(**dict(r)) for r in self.connection.execute('SELECT product_id,name,quantity,unit_price_cents,subtotal_cents FROM order_lines WHERE order_id=? ORDER BY product_id',(fields['id'],))]
        return Order(**fields)

    def orders(self):
        return [self._order(r) for r in self.connection.execute('SELECT * FROM orders ORDER BY created_at DESC, rowid DESC').fetchall()]

    def order(self, key):
        return self._order(self.connection.execute('SELECT * FROM orders WHERE id=?',(key,)).fetchone())

    def order_by_request(self, client_id, request_key):
        return self._order(self.connection.execute('SELECT * FROM orders WHERE client_id=? AND request_key=?',(client_id,request_key)).fetchone())

    def save_order(self, o):
        self.connection.execute('''INSERT INTO orders VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
          ON CONFLICT(id) DO UPDATE SET state=excluded.state,completed_at=excluded.completed_at''',
          (o.id,o.client_id,o.state,o.created_at,o.level,o.discount_percent,o.subtotal_cents,
           o.level_discount_cents,o.redeemed_points,o.points_discount_cents,o.total_cents,
           o.points_to_earn,o.mode,o.table,o.request_key,o.completed_at))
        self.connection.executemany('INSERT OR IGNORE INTO order_lines VALUES (?,?,?,?,?,?)',
            [(o.id,l.product_id,l.name,l.quantity,l.unit_price_cents,l.subtotal_cents) for l in o.items])

class SQLiteUnitOfWork:
    """One connection per request. Serializes writers before reads to prevent races."""
    def __init__(self, path):
        self.path = path

    def __enter__(self):
        self.connection = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute('PRAGMA foreign_keys=ON')
        try:
            self.connection.execute('BEGIN IMMEDIATE')
        except Exception:
            self.connection.close()
            raise
        self.repo = SQLiteRepository(self.connection)
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            self.connection.execute('ROLLBACK' if exc_type else 'COMMIT')
        finally:
            self.connection.close()
