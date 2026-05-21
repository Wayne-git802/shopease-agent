# ShopEase - Full-Stack E-Commerce Platform

<p align="center">
  <img src="https://img.shields.io/badge/Django-5.2-092E20?logo=django&logoColor=white" alt="Django">
  <img src="https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black" alt="React">
  <img src="https://img.shields.io/badge/TypeScript-5.9-3178C6?logo=typescript&logoColor=white" alt="TypeScript">
  <img src="https://img.shields.io/badge/MySQL-8.4-4479A1?logo=mysql&logoColor=white" alt="MySQL">
  <img src="https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white" alt="Docker">
  <img src="https://img.shields.io/badge/Auth-JWT-000000?logo=jsonwebtokens&logoColor=white" alt="JWT">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="License">
</p>

A full-stack, multi-role e-commerce platform built with **Django REST Framework** and **React + TypeScript**. Features JWT authentication, order lifecycle management, inventory tracking, and a unified audit logging system — all containerized with Docker Compose for one-command deployment.

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React 19, TypeScript, Vite 7 |
| Backend | Django 5.2, Django REST Framework, SimpleJWT |
| Database | MySQL 8.4 |
| Containerization | Docker Compose |
| Auth | JWT (access + refresh token) |

## Features

- **Multi-role system** — Admin, Seller, and Customer with granular permissions
- **Product catalog** — Two-level category hierarchy, search, inventory management with transaction ledger
- **Order lifecycle** — Cart → Checkout → Order (paid → shipped → completed) → Refund state machine
- **Audit logging** — 69,000+ audit records with full operation traceability across all modules
- **Shop social** — Follow/unfollow shops, product reviews with moderation queue
- **Dockerized** — `docker compose up` runs the full stack with zero local dependencies
- **Hot reload** — Source code mounted into containers; edits appear instantly in browser

## Why Docker

This project uses **MySQL** as its database engine. Unlike SQLite (a single file with zero setup), MySQL requires a running server, user accounts, schema configuration, and manual data import — steps that differ across Windows, macOS, and Linux and are prone to environment-specific failures.

Docker encapsulates the entire runtime — Python, Node.js, MySQL, and environment configuration — into a single reproducible environment. This ensures:

- **Consistency**: every machine runs the identical stack, eliminating "it works on my machine" issues
- **Zero local dependencies**: no need to install Python, Node.js, or MySQL separately
- **Automated setup**: the database is provisioned and populated on first launch with no manual steps
- **Industry standard**: Docker Compose is the default deployment method for modern web applications on GitHub

## Quick Start

### Prerequisites

**Docker Desktop only.** Download from https://www.docker.com/products/docker-desktop

### Launch

```bash
docker compose up
```

On first run, allow 2–3 minutes for MySQL to import the pre-loaded database. Once complete:

```
backend-1   | Django version 5.2, using settings 'mysite.settings'
frontend-1  | Local:  http://localhost:5173/
```

| Service | URL |
|---|---|
| Frontend | http://localhost:5173 |
| Backend API | http://localhost:8000 |
| MySQL | localhost:3306 (root / shopeease123) |

### Live Reload

All source code is mounted into containers with hot-reload enabled:

- **Backend**: Python files saved → Django auto-restarts
- **Frontend**: React/TypeScript files saved → browser updates instantly via HMR
- **Database**: accessible at `localhost:3306` with any MySQL client (Workbench, DBeaver, CLI)

## Project Structure

```
├── backend/                # Django REST API
│   ├── users/              # User model, JWT auth, profile
│   ├── products/           # Product, Category, Shop, Inventory, Review
│   ├── orders/             # Order, OrderItem, Cart, Refund
│   └── admin_api/          # Admin dashboard, audit logs, DB explorer
├── frontend/               # React SPA
│   └── src/
│       ├── App.tsx         # Main application component & routing
│       ├── api.ts          # Unified API client with JWT auto-refresh
│       └── types.ts        # TypeScript type definitions
├── docker/mysql/init/      # Database dump (auto-imported on first launch)
├── docker-compose.yml      # Service orchestration
└── .env                    # Environment configuration
```

## Demo Accounts

| Role | Username | Password |
|---|---|---|
| Admin | admin | admin123 |
| Customer | alice | password123 |
| Customer | bob | password123 |
| Seller | seller01 | seller123 |
| Seller | s00001 | seller123 |

## Running Without Docker

If Docker is not available, install the following and run each service manually:

### Prerequisites

- Python 3.10+
- Node.js 18+
- MySQL 8.4

### Backend

```bash
cd backend
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver 0.0.0.0:8000
```

### Frontend

```bash
cd frontend
npm install
npx vite --host 0.0.0.0 --port 5173
```

### Database

Import the pre-loaded SQL dump into your local MySQL instance:

```bash
mysql -u root -p < docker/mysql/init/01_dump.sql
```

---

Developed with AI-assisted software engineering tools.
