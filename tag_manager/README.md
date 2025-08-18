# Helix Tag Manager

## 📋 Overview

The Tag Manager Application is a comprehensive Django-based system designed to manage the migration from Helix V1 to V2 components. It provides tools for analyzing websites, extracting components, managing complexity parameters, and facilitating the migration process.

## 🚀 Quick Start Guide

### Prerequisites

Before you begin, ensure you have the following installed:
- Python 3.13 or higher
- MySQL 8.0 or higher
- Git LFS (Large File Storage)
- pip (Python package installer)

### Step 1: Clone and Setup

1. Clone the repository:
```bash
git clone <repository-url>
cd tag_manager
```

2. Create and activate a virtual environment:
```bash
# For macOS/Linux
python3 -m venv venv
source venv/bin/activate

# For Windows
python -m venv venv
.\venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

### Step 2: Database Setup

1. Create MySQL database and user:
```sql
CREATE DATABASE helix_tag_manager CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'helix_user'@'localhost' IDENTIFIED BY 'your_password';
GRANT ALL PRIVILEGES ON helix_tag_manager.* TO 'helix_user'@'localhost';
FLUSH PRIVILEGES;
```

2. Configure Environment Variables:
   Create a `.env` file in the project root (`tag_manager/.env`):
   ```env
   # Django Configuration
   DEBUG=True
   SECRET_KEY=your-secure-secret-key

   # Database Configuration
   DB_NAME=helix_tag_manager
   DB_USER=helix_user
   DB_PASSWORD=your_password
   DB_HOST=localhost
   DB_PORT=3306

   # Static Files Configuration
   STATIC_URL=/static/
   STATIC_ROOT=/absolute/path/to/static/files
   ```

3. Run migrations and create superuser:
```bash
python manage.py migrate
python manage.py createsuperuser
```

### Step 3: Run the Application

1. Start the development server:
```bash
python manage.py runserver
```

2. Access the application:
- Main application: http://127.0.0.1:8000/
- Admin interface: http://127.0.0.1:8000/admin/

## 📝 Development Workflow

1. Create a new branch:
```bash
git checkout -b feature/your-feature-name
```

2. Make your changes and run tests:
```bash
python manage.py test
```

3. Commit your changes:
```bash
git add .
git commit -m "Description of changes"
```

4. Push your changes:
```bash
git push origin feature/your-feature-name
```

5. Create a Pull Request

## 🔒 Security Best Practices

- Never commit `.env` files to version control.
- Use `.env.example` as a template for environment variables.
- Rotate secrets regularly and use secure storage for sensitive data.

---

**Last Updated**: August 2025
**Maintained By**: Development Team
