from datetime import datetime
from contextlib import asynccontextmanager
import os
import sys
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv()

# Add parent directory to path to import the active SQLite data layer.
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import database as db
from backend.mpesa_api import MpesaGateWay
from backend.security import (
    bootstrap_admin_from_env,
    create_access_token,
    get_current_user,
    login_rate_limiter,
    request_client_key,
    require_admin,
    validate_security_configuration,
)


def _cors_origins() -> list[str]:
    configured = os.getenv("CORS_ORIGINS")
    if configured is None:
        return ["http://localhost:5173", "https://kipchi-pos.vercel.app"]
    return [origin.strip() for origin in configured.split(",") if origin.strip()]


@asynccontextmanager
async def lifespan(_app: FastAPI):
    validate_security_configuration()
    if "*" in _cors_origins():
        raise RuntimeError("CORS_ORIGINS must be an explicit origin allowlist")
    db.init_db()
    bootstrap_admin_from_env()
    yield


app = FastAPI(title="ZenPOS API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    allow_credentials=False,
)

# Values are sourced only from the process environment; empty config disables M-Pesa.
MPESA_CONFIG = {
    "consumer_key": os.getenv("MPESA_CONSUMER_KEY", ""),
    "consumer_secret": os.getenv("MPESA_CONSUMER_SECRET", ""),
    "shortcode": os.getenv("MPESA_SHORTCODE", ""),
    "passkey": os.getenv("MPESA_PASSKEY", ""),
}
mpesa_client = MpesaGateWay(**MPESA_CONFIG)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' data: https:; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' data: https://fonts.gstatic.com; "
        "script-src 'self'; connect-src 'self' https:; frame-ancestors 'none'"
    )
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    forwarded_proto = request.headers.get("x-forwarded-proto", "").split(",", 1)[0].strip()
    if request.url.scheme == "https" or forwarded_proto == "https":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


@app.exception_handler(RequestValidationError)
async def safe_validation_errors(_request: Request, exc: RequestValidationError):
    errors = []
    for error in exc.errors():
        item = dict(error)
        if "password" in item.get("loc", ()):
            item["input"] = "[redacted]"
        errors.append(item)
    return JSONResponse(status_code=422, content={"detail": errors})


@app.exception_handler(Exception)
async def safe_internal_error(_request: Request, _exc: Exception):
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


# --- Models ---
class SaleItem(BaseModel):
    product: int
    quantity: int
    unit_price: float
    subtotal: float


class SaleCreate(BaseModel):
    sale_number: str
    customer: Optional[int] = None
    total_amount: float
    tax_amount: float
    payment_method: str
    items: List[SaleItem]
    phone: Optional[str] = None


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=1, max_length=1024)


class ProductCreate(BaseModel):
    sku: str
    name: str
    category_id: Optional[int] = None
    cost_price: float
    price: float
    stock: int


class MpesaStkRequest(BaseModel):
    phoneNumber: str = Field(min_length=10, max_length=15)
    amount: float = Field(gt=0)
    saleId: Optional[int | str] = None


@app.post("/api/login")
def login(data: LoginRequest, request: Request):
    client_key = request_client_key(request)
    if login_rate_limiter.is_limited(client_key):
        raise HTTPException(status_code=429, detail="Too many login attempts. Try again later.")
    user = db.check_user(data.username, data.password)
    if not user:
        login_rate_limiter.record_failure(client_key)
        raise HTTPException(status_code=401, detail="Invalid credentials")
    login_rate_limiter.clear(client_key)
    try:
        token = create_access_token(user)
    except RuntimeError:
        raise HTTPException(status_code=503, detail="Authentication is not configured") from None
    # Keep the existing token/user response fields used by the browser.
    return {"token": token, "user": {"username": user["username"], "role": user["role"]}}


# Public: login only. Every data route requires a token; write/admin routes
# additionally require the current role loaded from the users table.
@app.get("/api/products/")
def get_products(search: str = "", _user: dict = Depends(get_current_user)):
    rows = db.search_products(search) if search else db.get_all_products()
    return [dict(row) for row in rows]


@app.post("/api/products/")
def add_product(data: ProductCreate, _admin: dict = Depends(require_admin)):
    try:
        db.add_product(data.sku, data.name, data.category_id, data.cost_price, data.price, data.stock)
        return {"status": "success"}
    except Exception:
        raise HTTPException(status_code=400, detail="Unable to create product") from None


@app.put("/api/products/{product_id}")
def update_product(product_id: int, data: ProductCreate, _admin: dict = Depends(require_admin)):
    try:
        db.update_product(product_id, data.sku, data.name, data.category_id, data.cost_price, data.price, data.stock)
        return {"status": "success"}
    except Exception:
        raise HTTPException(status_code=400, detail="Unable to update product") from None


@app.delete("/api/products/{product_id}")
def delete_product(product_id: int, _admin: dict = Depends(require_admin)):
    try:
        db.delete_product(product_id)
        return {"status": "success"}
    except Exception:
        raise HTTPException(status_code=400, detail="Unable to delete product") from None


@app.get("/api/customers/")
def get_customers(search: str = "", _user: dict = Depends(get_current_user)):
    rows = db.search_customers(search) if search else db.get_all_customers()
    return [dict(row) for row in rows]


@app.post("/api/sales/")
def create_sale(data: SaleCreate, _user: dict = Depends(get_current_user)):
    items = [{"product_id": item.product, "quantity": item.quantity} for item in data.items]
    try:
        total, sale_id = db.create_sale(items, data.customer)
        return {"id": sale_id, "status": "success", "total": total}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    except Exception:
        raise HTTPException(status_code=400, detail="Unable to create sale") from None


@app.get("/api/sales/")
def get_sales(_user: dict = Depends(get_current_user)):
    return [dict(row) for row in db.get_recent_sales()]


@app.get("/api/sales/{sale_id}")
def get_sale_details(sale_id: int, _user: dict = Depends(get_current_user)):
    return [dict(row) for row in db.get_sale_items(sale_id)]


@app.post("/api/realtime/mpesa/stkpush")
def mpesa_stk(data: MpesaStkRequest, _user: dict = Depends(get_current_user)):
    if not all(MPESA_CONFIG.values()) or not os.getenv("MPESA_CALLBACK_URL"):
        raise HTTPException(status_code=503, detail="M-Pesa is not configured")
    try:
        resp = mpesa_client.stk_push(
            data.phoneNumber, data.amount, os.environ["MPESA_CALLBACK_URL"]
        )
    except Exception:
        raise HTTPException(status_code=502, detail="M-Pesa request failed") from None
    return {"status": "STK_SENT", "mpesa_response": resp}


@app.get("/api/reports/dashboard")
def dashboard_stats(_admin: dict = Depends(require_admin)):
    today = datetime.now().strftime("%Y-%m-%d")
    summary = db.get_sales_summary(today)
    cogs = db.get_cogs(today)
    expenses = db.get_total_expenses(today)
    top_selling = db.get_top_selling_products(today)
    low_stock = db.get_low_stock_products(10)
    return {
        "revenue": summary["total"],
        "orders_count": summary["count"],
        "profit": summary["total"] - cogs - expenses,
        "top_selling": [dict(row) for row in top_selling],
        "low_stock": [dict(row) for row in low_stock],
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "5000")))
