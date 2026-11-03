import ast
import json
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from negocio.modelos import BusinessError, ItemRequest, OrderRequest, OrderLine
from negocio.reglas import calculate, level_for, STATES
from negocio.servicio import CafeService
from persistencia.sqlite import SQLiteUnitOfWork, initialize
from presentation.http import create_server

class RulesTest(unittest.TestCase):
    def test_discounts(self):
        for level,total in [('Junior',9_500_000),('Mid',9_000_000),('Senior',8_500_000)]:
            with self.subTest(level=level):
                q=calculate([OrderLine('p','Coffee',1,10_000_000,10_000_000)],level,0,0)
                self.assertEqual(q.total_cents,total)

    def test_exact_promotion_boundaries(self):
        for amount,level in [(0,'Junior'),(49_999_999,'Junior'),(50_000_000,'Mid'),(149_999_999,'Mid'),(150_000_000,'Senior')]:
            self.assertEqual(level_for(amount),level)

    def test_points_floor_per_order(self):
        for subtotal,points in [(2_000_000,0),(4_000_000,1),(6_000_000,2)]:
            q=calculate([OrderLine('p','P',1,subtotal,subtotal)],'Junior',0,0)
            self.assertEqual(q.points_to_earn,points)

    def test_points_after_level_discount(self):
        q=calculate([OrderLine('p','P',1,10_000_000,10_000_000)],'Junior',10,10)
        self.assertEqual(q.total_cents,9_300_000)
        self.assertEqual(q.points_discount_cents,200_000)

    def test_no_negative_total(self):
        with self.assertRaises(BusinessError):
            calculate([OrderLine('p','P',1,10_000,10_000)],'Junior',5,1)

    def test_insufficient_points(self):
        with self.assertRaises(BusinessError):
            calculate([OrderLine('p','P',1,1_000_000,1_000_000)],'Junior',0,1)

    def test_half_up_rounding(self):
        q=calculate([OrderLine('p','P',1,110,110)],'Junior',0,0)
        self.assertEqual(q.level_discount_cents,6)

class ApplicationTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.path=str(Path(self.temp.name)/'test.sqlite3')
        initialize(self.path)
        self.service=CafeService(lambda:SQLiteUnitOfWork(self.path))
        self.client=self.service.register_client('Ana','ana@example.test')
        self.product=self.service.save_product('Espresso',4_000_000,10)

    def tearDown(self):
        self.temp.cleanup()

    def request(self,**kwargs):
        data=dict(client_id=self.client.id,items=[ItemRequest(self.product.id,1)],request_key='request-1')
        data.update(kwargs)
        return OrderRequest(**data)

    def complete(self,order):
        for state in STATES[1:]:
            order=self.service.change_state(order.id,state)
        return order

    def test_client_defaults(self):
        self.assertEqual((self.client.level,self.client.points,self.client.accumulated_cents),('Junior',0,0))

    def test_duplicate_email(self):
        with self.assertRaises(BusinessError):self.service.register_client('Otro','ANA@example.test')

    def test_email_validation(self):
        with self.assertRaises(BusinessError):self.service.register_client('Otro','invalid')

    def test_stock_exceeded(self):
        with self.assertRaises(BusinessError):self.service.create_order(self.request(items=[ItemRequest(self.product.id,11)]))
        self.assertEqual(self.service.snapshot().products[0].stock,10)
        self.assertEqual(len(self.service.snapshot().orders),0)

    def test_repeated_lines_combined_before_stock_validation(self):
        with self.assertRaises(BusinessError):self.service.create_order(self.request(items=[ItemRequest(self.product.id,6),ItemRequest(self.product.id,6)]))

    def test_reserve_stock_on_registration(self):
        order=self.service.create_order(self.request())
        self.assertEqual(order.state,'Pendiente de pago')
        self.assertEqual(self.service.snapshot().products[0].stock,9)
        self.assertEqual(self.service.snapshot().clients[0].points,0)

    def test_pending_blocks_second_order(self):
        self.service.create_order(self.request())
        with self.assertRaises(BusinessError):self.service.create_order(self.request(request_key='request-2'))

    def test_paid_order_allows_new_order(self):
        order=self.service.create_order(self.request())
        self.service.change_state(order.id,'En Preparación')
        self.service.create_order(self.request(request_key='request-2'))
        self.assertEqual(len(self.service.snapshot().orders),2)

    def test_no_skipped_states(self):
        order=self.service.create_order(self.request())
        with self.assertRaises(BusinessError):self.service.change_state(order.id,'Entregado')

    def test_no_backward_states(self):
        order=self.complete(self.service.create_order(self.request()))
        with self.assertRaises(BusinessError):self.service.change_state(order.id,'Listo')

    def test_completion_earns_once(self):
        order=self.complete(self.service.create_order(self.request()))
        self.service.change_state(order.id,'Entregado')
        client=self.service.snapshot().clients[0]
        self.assertEqual(client.accumulated_cents,3_800_000)
        self.assertEqual(client.points,1)

    def test_idempotent_registration(self):
        first=self.service.create_order(self.request())
        second=self.service.create_order(self.request())
        self.assertEqual(first.id,second.id)
        self.assertEqual(self.service.snapshot().products[0].stock,9)

    def test_request_key_cannot_change_order(self):
        self.service.create_order(self.request())
        with self.assertRaises(BusinessError):self.service.create_order(self.request(items=[ItemRequest(self.product.id,2)]))

    def test_points_only_redeem_on_following_order(self):
        first=self.service.create_order(self.request())
        self.assertEqual(self.service.snapshot().clients[0].points,0)
        self.complete(first)
        second=self.service.create_order(self.request(request_key='second',redeem_points=1))
        self.assertEqual(second.total_cents,3_780_000)
        self.assertEqual(self.service.snapshot().clients[0].points,0)

    def test_mid_promotion_affects_next_order_only(self):
        with SQLiteUnitOfWork(self.path) as u:
            client=u.repo.client(self.client.id);client.accumulated_cents=46_200_000;u.repo.save_client(client)
        first=self.complete(self.service.create_order(self.request()))
        self.assertEqual(first.discount_percent,5)
        self.assertEqual(self.service.snapshot().clients[0].level,'Mid')
        second=self.service.create_order(self.request(request_key='second'))
        self.assertEqual(second.discount_percent,10)

    def test_senior_promotion(self):
        with SQLiteUnitOfWork(self.path) as u:
            client=u.repo.client(self.client.id);client.accumulated_cents=146_400_000;client.level='Mid';u.repo.save_client(client)
        first=self.complete(self.service.create_order(self.request()))
        self.assertEqual(first.total_cents,3_600_000)
        self.assertEqual(self.service.snapshot().clients[0].level,'Senior')

    def test_price_snapshot(self):
        order=self.service.create_order(self.request())
        self.service.save_product('Nuevo nombre',5_000_000,9,self.product.id)
        saved=self.service.snapshot().orders[0]
        self.assertEqual(saved.total_cents,order.total_cents)
        self.assertEqual(saved.items[0].name,'Espresso')

    def test_quote_has_no_side_effects(self):
        self.service.quote(self.request())
        self.assertEqual(len(self.service.snapshot().orders),0)
        self.assertEqual(self.service.snapshot().products[0].stock,10)

    def test_invalid_quantities(self):
        for value in [0,-1,1.5,True,'1']:
            with self.subTest(value=value),self.assertRaises(BusinessError):
                self.service.quote(self.request(items=[ItemRequest(self.product.id,value)]))

    def test_table_required(self):
        with self.assertRaises(BusinessError):self.service.quote(self.request(mode='Mesa'))

    def test_takeaway_and_table(self):
        self.assertGreater(self.service.quote(self.request(mode='Mesa',table='04')).total_cents,0)
        self.assertGreater(self.service.quote(self.request(mode='Para llevar')).total_cents,0)

    def test_empty_order(self):
        with self.assertRaises(BusinessError):self.service.quote(self.request(items=[]))

    def test_unknown_product(self):
        with self.assertRaises(BusinessError):self.service.quote(self.request(items=[ItemRequest('missing',1)]))

    def test_transaction_rollback(self):
        with self.assertRaises(RuntimeError):
            with SQLiteUnitOfWork(self.path) as u:
                product=u.repo.product(self.product.id);product.stock=2;u.repo.save_product(product)
                raise RuntimeError('Failure before commit')
        self.assertEqual(self.service.snapshot().products[0].stock,10)

    def test_concurrent_last_item(self):
        self.service.save_product('Espresso',4_000_000,1,self.product.id)
        other=self.service.register_client('Luis','luis@example.test')
        barrier=threading.Barrier(2)
        def buy(client):
            barrier.wait()
            try:return self.service.create_order(self.request(client_id=client)).id
            except BusinessError:return None
        with ThreadPoolExecutor(2) as pool:results=list(pool.map(buy,[self.client.id,other.id]))
        self.assertEqual(sum(x is not None for x in results),1)
        self.assertEqual(self.service.snapshot().products[0].stock,0)

    def test_concurrent_pending_same_client(self):
        barrier=threading.Barrier(2)
        def buy(key):
            barrier.wait()
            try:return self.service.create_order(self.request(request_key=key)).id
            except BusinessError:return None
        with ThreadPoolExecutor(2) as pool:results=list(pool.map(buy,['one','two']))
        self.assertEqual(sum(x is not None for x in results),1)

    def test_concurrent_completion(self):
        order=self.service.create_order(self.request())
        self.service.change_state(order.id,'En Preparación');self.service.change_state(order.id,'Listo')
        with ThreadPoolExecutor(2) as pool:list(pool.map(lambda _:self.service.change_state(order.id,'Entregado'),range(2)))
        self.assertEqual(self.service.snapshot().clients[0].points,1)

class HttpTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();path=str(Path(self.temp.name)/'test.db');initialize(path)
        self.service=CafeService(lambda:SQLiteUnitOfWork(path));self.service.seed_menu()
        self.server=create_server(self.service,0)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.base=f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.temp.cleanup()

    def call(self,path,body=None):
        req=Request(self.base+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json'})
        with urlopen(req) as response:return json.load(response)

    def test_full_http_flow_ignores_forged_total(self):
        client=self.call('/api/clients',{'name':'Eva','email':'eva@example.test'})
        body={'client_id':client['id'],'items':[{'product_id':'combo','quantity':2}],'request_key':'http-1','total_cents':1,'level':'Senior'}
        order=self.call('/api/orders',body)
        self.assertEqual(order['total_cents'],4_560_000)
        for state in STATES[1:]:self.call('/api/orders/'+order['id']+'/state',{'state':state})
        snapshot=self.call('/api/bootstrap')
        self.assertEqual(snapshot['clients'][0]['points'],2)

    def test_assets_and_no_directory_traversal(self):
        for path in ['/','/app.js','/style.css']:
            with urlopen(self.base+path) as response:self.assertEqual(response.status,200)
        with self.assertRaises(HTTPError) as error:urlopen(self.base+'/../run.py')
        self.assertEqual(error.exception.code,404)

    def test_wrong_origin_rejected(self):
        req=Request(self.base+'/api/clients',data=b'{}',headers={'Content-Type':'application/json','Origin':'https://other.example'})
        with self.assertRaises(HTTPError) as error:urlopen(req)
        self.assertEqual(error.exception.code,403)

    def test_malformed_json(self):
        req=Request(self.base+'/api/clients',data=b'{broken',headers={'Content-Type':'application/json'})
        with self.assertRaises(HTTPError) as error:urlopen(req)
        self.assertEqual(error.exception.code,400)

class IsolationTest(unittest.TestCase):
    def test_layer_import_boundaries(self):
        root=Path(__file__).resolve().parents[1]
        forbidden={'negocio':{'presentation','persistencia','sqlite3','json','http'},
                   'presentation':{'persistencia','sqlite3'},
                   'persistencia':{'presentation','negocio.servicio','negocio.reglas'}}
        for layer,banned in forbidden.items():
            for file in (root/layer).rglob('*.py'):
                tree=ast.parse(file.read_text(encoding='utf-8'))
                for node in ast.walk(tree):
                    modules=[a.name for a in node.names] if isinstance(node,ast.Import) else [node.module or ''] if isinstance(node,ast.ImportFrom) else []
                    for module in modules:
                        self.assertFalse(any(module==b or module.startswith(b+'.') for b in banned),f'{file}: prohibited import {module}')

if __name__=='__main__':unittest.main()
