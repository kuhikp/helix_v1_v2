# 🚀 Helix Tag Manager

> **A powerful Django application for migrating Adobe Helix V1 components to V2**

[![Python](https://img.shields.io/badge/Python-3.13+-blue.svg)](https://python.org)
[![Django](https://img.shields.io/badge/Django-5.2.4-green.svg)](https://djangoproject.com)
[![MySQL](https://img.shields.io/badge/MySQL-8.0+-orange.svg)](https://mysql.com)

## 📋 What is Helix Tag Manager?

The Helix Tag Manager is a comprehensive web application that helps developers migrate websites from Adobe Helix V1 to V2. It provides:

- 🔍 **Website Analysis**: Scan and analyze existing V1 components
- 🏷️ **Component Mapping**: Map V1 components to their V2 equivalents  
- 📊 **Complexity Assessment**: Evaluate migration difficulty and effort
- 🔧 **Code Generation**: Generate V2 code from V1 components
- 📈 **Progress Tracking**: Monitor migration progress across multiple sites
- 🤖 **API Access**: RESTful API for programmatic access

## 🏗️ Architecture Overview

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Frontend      │    │   Django App    │    │   Database      │
│                 │    │                 │    │                 │
│ • Admin Panel   │◄───┤ • Tag Manager   │◄───┤ • MySQL 8.0+    │
│ • Web Interface │    │ • Site Manager  │    │ • User Data     │
│ • REST Client   │    │ • Auth System   │    │ • Component Map │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## 🎯 Core Components

| Component | Purpose | Key Features |
|-----------|---------|--------------|
| **Tag Manager** | Component management | Tag extraction, mapping, versioning |
| **Site Manager** | Website analysis | Complexity scoring, page analysis |
| **Data Migration** | V1→V2 transformation | Code generation, migration preview |
| **User Management** | Authentication | Role-based access, user profiles |
| **API Component** | REST endpoints | Programmatic access, integrations |

## ⚡ Quick Start (5 Minutes)

### Prerequisites ✅

**Required:**
- 🐍 Python 3.13+ ([Download](https://python.org/downloads/))
- 🗄️ MySQL 8.0+ ([Download](https://dev.mysql.com/downloads/))
- 📦 Git LFS ([Install](https://git-lfs.github.io/))

**Optional but Recommended:**
- 🐳 Docker & Docker Compose (for containerized development)
- 🔧 VS Code with Python extension

### Step 1: Clone and Setup

1. Clone the repository and navigate to the project directory:
   ```bash
   git clone <repository-url>
   cd tag_manager
   ```

2. Create and activate a virtual environment:
   ```bash
   # macOS/Linux
   python3 -m venv venv
   source venv/bin/activate

   # Windows
   python -m venv venv
   .\venv\Scripts\activate
   ```

3. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```

### Step 2: Database Setup

1. Create a MySQL database and user:
   ```sql
   CREATE DATABASE helix_upgrade_tag_manager CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
   CREATE USER 'helix_user'@'localhost' IDENTIFIED BY 'your_password';
   GRANT ALL PRIVILEGES ON helix_upgrade_tag_manager.* TO 'helix_user'@'localhost';
   FLUSH PRIVILEGES;
   ```

2. Configure environment variables by creating a `.env` file in the project root:
   ```env
   # Django Configuration
   DEBUG=True
   SECRET_KEY=your-secure-secret-key

   # Database Configuration
   DB_NAME=helix_upgrade_tag_manager
   DB_USER=helix_user
   DB_PASSWORD=your_password
   DB_HOST=localhost
   DB_PORT=3306

   # Static Files Configuration
   STATIC_URL=/static/
   STATIC_ROOT=/absolute/path/to/static/files
   ```

3. Apply migrations and create a superuser:
   ```bash
   python manage.py migrate
   python manage.py createsuperuser
   ```

### Step 3: Import Sample Data (Optional for Development)

To set up sample data for development, choose one of the following options:

**Option 1: Automated Setup**
   ```bash
   ./setup_dev_environment.sh
   ```

This will populate the database with:
- Sample users (e.g., admin/admin123)
- Complexity parameters for various site types
- Sample Tags Extractor


### Step 4: Run the Application

1. Start the development server:
   ```bash
   python manage.py runserver
   ```

2. Access the application:
   - Main application: [http://127.0.0.1:8000/](http://127.0.0.1:8000/)
   - Admin interface: [http://127.0.0.1:8000/admin/](http://127.0.0.1:8000/admin/)

## 📝 Development Workflow

### Setting Up Your Development Environment

1. **Create a feature branch:**
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes and test:**
   ```bash
   # Run tests
   python manage.py test
   
   # Run specific app tests
   python manage.py test tag_manager_component
   python manage.py test site_manager
   
   # Check code style
   flake8 .
   ```

3. **Database operations:**
   ```bash
   # Create new migrations
   python manage.py makemigrations
   
   # Apply migrations
   python manage.py migrate
   
   # Reset database (development only)
   python manage.py flush
   ```

4. **Commit and push:**
   ```bash
   git add .
   git commit -m "feat: add new component mapping feature"
   git push origin feature/your-feature-name
   ```

### Useful Development Commands

```bash
# Django Shell
python manage.py shell

# Create superuser
python manage.py createsuperuser

# Collect static files
python manage.py collectstatic

# Show URLs
python manage.py show_urls

# Database shell
python manage.py dbshell

# Check for issues
python manage.py check
```

## 🔧 Project Structure

```
tag_manager/
├── 📁 authentication/          # User authentication & login
├── 📁 api_component/          # REST API endpoints
├── 📁 data_migration_utility/ # V1→V2 migration tools
├── 📁 site_manager/           # Website analysis & management
├── 📁 tag_manager_component/  # Core tag management
├── 📁 user_management/        # User profiles & permissions
├── 📁 static/                 # CSS, JS, images
├── 📁 templates/             # HTML templates
├── 📄 manage.py              # Django management script
├── 📄 requirements.txt       # Python dependencies
└── 📄 .env                   # Environment variables
```

## 🔌 API Endpoints

The application provides RESTful APIs for programmatic access:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/tags/` | GET, POST | List/create tags |
| `/api/mappers/` | GET, POST | List/create tag mappers |
| `/api/sites/` | GET, POST | List/analyze websites |
| `/api/migrations/` | GET, POST | List/create migrations |
| `/api/complexity/` | GET | Get complexity parameters |

### API Usage Example

```bash
# Get all tags
curl -H "Authorization: Token your-token" \
     http://localhost:8000/api/tags/

# Create a new tag mapper
curl -X POST \
     -H "Authorization: Token your-token" \
     -H "Content-Type: application/json" \
     -d '{"v1_component_name": "old-header", "v2_component_name": "new-header", "weight": 0.8}' \
     http://localhost:8000/api/mappers/
```

## 🧪 Testing

### Running Tests

```bash
# Run all tests
python manage.py test

# Run with coverage
coverage run --source='.' manage.py test
coverage report
coverage html

# Run specific test file
python manage.py test tag_manager_component.tests.test_models

# Run with verbose output
python manage.py test --verbosity=2
```

### Writing Tests

Create test files following Django conventions:

```python
# tag_manager_component/tests/test_models.py
from django.test import TestCase
from tag_manager_component.models import Tag

class TagModelTest(TestCase):
    def test_tag_creation(self):
        tag = Tag.objects.create(
            name='test-tag',
            path='/blocks/test-tag',
            version='V1',
            complexity='simple'
        )
        self.assertEqual(tag.name, 'test-tag')
        self.assertTrue(tag.id)
```

## 🚀 Production Deployment

### Environment Variables

Create a `.env.production` file:

```env
DEBUG=False
SECRET_KEY=your-super-secure-production-key
ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com

# Database
DB_NAME=helix_production_db
DB_USER=helix_prod_user
DB_PASSWORD=secure-production-password
DB_HOST=your-db-host
DB_PORT=3306

# Static files
STATIC_URL=/static/
STATIC_ROOT=/var/www/helix-tag-manager/static/
```

### Docker Deployment

```dockerfile
FROM python:3.13-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
RUN python manage.py collectstatic --noinput

CMD ["gunicorn", "tag_manager.wsgi:application", "--bind", "0.0.0.0:8000"]
```

### Production Checklist

- [ ] Set `DEBUG=False`
- [ ] Configure secure `SECRET_KEY`
- [ ] Set up proper database credentials
- [ ] Configure static file serving
- [ ] Set up SSL certificates
- [ ] Configure backup strategy
- [ ] Set up monitoring and logging
- [ ] Run security checks: `python manage.py check --deploy`

## 🛠️ Troubleshooting

### Common Issues

**Database Connection Error:**
```bash
# Check MySQL service
sudo systemctl status mysql

# Test connection
mysql -u helix_user -p -h localhost helix_upgrade_tag_manager
```

**Migration Issues:**
```bash
# Reset migrations (development only!)
python manage.py migrate --fake-initial
python manage.py migrate --fake

# Or start fresh
rm -rf */migrations/
python manage.py makemigrations
python manage.py migrate
```

**Static Files Not Loading:**
```bash
# Collect static files
python manage.py collectstatic --noinput

# Check STATIC_URL and STATIC_ROOT in settings
```

**Import Errors:**
```bash
# Check Python path
python -c "import sys; print('\n'.join(sys.path))"

# Verify virtual environment
which python
pip list
```

### Debug Mode

Enable debug mode for detailed error information:

```python
# settings.py
DEBUG = True
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'DEBUG',
    },
}
```

## 📚 Additional Resources

- **Django Documentation**: https://docs.djangoproject.com/
- **Django REST Framework**: https://www.django-rest-framework.org/
- **MySQL Documentation**: https://dev.mysql.com/doc/
- **Adobe Helix Documentation**: https://www.hlx.live/docs/

## 🤝 Contributing

### Code Style

We follow PEP 8 and use these tools:

```bash
# Install development tools
pip install flake8 black isort

# Format code
black .
isort .

# Check style
flake8 .
```

### Pull Request Process

1. Fork the repository
2. Create a feature branch
3. Make your changes with tests
4. Ensure all tests pass
5. Update documentation
6. Submit a pull request

### Commit Message Format

```
feat: add new tag mapping functionality
fix: resolve database connection issue
docs: update API documentation
test: add tests for site analysis
refactor: improve code organization
```

## 🔒 Security Best Practices

### Development Security

- ✅ Never commit `.env` files to version control
- ✅ Use `.env.example` as a template for environment variables
- ✅ Regularly rotate secrets and API keys
- ✅ Use strong passwords for database users
- ✅ Keep dependencies up to date: `pip list --outdated`

### Production Security

- ✅ Set `DEBUG=False` in production
- ✅ Use HTTPS everywhere
- ✅ Configure proper CORS headers
- ✅ Set up rate limiting
- ✅ Use secure session cookies
- ✅ Regular security audits: `pip audit`

```python
# settings.py - Production security settings
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
```

## 📊 Sample Data

The application includes comprehensive sample data for development:

### Quick Setup with Sample Data

```bash
# One-command setup (recommended for new developers)
./setup_dev_environment.sh
```

**This creates:**
- 👤 **2 Users**: Admin (`admin/admin123`) & Tag Manager (`tagmanager/tagmanager123`)
- ⚙️ **3 Complexity Configs**: Simple, Medium, Complex site parameters
- 🏷️ **7 Component Tags**: Mix of V1 and V2 components
- 🔄 **4 Tag Mappers**: V1→V2 migration mappings with confidence scores
- 🌐 **3 Sample Websites**: Adobe properties with realistic complexity analysis
- 📝 **2 Migration Examples**: Complete V1→V2 code transformations

### Manual Sample Data Import

```bash
# Import sample data only
python manage.py import_sample_data

# Reset and import fresh data
python manage.py import_sample_data --flush
```

For detailed information about sample data, see [`SAMPLE_DATA_README.md`](./SAMPLE_DATA_README.md).

## 🚀 Getting Started (New Developer Checklist)

### ✅ Prerequisites Setup
- [ ] Install Python 3.13+
- [ ] Install MySQL 8.0+
- [ ] Install Git LFS
- [ ] Clone the repository

### ✅ Environment Setup  
- [ ] Create virtual environment
- [ ] Install dependencies: `pip install -r requirements.txt`
- [ ] Create `.env` file (copy from `.env.example`)
- [ ] Set up MySQL database and user

### ✅ Database & Data
- [ ] Run migrations: `python manage.py migrate`
- [ ] Import sample data: `./setup_dev_environment.sh`
- [ ] Verify login with sample credentials

### ✅ Development Ready
- [ ] Start server: `python manage.py runserver`
- [ ] Access app: http://127.0.0.1:8000/
- [ ] Access admin: http://127.0.0.1:8000/admin/
- [ ] Run tests: `python manage.py test`

## 🆘 Need Help?

### Quick Solutions

**"Can't connect to database"**
```bash
# Check if MySQL is running
brew services start mysql  # macOS
sudo systemctl start mysql # Linux

# Test connection
mysql -u root -p
```

**"Module not found"**
```bash
# Ensure virtual environment is active
source venv/bin/activate  # or .\venv\Scripts\activate on Windows
pip install -r requirements.txt
```

**"Permission denied on setup script"**
```bash
chmod +x setup_dev_environment.sh
```

**"Static files not loading"**
```bash
python manage.py collectstatic --noinput
```

### Support Channels

- 📖 **Documentation**: Check `SAMPLE_DATA_README.md` for sample data details
- 🐛 **Issues**: Create GitHub issues for bugs or feature requests  
- 💬 **Discussions**: Use GitHub discussions for questions
- 📧 **Email**: Contact the development team

---

## 📈 Project Status & Roadmap

### Current Version: v2.0.0

**✅ Completed Features:**
- Core tag management system
- Website analysis and complexity scoring  
- V1→V2 component mapping
- REST API endpoints
- User authentication and roles
- Sample data generation

**🚧 In Progress:**
- Automated migration testing
- Enhanced UI/UX improvements
- Batch processing capabilities
- Performance optimizations

**🔮 Planned Features:**
- Real-time collaboration
- Advanced analytics dashboard
- Plugin system for custom components
- CI/CD pipeline integration

---

**Last Updated**: August 2025 | **Version**: 2.0.0 | **Maintained By**: Development Team

> Made with ❤️ for Helix Migration
