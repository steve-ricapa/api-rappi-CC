import os
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from google.cloud import firestore
from pydantic import BaseModel


def now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def success_response(data, status_code=200):
    return JSONResponse(status_code=status_code, content={"success": True, "data": data})


def error_response(message, status_code=400):
    return JSONResponse(status_code=status_code, content={"success": False, "error": message})


GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID", "")
FIRESTORE_COLLECTION = os.getenv("FIRESTORE_COLLECTION", "rappi_orders")

db = firestore.Client(project=GCP_PROJECT_ID or None)
collection = db.collection(FIRESTORE_COLLECTION)

app = FastAPI(title="rappi-status-api")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class StatusUpdateRequest(BaseModel):
    orderId: str | None = None
    tenantId: str
    storeId: str
    status: str
    timestamp: str | None = None


class FixedStatusUpdateRequest(StatusUpdateRequest):
    externalOrderId: str


@app.exception_handler(HTTPException)
async def http_exception_handler(_request: Request, exc: HTTPException):
    return error_response(exc.detail, exc.status_code)


@app.exception_handler(Exception)
async def unexpected_exception_handler(_request: Request, exc: Exception):
    return error_response(str(exc), 500)


@app.get("/health")
def health():
    return success_response(
        {
            "service": "rappi-status-api",
            "status": "ok",
            "firestoreCollection": FIRESTORE_COLLECTION,
        }
    )


def get_order_document_or_404(external_order_id: str):
    snapshot = collection.document(external_order_id).get()
    if not snapshot.exists:
        raise HTTPException(status_code=404, detail="Rappi order not found")
    return snapshot.reference, snapshot.to_dict()


def apply_status_update(external_order_id: str, payload: StatusUpdateRequest):
    reference, order = get_order_document_or_404(external_order_id)
    status_timestamp = payload.timestamp or now_iso()
    status_history = list(order.get("statusHistory") or [])
    status_history.append(
        {
            "status": payload.status,
            "timestamp": status_timestamp,
            "source": "AWS",
        }
    )

    update_data = {
        "status": payload.status,
        "updatedAt": status_timestamp,
        "statusHistory": status_history,
        "tenantId": payload.tenantId,
        "storeId": payload.storeId,
    }
    if payload.orderId:
        update_data["awsOrderId"] = payload.orderId

    reference.update(update_data)
    return {**order, **update_data, "externalOrderId": external_order_id}


@app.post("/rappi/orders/{external_order_id}/status")
def update_order_status(external_order_id: str, payload: StatusUpdateRequest):
    updated = apply_status_update(external_order_id, payload)
    return success_response({"externalOrderId": external_order_id, "status": updated["status"]})


@app.post("/rappi/status")
def update_order_status_fixed_url(payload: FixedStatusUpdateRequest):
    updated = apply_status_update(payload.externalOrderId, payload)
    return success_response({"externalOrderId": payload.externalOrderId, "status": updated["status"]})


@app.get("/rappi/orders")
def list_orders():
    documents = collection.stream()
    orders = []
    for document in documents:
        order = document.to_dict()
        order["externalOrderId"] = order.get("externalOrderId") or document.id
        orders.append(order)
    orders.sort(key=lambda item: item.get("createdAt", ""), reverse=True)
    return success_response(orders)


@app.get("/rappi/orders/{external_order_id}")
def get_order(external_order_id: str):
    _reference, order = get_order_document_or_404(external_order_id)
    order["externalOrderId"] = order.get("externalOrderId") or external_order_id
    return success_response(order)
