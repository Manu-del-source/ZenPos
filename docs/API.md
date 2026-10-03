# ZenPOS API Documentation

## Auth
- `POST /api/v1/auth/login`: Authenticate and get JWT.
- `POST /api/v1/auth/register`: Create a new user.

## Inventory
- `GET /api/v1/inventory/products`: Get all products for the current branch.
- `GET /api/v1/inventory/products/:barcode`: Search product by barcode.
- `POST /api/v1/inventory/products`: Upsert a product.

## Sales
- `POST /api/v1/sales`: Create a new sale transaction.
- `GET /api/v1/sales`: Get sales history for the branch.

## Payments
- `POST /api/v1/payments/mpesa/stkpush`: Trigger STK Push to a phone number.
- `POST /api/v1/payments/mpesa/callback`: Safaricom callback listener.
