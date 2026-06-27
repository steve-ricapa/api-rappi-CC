import os
import uuid
from datetime import datetime, timezone

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from google.cloud import firestore
from pydantic import BaseModel, Field


def now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def success_response(data, status_code=200):
    return JSONResponse(status_code=status_code, content={"success": True, "data": data})


def error_response(message, status_code=400):
    return JSONResponse(status_code=status_code, content={"success": False, "error": message})


def new_external_order_id():
    return f"rappi-{uuid.uuid4().hex[:12]}"


AWS_RAPPI_ORDER_URL = os.getenv("AWS_RAPPI_ORDER_URL", "")
RAPPI_API_KEY = os.getenv("RAPPI_API_KEY", "")
GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID", "")
FIRESTORE_COLLECTION = os.getenv("FIRESTORE_COLLECTION", "rappi_orders")

db = firestore.Client(project=GCP_PROJECT_ID or None)
collection = db.collection(FIRESTORE_COLLECTION)

app = FastAPI(title="rappi-order-api")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class OrderItem(BaseModel):
    productId: str
    name: str
    quantity: int = Field(gt=0)
    price: float = Field(ge=0)


class CreateRappiOrderRequest(BaseModel):
    tenantId: str = "popeyes"
    storeId: str = "store-001"
    customerName: str
    customerPhone: str
    deliveryAddress: str
    items: list[OrderItem]
    total: float = Field(ge=0)


@app.exception_handler(HTTPException)
async def http_exception_handler(_request: Request, exc: HTTPException):
    return error_response(exc.detail, exc.status_code)


@app.exception_handler(Exception)
async def unexpected_exception_handler(_request: Request, exc: Exception):
    return error_response(str(exc), 500)


@app.get("/health")
async def health():
    return success_response(
        {
            "service": "rappi-order-api",
            "status": "ok",
            "firestoreCollection": FIRESTORE_COLLECTION,
        }
    )


@app.post("/rappi/orders")
async def create_rappi_order(payload: CreateRappiOrderRequest):
    if not AWS_RAPPI_ORDER_URL:
        raise HTTPException(status_code=500, detail="AWS_RAPPI_ORDER_URL is not configured")
    if not RAPPI_API_KEY:
        raise HTTPException(status_code=500, detail="RAPPI_API_KEY is not configured")

    timestamp = now_iso()
    external_order_id = new_external_order_id()
    document = {
        "externalOrderId": external_order_id,
        "awsOrderId": None,
        "tenantId": payload.tenantId,
        "storeId": payload.storeId,
        "customerName": payload.customerName,
        "customerPhone": payload.customerPhone,
        "deliveryAddress": payload.deliveryAddress,
        "items": [item.model_dump() for item in payload.items],
        "total": payload.total,
        "status": "CREATED",
        "statusHistory": [
            {
                "status": "CREATED",
                "timestamp": timestamp,
                "source": "GCP_RAPPI",
            }
        ],
        "createdAt": timestamp,
        "updatedAt": timestamp,
    }
    collection.document(external_order_id).set(document)

    aws_payload = {
        "externalOrderId": external_order_id,
        "tenantId": payload.tenantId,
        "storeId": payload.storeId,
        "customerName": payload.customerName,
        "customerPhone": payload.customerPhone,
        "deliveryAddress": payload.deliveryAddress,
        "items": [item.model_dump() for item in payload.items],
        "total": payload.total,
        "origin": "RAPPI",
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                AWS_RAPPI_ORDER_URL,
                json=aws_payload,
                headers={"x-api-key": RAPPI_API_KEY, "Content-Type": "application/json"},
            )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Order stored in Firestore but AWS order creation failed: {exc}",
        )

    if response.status_code >= 400:
        message = response.text
        try:
            message = response.json().get("error") or response.text
        except ValueError:
            pass
        raise HTTPException(
            status_code=502,
            detail=f"Order stored in Firestore but AWS returned {response.status_code}: {message}",
        )

    try:
        aws_body = response.json()
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=f"AWS returned invalid JSON: {exc}")

    aws_order = aws_body.get("data") or {}
    aws_order_id = aws_order.get("orderId")
    collection.document(external_order_id).update({"awsOrderId": aws_order_id, "updatedAt": now_iso()})

    return success_response(
        {
            "externalOrderId": external_order_id,
            "awsOrderId": aws_order_id,
            "status": "CREATED",
        },
        201,
    )
