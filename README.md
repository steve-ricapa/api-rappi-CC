# gcp-rappi-fake

Proyecto GCP que representa un sistema externo independiente llamado `Rappi Fake` dentro de la arquitectura multi-nube del Sistema de Gestion de Pedidos Popeyes.

## Que representa GCP en la arquitectura

- GCP simula la plataforma externa de Rappi.
- `rappi-order-api` crea pedidos externos y los envia a AWS por REST.
- `rappi-status-api` recibe cambios de estado enviados desde AWS por REST.
- GCP mantiene su propia persistencia con Firestore.

## Por que Firestore es la base propia de Rappi

- Firestore representa la base de datos independiente del sistema externo.
- Los pedidos creados desde Rappi Fake viven primero en GCP.
- AWS no comparte DynamoDB con GCP; ambos sistemas solo se comunican por APIs HTTP.

## Por que GCP no accede a DynamoDB

- El requerimiento multi-nube pide aislamiento entre plataformas.
- GCP no debe depender internamente de AWS para su persistencia.
- La integracion entre nubes se hace unicamente por REST:
  - GCP -> AWS: `POST /orders/rappi`
  - AWS -> GCP: `POST /rappi/orders/{externalOrderId}/status`

## Estructura

```text
gcp-rappi-fake/
├── terraform/
│   ├── main.tf
│   ├── variables.tf
│   ├── outputs.tf
│   └── terraform.tfvars.example
├── services/
│   ├── rappi-order-api/
│   │   ├── main.py
│   │   ├── requirements.txt
│   │   └── Dockerfile
│   └── rappi-status-api/
│       ├── main.py
│       ├── requirements.txt
│       └── Dockerfile
└── README.md
```

## Servicios implementados

### rappi-order-api

- Framework: FastAPI
- Deploy: Cloud Run
- Endpoint: `POST /rappi/orders`
- Guarda el pedido en Firestore con estado inicial `CREATED`
- Luego llama a AWS `POST /orders/rappi`
- Si AWS responde bien, guarda `awsOrderId`

### rappi-status-api

- Framework: FastAPI
- Deploy: Cloud Run
- Endpoints:
  - `POST /rappi/orders/{externalOrderId}/status`
  - `GET /rappi/orders`
  - `GET /rappi/orders/{externalOrderId}`
- Actualiza el pedido correspondiente en Firestore
- Agrega entradas a `statusHistory`

### Ruta puente para el AWS actual

El backend AWS actual que ya tienes hace callback a una URL fija `RAPPI_STATUS_API_URL`.

Por compatibilidad, este proyecto agrega ademas:

- `POST /rappi/status`

Esa ruta acepta `externalOrderId` en el body y permite integrar sin modificar AWS hoy mismo.

## Firestore

Coleccion:

- `rappi_orders`

Documento ejemplo:

```json
{
  "externalOrderId": "rappi-xxxx",
  "awsOrderId": "ord-xxxx",
  "tenantId": "popeyes",
  "storeId": "store-001",
  "customerName": "Cliente Rappi",
  "customerPhone": "999999999",
  "deliveryAddress": "Av. Demo 123",
  "items": [],
  "total": 0,
  "status": "CREATED",
  "statusHistory": [
    {
      "status": "CREATED",
      "timestamp": "2026-06-27T12:00:00Z",
      "source": "GCP_RAPPI"
    }
  ],
  "createdAt": "2026-06-27T12:00:00Z",
  "updatedAt": "2026-06-27T12:00:00Z"
}
```

## Prerrequisitos

Debes tener configurado en tu maquina o VM GCP:

- `terraform`
- `gcloud`
- proyecto GCP activo
- autenticacion de `gcloud` lista

Terraform usa `gcloud builds submit` para construir y subir las imagenes Docker a Artifact Registry antes de crear los servicios Cloud Run.

## Configuracion de terraform.tfvars

1. Copia el ejemplo:

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars
```

2. Completa valores reales:

```tfvars
project_id                   = "tu-project-id"
region                       = "us-central1"
artifact_registry_repository = "rappi-fake-images"
firestore_collection         = "rappi_orders"
aws_rappi_order_url          = "https://tu-api-aws.execute-api.us-east-1.amazonaws.com/orders/rappi"
rappi_api_key                = "misma-api-key-que-aws"
```

## Despliegue con Terraform

```bash
cd terraform
terraform init
terraform plan
terraform apply
```

## Recursos creados por Terraform

- APIs necesarias:
  - `run.googleapis.com`
  - `cloudbuild.googleapis.com`
  - `artifactregistry.googleapis.com`
  - `firestore.googleapis.com`
  - `iam.googleapis.com`
- Artifact Registry
- Firestore Native
- Cloud Run `rappi-order-api`
- Cloud Run `rappi-status-api`
- permisos HTTP publicos para demo

## Outputs utiles

Despues de `terraform apply`, obtendras:

- `rappi_order_api_url`
- `rappi_status_api_url`
- `rappi_status_callback_url_for_aws`
- `aws_rappi_order_url_configured`

## Que URL copiar en AWS como RAPPI_STATUS_API_URL

Usa el output:

- `rappi_status_callback_url_for_aws`

Ese output apunta a:

- `https://.../rappi/status`

y funciona con tu Lambda AWS actual que hace POST a una URL fija.

## Que URL de AWS colocar en GCP como AWS_RAPPI_ORDER_URL

Usa la URL publica del endpoint AWS:

- `https://<api-id>.execute-api.<region>.amazonaws.com/orders/rappi`

Ese valor se coloca en `terraform.tfvars` como:

- `aws_rappi_order_url`

## Variables de entorno en Cloud Run

`rappi-order-api`:

- `AWS_RAPPI_ORDER_URL`
- `RAPPI_API_KEY`
- `GCP_PROJECT_ID`
- `FIRESTORE_COLLECTION`

`rappi-status-api`:

- `GCP_PROJECT_ID`
- `FIRESTORE_COLLECTION`

## Ejemplos curl

### Crear pedido desde Rappi

```bash
curl -X POST "$RAPPI_ORDER_API_URL/rappi/orders" \
  -H "Content-Type: application/json" \
  -d '{
    "tenantId": "popeyes",
    "storeId": "store-001",
    "customerName": "Cliente Rappi",
    "customerPhone": "999999999",
    "deliveryAddress": "Av. Demo 123",
    "items": [
      {
        "productId": "combo-2-piezas",
        "name": "Combo 2 piezas",
        "quantity": 1,
        "price": 25.90
      }
    ],
    "total": 25.90
  }'
```

### Recibir actualizacion de estado en la ruta canonica

```bash
curl -X POST "$RAPPI_STATUS_API_URL/rappi/orders/rappi-123/status" \
  -H "Content-Type: application/json" \
  -d '{
    "orderId": "ord-abc123",
    "tenantId": "popeyes",
    "storeId": "store-001",
    "status": "PACKED",
    "timestamp": "2026-06-27T12:00:00Z"
  }'
```

### Recibir actualizacion de estado compatible con el AWS actual

```bash
curl -X POST "$RAPPI_STATUS_API_URL/rappi/status" \
  -H "Content-Type: application/json" \
  -d '{
    "externalOrderId": "rappi-123",
    "orderId": "ord-abc123",
    "tenantId": "popeyes",
    "storeId": "store-001",
    "status": "PACKED",
    "timestamp": "2026-06-27T12:00:00Z"
  }'
```

### Listar pedidos

```bash
curl "$RAPPI_STATUS_API_URL/rappi/orders"
```

### Consultar un pedido especifico

```bash
curl "$RAPPI_STATUS_API_URL/rappi/orders/rappi-123"
```

## Respuestas esperadas

### POST /rappi/orders

```json
{
  "success": true,
  "data": {
    "externalOrderId": "rappi-...",
    "awsOrderId": "ord-...",
    "status": "CREATED"
  }
}
```

### POST /rappi/orders/{externalOrderId}/status

```json
{
  "success": true,
  "data": {
    "externalOrderId": "rappi-...",
    "status": "PACKED"
  }
}
```

### GET /rappi/orders

```json
{
  "success": true,
  "data": []
}
```

### GET /rappi/orders/{externalOrderId}

```json
{
  "success": true,
  "data": {}
}
```
# api-rappi-CC
