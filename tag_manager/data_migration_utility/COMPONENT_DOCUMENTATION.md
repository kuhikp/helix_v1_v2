# Data Migration Utility Documentation

## Overview
This component facilitates the migration of data from Helix V1 to V2.

## Key Files
- `models.py`: Defines migration-related models.
- `views.py`: Handles migration logic.
- `urls.py`: URL routing for migration utilities.

## Setup Instructions
- Ensure database configurations are correctly set in the `.env` file.

## Testing
Run the following command to test the data migration utility:
```bash
python manage.py test data_migration_utility
```
