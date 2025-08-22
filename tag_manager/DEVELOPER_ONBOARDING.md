# 🎯 Developer Onboarding Guide

Welcome to HelixBridge! This guide will get you up and running in less than 10 minutes.

## 🚀 Super Quick Start

### Option 1: Automated Setup (Recommended)
```bash
git clone <repository-url>
cd tag_manager
cp .env.example .env
# Edit .env with your database credentials
./setup_dev_environment.sh
python manage.py runserver
```

### Option 2: Step-by-Step
```bash
# 1. Clone and setup
git clone <repository-url>
cd tag_manager
python3 -m venv venv
source venv/bin/activate  # Windows: .\venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Database setup
mysql -u root -p -e "CREATE DATABASE helix_upgrade_tag_manager;"
mysql -u root -p -e "CREATE USER 'helix_user'@'localhost' IDENTIFIED BY 'password123';"
mysql -u root -p -e "GRANT ALL PRIVILEGES ON helix_upgrade_tag_manager.* TO 'helix_user'@'localhost';"

# 4. Configure environment
cp .env.example .env
# Edit .env file with your database credentials

# 5. Setup Django
python manage.py migrate
python manage.py import_sample_data

# 6. Run server
python manage.py runserver
```

## 🎉 You're Ready!

Visit: http://127.0.0.1:8000/

**Login Credentials:**
- Admin: `admin` / `admin123`
- Tag Manager: `tagmanager` / `tagmanager123`

## 🔧 What You Get

After setup, you'll have:

✅ **Working Django Application**
- Web interface for tag management
- Admin panel with full database access
- REST API endpoints

✅ **Sample Data**
- 7 component tags (V1 and V2)
- 4 tag mappers for V1→V2 migrations  
- 3 sample websites with complexity analysis
- 2 complete migration examples

✅ **Development Tools**
- Django debug toolbar
- Sample API endpoints
- Test data for development

## 📁 Key Files & Folders

```
tag_manager/
├── 📄 manage.py                    # Django management commands
├── 📄 requirements.txt             # Python dependencies
├── 📄 .env.example                # Environment template
├── 📄 setup_dev_environment.sh    # Automated setup script
│
├── 📁 tag_manager_component/       # Core tag management
│   ├── models.py                  # Database models
│   ├── views.py                   # Web views
│   └── management/commands/       # Custom Django commands
│
├── 📁 site_manager/               # Website analysis
├── 📁 data_migration_utility/     # V1→V2 migrations
├── 📁 authentication/             # User auth
├── 📁 api_component/              # REST APIs
└── 📁 static/                     # CSS, JS, images
```

## 🚦 Next Steps

1. **Explore the Admin Panel**: http://127.0.0.1:8000/admin/
2. **Check the API**: http://127.0.0.1:8000/api/
3. **Review Sample Data**: Browse tags, mappers, and sites
4. **Run Tests**: `python manage.py test`
5. **Start Developing**: Create your first feature branch

## ❓ Need Help?

**Common Issues:**
- **Database connection error**: Check MySQL is running and credentials in `.env`
- **Module not found**: Make sure virtual environment is activated
- **Permission denied**: Run `chmod +x setup_dev_environment.sh`

**Resources:**
- 📖 Main README.md for full documentation
- 📊 SAMPLE_DATA_README.md for data details
- 🐛 GitHub Issues for problems
- 💬 Team Slack for questions

## 🎯 Development Workflow

```bash
# Create feature branch
git checkout -b feature/your-feature

# Make changes and test
python manage.py test
python manage.py runserver

# Commit and push
git add .
git commit -m "feat: add your feature"
git push origin feature/your-feature
```

---

**Happy coding! 🚀**

*Need more details? Check the main [README.md](./README.md) for comprehensive documentation.*
