from django.db import models
from django.contrib.auth.models import AbstractUser

# Create your models here.

class User(AbstractUser):
    ROLE_CHOICES = [
        ('admin', 'Admin'),
        ('tag_manager', 'Tag Manager'),
    ]

    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='tag_manager')

    def __str__(self):
        return self.username
