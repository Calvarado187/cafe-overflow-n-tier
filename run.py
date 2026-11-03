"""Composition root: connects the three layers; Python 3.10+ only."""
import argparse
from pathlib import Path
from negocio.servicio import CafeService
from persistencia.sqlite import SQLiteUnitOfWork, initialize
from presentation.http import create_server

def main():
    parser = argparse.ArgumentParser(description='Cafe Overflow - taller local sin frameworks')
    parser.add_argument('--port', type=int, default=8080)
    parser.add_argument('--db', default=str(Path(__file__).parent / 'data' / 'cafe.sqlite3'))
    args = parser.parse_args()
    initialize(args.db)
    service = CafeService(lambda: SQLiteUnitOfWork(args.db))
    service.seed_menu()
    server = create_server(service, args.port)
    print(f'Cafe Overflow: http://127.0.0.1:{server.server_port}', flush=True)
    print('Modo taller local. Ctrl+C para detener.', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

if __name__ == '__main__':
    main()
