# Café Overflow · Dev & Coffee Lounge

Aplicación web del Taller Modelo N-Tier. Implementada **sin frameworks ni dependencias externas** con HTML, CSS, JavaScript, Python 3.10+ y SQLite. Incluye tres capas lógicas, diagramas C4 de niveles 1, 2 y 3 y 39 pruebas automáticas.

## Ejecutar

1. Instala Python 3.10 o posterior si no lo tienes.
2. Abre una terminal dentro de esta carpeta.
3. Ejecuta `python run.py` (en Windows también puedes abrir `iniciar.bat`).
4. Abre <http://127.0.0.1:8080>.
5. Para detener, pulsa `Ctrl+C` en la terminal.

No necesitas `pip install`, Node.js, un servidor de bases de datos ni conexión a internet. En Windows, si `python` no se reconoce y tienes el lanzador de Python instalado, usa `py -3 run.py`.

Opciones: `python run.py --port 8081 --db data/otra-demo.sqlite3`. La base se crea automáticamente y se cargan seis productos solo cuando el catálogo está vacío. No se incluyen clientes ni pedidos reales. Para iniciar una demostración limpia, elige otra ruta de base de datos con `--db`.

## Recorrido de demostración

1. En **Pedir algo rico**, abre **Soy nuevo, crear mi perfil** y registra nombre y correo de prueba.
2. Agrega un Combo BugHunter ($24.000). Como Junior, el servidor devuelve $1.200 de descuento y un total de $22.800.
3. Elige **Mesa** e indica la mesa, o **Para llevar**. Confirma el pedido.
4. Mientras esté pendiente de pago, intenta cotizar otro pedido: el núcleo lo rechaza.
5. En **Cocina y caja**, pulsa **Confirmar pago y preparar**, **Marcar Listo** y **Marcar Entregado**.
6. Regresa a **Pedir algo rico**: el perfil tendrá $22.800 acumulados y 1 DevPoint.
7. Agrega otro combo y redime 1 punto: total $22.600. El punto se debita al registrar el pedido y se generan nuevos puntos únicamente al entregarlo.
8. En **Gestionar menú**, crea productos o edita nombre, precio y stock. Los pedidos previos conservan sus precios originales.

Los perfiles se eligen sin contraseña y los controles de caja/menú están disponibles en la misma pantalla: es una **demostración académica local**, no un comercio publicado. El pago es una confirmación simulada de caja, no un cargo financiero real.

## Estructura

```text
CafeOverflow/
├── run.py                         # Composición e inyección de dependencias
├── presentation/                  # CAPA 1: adaptación de entrada/salida
│   ├── http.py                    # HTTP, JSON y traducción de errores
│   └── static/
│       ├── index.html             # Vistas y formularios
│       ├── style.css              # Diseño adaptable
│       └── app.js                 # Renderizado y llamadas a la API
├── negocio/                       # CAPA 2: dominio y casos de uso
│   ├── modelos.py                 # Producto, Cliente, Pedido y DTO tipados
│   ├── reglas.py                  # Descuentos, puntos, ascensos y estados
│   ├── puertos.py                 # Contratos Repository y UnitOfWork
│   └── servicio.py                # Orquestación y validaciones del negocio
├── persistencia/                  # CAPA 3: acceso a datos
│   └── sqlite.py                  # Esquema, DAO, transacciones y mapeos
├── tests/test_app.py              # Pruebas de reglas, integración, HTTP y aislamiento
├── docs/                          # Documento, diagramas y evidencia de revisión
├── .github/workflows/tests.yml    # Pruebas al publicar cambios en GitHub
└── data/                          # Generada al ejecutar; excluida de Git
```

Dependencias de código: `presentation → negocio`; `persistencia → negocio.modelos/puertos` por contrato estructural; `run.py` conecta las implementaciones. El núcleo nunca importa persistencia ni presentación. La UI no calcula subtotales, descuentos, puntos o niveles: muestra la cotización devuelta por el servidor. Convertir centavos a pesos para mostrar moneda, o convertir la entrada de precio a centavos, es adaptación de formato.

El flujo de ejecución es presentación → servicio de negocio → contrato de repositorio/unidad de trabajo → SQLite. La inversión de dependencias mantiene la tecnología de datos fuera del núcleo. Los tres paquetes representan **capas lógicas**, no tres servidores físicos: el servidor Python ejecuta las tres partes del servidor y SQLite es un archivo local; JavaScript se ejecuta en el navegador.

## Reglas implementadas

| Regla | Implementación |
|---|---|
| Junior / Mid / Senior | 5 % / 10 % / 15 % sobre subtotal |
| Nuevo cliente | Junior, $0 acumulados y 0 puntos |
| Ascenso a Mid | Acumulado completado ≥ $500.000 |
| Ascenso a Senior | Acumulado completado ≥ $1.500.000 |
| Acumulación | Un punto por cada $20.000 netos del pedido completado; división entera por pedido |
| Redención | Cada punto vale $200 y se aplica después del descuento por nivel |
| Stock | No puede registrarse una cantidad mayor que la disponible; suma líneas repetidas antes de validar |
| Pedido pendiente | No se permite otro pedido del mismo cliente mientras exista uno pendiente de pago |
| Estados | Pendiente de pago → En Preparación → Listo → Entregado |

### Decisiones sobre aspectos no definidos por el enunciado

- Moneda de demostración: COP; importes internos en centavos enteros. El símbolo `$` del taller no identifica por sí solo la moneda.
- “Completado” significa **Entregado**. Antes de ese estado no hay puntos nuevos, acumulado ni ascenso.
- “Consumido” se interpreta como total neto después de ambos descuentos. Los sobrantes inferiores a $20.000 no se acumulan entre pedidos para ganar puntos, pero sí forman parte del monto histórico.
- Redención solo de puntos ya acreditados: se aplica después del porcentaje y no puede exceder el saldo ni el neto disponible. Se rechaza el exceso, sin truncarlo silenciosamente.
- El descuento porcentual se redondea a un centavo con half-up. Un pedido de $1,10 Junior tiene descuento de $0,06 y total de $1,04.
- Stock y puntos redimidos se descuentan al **registrar** el pedido, de forma atómica. No se vuelven a descontar al pagar o entregar.
- Un pedido conserva el nivel, porcentaje, nombres y precios del momento de su registro. Un ascenso no modifica pedidos ya registrados; afecta a los nuevos pedidos posteriores.
- El pago se confirma manualmente en caja. No se incluyen pasarela, facturación fiscal, autenticación, cancelaciones, devoluciones ni vencimiento automático de pedidos. Un pedido pendiente se resuelve siguiendo el flujo de pago/entrega; no hay liberación automática de reservas.

## Consistencia e idempotencia

`BEGIN IMMEDIATE` abre la transacción antes de las lecturas que preceden a las decisiones. Dos solicitudes competidoras no pueden leer el mismo stock y confirmar simultáneamente la última unidad. Este bloqueo también serializa el saldo de puntos y la condición de pedido pendiente. El DAO no toma esas decisiones: las ejecuta `CafeService` dentro de la transacción provista por el adaptador.

`request_key` identifica una solicitud de pedido. Un reintento con el mismo cliente, clave y contenido devuelve el pedido existente, sin descontar stock o puntos otra vez. Cambiar el contenido con la misma clave produce rechazo. Repetir la transición al estado actual no tiene efectos adicionales. La entrega acredita puntos e histórico una sola vez en la misma transacción que cambia el estado.

La restricción SQL única de `(client_id, request_key)` y las claves foráneas conservan integridad estructural. La persistencia no decide descuentos, puntos, niveles, suficiencia de stock ni transiciones.

## Pruebas

```bash
python -m unittest discover -s tests -v
```

39 pruebas: límites de ascenso, porcentajes, redención y redondeo; nuevos clientes; cantidades inválidas; stock repetido y concurrente; exclusión de pedidos pendientes; estados; acreditación única; precios históricos; rollback; API y rechazo de total manipulado; aislamiento de importaciones.

La suite crea bases temporales y no modifica `data/cafe.sqlite3`. Si un entorno restringe su carpeta temporal, configura `TEMP`/`TMP` hacia una carpeta de trabajo autorizada. `docs/PRUEBAS.txt` contiene la evidencia de la ejecución realizada.

## API local

| Método y ruta | Caso de uso |
|---|---|
| GET `/api/bootstrap` | Productos, clientes y pedidos de la demostración |
| POST `/api/clients` | Registrar cliente: `name`, `email` |
| POST `/api/products` | Crear producto: `name`, `price_cents`, `stock` |
| POST `/api/products/{id}` | Actualizar producto con los mismos campos |
| POST `/api/quote` | Calcular pedido sin persistir |
| POST `/api/orders` | Registrar pedido y reservar stock/puntos |
| POST `/api/orders/{id}/state` | Cambiar estado con el campo `state` |

Cotización/pedido: `client_id`, `items: [{product_id, quantity}]`, `redeem_points`, `mode` (`Mesa` o `Para llevar`), `table`; registro requiere además `request_key`. Los identificadores se obtienen de las respuestas del servidor. El servidor ignora totales/niveles enviados por el cliente y los determina desde sus propios datos.

## Diagramas y documento

- [Documento del taller](docs/Taller_NTier_CafeOverflow_Resuelto.pdf)
- [Arquitectura editable](docs/ARQUITECTURA.md)
- [C4 nivel 1 · Contexto](docs/C4_Nivel_1.svg)
- [C4 nivel 2 · Contenedores](docs/C4_Nivel_2.svg)
- [C4 nivel 3 · Componentes](docs/C4_Nivel_3.svg)

## Repositorio público

Entrega: [Calvarado187/cafe-overflow-n-tier](https://github.com/Calvarado187/cafe-overflow-n-tier).

El repositorio contiene el código, las pruebas y la documentación. No incluye bases de ejecución ni datos reales de clientes. El flujo de GitHub Actions ejecuta la suite con Python 3.12 en cada push y pull request; su resultado se consulta en la pestaña Actions.

GitHub Pages no ejecuta el servidor Python ni SQLite: esta publicación aloja el código y los documentos. La aplicación se ejecuta localmente siguiendo los pasos anteriores.

## Alcance técnico

Diseñado para demostración en `127.0.0.1`, sin cuentas autenticadas ni separación de permisos. `http.server` forma parte de la biblioteca estándar y es adecuado para este ejercicio local; la documentación de Python no lo recomienda para producción. Un despliegue real requeriría autenticación, autorización, TLS, operación del servidor, respaldo y políticas de cancelación, además de una evaluación de concurrencia con una base de datos de servidor.
