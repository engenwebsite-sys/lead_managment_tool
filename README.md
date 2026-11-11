# ENGEN CRM Tool

A web-based Customer Relationship Management (CRM) application designed to manage leads, customers, users, quotations, and business operations through a centralized platform.

## Features

- **Lead Management** – Create, update, assign, and track leads.
- **Customer Management** – Manage customer information and records.
- **User Management** – Role-based access for Admin and Staff.
- **Quotation Management** – Generate and manage quotations and PDF documents.
- **Authentication & Security** – Secure login, session management, and password recovery.
- **Dashboard** – View CRM summaries and business information.
- **Access Control** – Manage permissions and assigned-record access.
- **Backup & Recovery** – Encrypted database backup and restore functionality.

## Tech Stack

### Backend
- Python
- Django / Django REST Framework
- PostgreSQL
- Alembic (if applicable to the backend modules)

### Frontend
- React
- Vite
- JavaScript
- CSS

### Tools & Infrastructure
- Git & GitHub
- Docker
- Nginx

## Project Structure

```text
CRM-TOOL/
├── backend/
│   ├── app/
│   ├── audit/
│   ├── migrations/
│   ├── tests/
│   ├── .env.example
│   └── requirements.txt
│
├── crm-ui/
│   ├── src/
│   ├── tests/
│   ├── public/
│   ├── .env.example
│   └── package.json
│
├── .gitignore
└── README.md
```

## Prerequisites

- Python
- Node.js and npm
- PostgreSQL
- Git
- Docker (optional)

## Installation & Setup

### 1. Clone the Repository

```bash
git clone https://github.com/engenwebsite-sys/lead_managment_tool.git
cd lead_managment_tool
```

### 2. Backend Setup

```bash
cd backend
python -m venv venv
```

Activate the virtual environment:

**Windows:**
```powershell
venv\Scripts\activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Configure the backend environment:

```powershell
Copy-Item .env.example .env.local
```

Update the required environment variables in `.env.local`.

Run the backend using the project's configured startup command.

### 3. Frontend Setup

Open another terminal:

```bash
cd crm-ui
npm install
```

Configure the frontend environment using `.env.example` and update the required values.

Start the development server:

```bash
npm run dev
```

## Environment Variables

Configure the required environment variables in the backend and frontend environment files.

Never commit actual passwords, API keys, database credentials, OAuth secrets, or private keys.

## Testing

Run backend and frontend tests using the test commands configured in their respective project directories.

## Security

- Environment files and secrets are excluded from Git.
- Role-based authorization protects sensitive CRM operations.
- Database backups use encryption.
- Authentication and password recovery include security controls.

## License

Private and proprietary software. Unauthorized copying, distribution, or modification is prohibited.

---

**ENGEN CRM Tool**  
Developed for business and customer relationship management.
