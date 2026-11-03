import json
import logging
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from negocio.modelos import ItemRequest, OrderRequest, BusinessError

STATIC = Path(__file__).parent / 'static'
ASSETS = {'/':('index.html','text/html; charset=utf-8'),
          '/app.js':('app.js','text/javascript; charset=utf-8'),
          '/style.css':('style.css','text/css; charset=utf-8')}

def order_request(body):
    items = body.get('items', [])
    if not isinstance(items, list) or any(not isinstance(i, dict) for i in items):
        raise ValueError('La lista de productos no es válida.')
    return OrderRequest(body.get('client_id',''),
        [ItemRequest(i.get('product_id',''),i.get('quantity')) for i in items],
        body.get('redeem_points',0),body.get('mode','Para llevar'),
        body.get('table',''),body.get('request_key',''))

def create_server(service, port=8080):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass

        def send(self, status, payload, content_type='application/json; charset=utf-8'):
            data = payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type',content_type)
            self.send_header('Content-Length',str(len(data)))
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; object-src 'none'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(data)

        def valid_host(self):
            return self.headers.get('Host','') in (f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}')

        def do_GET(self):
            if not self.valid_host():
                return self.send(403,{'error':'Host no permitido.'})
            path = urlsplit(self.path).path
            if path in ASSETS:
                filename, kind = ASSETS[path]
                return self.send(200,(STATIC/filename).read_bytes(),kind)
            if path == '/api/bootstrap':
                try:
                    return self.send(200,asdict(service.snapshot()))
                except Exception:
                    logging.exception('Snapshot failed')
                    return self.send(500,{'error':'No se pudo consultar la información.'})
            self.send(404,{'error':'Ruta no encontrada.'})

        def do_POST(self):
            if not self.valid_host():
                return self.send(403,{'error':'Host no permitido.'})
            allowed_origin = {f'http://127.0.0.1:{self.server.server_port}',f'http://localhost:{self.server.server_port}'}
            if self.headers.get('Origin') and self.headers['Origin'] not in allowed_origin:
                return self.send(403,{'error':'Origen no permitido.'})
            if self.headers.get('Content-Type','').split(';')[0] != 'application/json':
                return self.send(415,{'error':'Se requiere application/json.'})
            try:
                length = int(self.headers.get('Content-Length','0'))
                if not 0 < length <= 65536:
                    return self.send(413,{'error':'Tamaño de solicitud no permitido.'})
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict):
                    raise ValueError('El cuerpo debe ser un objeto.')
                path = urlsplit(self.path).path
                if path == '/api/clients':
                    result = service.register_client(body.get('name'),body.get('email'))
                elif path == '/api/products':
                    result = service.save_product(body.get('name'),body.get('price_cents'),body.get('stock'))
                elif path.startswith('/api/products/'):
                    result = service.save_product(body.get('name'),body.get('price_cents'),body.get('stock'),path.split('/')[-1])
                elif path == '/api/quote':
                    result = service.quote(order_request(body))
                elif path == '/api/orders':
                    result = service.create_order(order_request(body))
                elif path.startswith('/api/orders/') and path.endswith('/state'):
                    result = service.change_state(path.split('/')[-2],body.get('state'))
                else:
                    return self.send(404,{'error':'Ruta no encontrada.'})
                self.send(200,asdict(result))
            except BusinessError as exc:
                self.send(409,{'error':str(exc)})
            except (ValueError, TypeError, AttributeError, UnicodeDecodeError):
                self.send(400,{'error':'Datos inválidos. Revisa el formulario.'})
            except Exception:
                logging.exception('Request failed')
                self.send(500,{'error':'No se pudo completar la operación. Intenta de nuevo.'})

    return ThreadingHTTPServer(('127.0.0.1',port),Handler)
