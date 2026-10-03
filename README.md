# ZenPOS Supermarket System

A high-volume, multi-branch POS system designed for the Kenyan retail market.

## Features
- **Backend:** Node.js, Express, PostgreSQL, Prisma.
- **Frontend:** React, Tailwind CSS.
- **Payments:** Integrated M-Pesa STK Push.
- **Multi-Branch:** Scoped data for inventory and sales.
- **Loyalty Program:** Points accumulation for customers.

## Quick Start (Local Development)

### Prerequisites
- Node.js (v18+)
- PostgreSQL

### 1. Backend Setup
```bash
cd backend
npm install
# Update .env with your DATABASE_URL and M-Pesa credentials
npx prisma generate
npm start
```

### 2. Frontend Setup
```bash
cd frontend
npm install
npm run dev
```

## Deployment
- **Termux:** Install `postgresql` and `nodejs`. Use `pm2` to manage the backend.
- **VPS:** Recommended to use Docker Compose (coming soon).

## Documentation
Refer to the `docs/` folder for detailed API, Database, and Architecture guides.
