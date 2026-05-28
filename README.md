# ShopEase — Full-Stack E-Commerce Platform with AI Agent

<p align="center">
  <img src="https://img.shields.io/badge/Django-5.2-092E20?logo=django&logoColor=white" alt="Django">
  <img src="https://img.shields.io/badge/MySQL-8.4-4479A1?logo=mysql&logoColor=white" alt="MySQL">
  <img src="https://img.shields.io/badge/LangGraph-Agent-7C3AED?logo=langchain&logoColor=white" alt="LangGraph">
  <img src="https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white" alt="Docker">
  <img src="https://img.shields.io/badge/Auth-JWT-000000?logo=jsonwebtokens&logoColor=white" alt="JWT">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="License">
</p>

A full-stack, multi-role e-commerce platform built with **Django** and **LangGraph**, featuring an AI-powered shopping assistant that handles product discovery, cart management, order tracking, and purchase flow — all through natural conversation. JWT authentication, order lifecycle management, inventory tracking, and a unified audit logging system.

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Django Templates, vanilla JS |
| Backend | Django 5.2, Django REST Framework, SimpleJWT |
| AI Agent | LangGraph (multi-agent orchestration), DeepSeek |
| Vector Search | FAISS, sentence-transformers |
| Database | MySQL 8.4 |
| Containerization | Docker Compose |
| Auth | JWT (access + refresh token) |

## Features

- **AI Shopping Assistant** — Natural conversation interface for product discovery, cart management, order tracking, and purchase flow via LangGraph multi-agent orchestration
- **Multi-agent architecture** — Commerce, Cart, Purchase, and Order agents coordinated by a state router with fallback handling
- **Multi-role system** — Admin, Seller, and Customer with granular permissions
- **Product catalog** — Two-level category hierarchy, search, inventory management with transaction ledger
- **Order lifecycle** — Cart → Checkout → Order (paid → shipped → completed) → Refund state machine
- **Audit logging** — Full operation traceability across all modules
- **Shop social** — Follow/unfollow shops, product reviews
- **Dockerized** — `docker compose up` runs the full stack with zero local dependencies

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
│   ├── agents/             # LangGraph AI Agent (multi-agent orchestration)
│   │   ├── api/            # Agent API views & serializers
│   │   ├── graph/          # LangGraph state machine & router
│   │   ├── core/           # LLM client, tool registry, base agent
│   │   └── ops/            # Observability, alerts, traces
│   ├── users/              # User model, JWT auth, profile
│   ├── products/           # Product, Category, Shop, Inventory, Review
│   ├── orders/             # Order, OrderItem, Cart, Refund
│   └── admin_api/          # Admin dashboard, audit logs
├── frontend/               # Django Templates + vanilla JS
│   └── templates/
│       ├── ai/             # AI Workspace chat interface
│       └── users/          # Login, Register pages
├── docker/mysql/init/      # Database dump (auto-imported on first launch)
├── docker-compose.yml      # Service orchestration
└── .env                    # Environment configuration
```

## Demo Accounts

| Role | Username | Password |
|---|---|---|
| Admin | admin | admin123 |
| Customer | c00001 | gi6AWCRM7fLh |
| Seller | s00001 | pZ9R9a%jcqhW |
| CSV Admin | a00001 | HF2z8n#xytDp |

## Running Without Docker

If Docker is not available, install the following and run each service manually:

### Prerequisites

- Python 3.11+
- MySQL 8.4

### Setup

```bash
# 1. Clone & install dependencies
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 2. Configure environment
cp .env.example .env
# Edit .env — set DB_PASSWORD, DEEPSEEK_API_KEY

# 3. Run
python manage.py runserver 0.0.0.0:8000
```

Then open http://127.0.0.1:8000/

### Database

Import the pre-loaded SQL dump into your local MySQL instance:

```bash
mysql -u root -p < docker/mysql/init/01_dump.sql
```

---

Developed with AI-assisted software engineering tools.
