from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse
from django.db.models import Q
from tag_manager_component.models import Tag
from user_management.models import User
from django.contrib.auth.forms import UserCreationForm
from django import forms

# Custom User Creation Form
class CustomUserCreationForm(forms.ModelForm):
    password1 = forms.CharField(
        label='Password',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter password'
        })
    )
    password2 = forms.CharField(
        label='Confirm Password',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Confirm password'
        })
    )

    class Meta:
        model = User
        fields = ('username', 'email', 'first_name', 'last_name', 'role')
        widgets = {
            'username': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter username'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter email address'
            }),
            'first_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter first name'
            }),
            'last_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter last name'
            }),
            'role': forms.Select(attrs={
                'class': 'form-select'
            })
        }

    def clean_password2(self):
        password1 = self.cleaned_data.get("password1")
        password2 = self.cleaned_data.get("password2")
        if password1 and password2 and password1 != password2:
            raise forms.ValidationError("Passwords don't match")
        return password2

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
        return user

# Create your views here.
def user_login(request):
    if request.method == 'POST':
        email = request.POST.get('username')  # Form sends 'username' field
        password = request.POST.get('password')
        user = authenticate(request, username=email, password=password)
        if user is not None:
            login(request, user)
            if user.role == 'admin':
                return redirect('admin_dashboard')
            elif user.role == 'tag_manager':
                return redirect('tag_manager_dashboard')
        else:
            messages.error(request, 'Invalid email or password. Please try again.')
    return render(request, 'authentication/login.html')

@login_required
def user_logout(request):
    logout(request)
    return redirect('login')

@login_required
def admin_dashboard(request):
    if request.user.role != 'admin':
        return HttpResponse('Unauthorized', status=403)

    users = User.objects.all()  # Fetch all users

    return render(request, 'authentication/admin_dashboard.html', {
        'users': users  # Pass the users to the template
    })

@login_required
def create_user(request):
    if request.user.role != 'admin':
        return HttpResponse('Unauthorized', status=403)
    
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            messages.success(request, f'User "{user.username}" created successfully!')
            return redirect('admin_dashboard')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = CustomUserCreationForm()
    
    return render(request, 'authentication/create_user.html', {'form': form})

@login_required
def tag_manager_dashboard(request):
    if request.user.role not in ['tag_manager', 'admin']:
        return HttpResponse('Unauthorized', status=403)
    
    # Get context data for dashboard
    from data_migration_utility.models import DataMigrationUtility
    from tag_manager_component.models import TagsExtractor, Tag, TagMapper
    from site_manager.models import SiteListDetails
    
    total_migrations = DataMigrationUtility.objects.count()
    # Since DataMigrationUtility doesn't have a status field, we'll consider complete migrations
    # as those that have both V1 and V2 content
    successful_migrations = DataMigrationUtility.objects.filter(
        v1_body__isnull=False, v2_body__isnull=False
    ).exclude(v1_body='', v2_body='').count()
    total_tags = Tag.objects.count()
    total_extractors = TagsExtractor.objects.count()
    recent_migrations = DataMigrationUtility.objects.order_by('-created_at')[:5]
    recent_extractors = TagsExtractor.objects.order_by('-created_at')[:3]
    
    # Get counts for sites and tag mapper blocks
    total_sites = SiteListDetails.objects.count()
    total_tag_mapper_blocks = TagMapper.objects.count()
    
    # Get complexity counts
    simple_sites = SiteListDetails.objects.filter(complexity='simple').count()
    medium_sites = SiteListDetails.objects.filter(complexity='medium').count()
    complex_sites = SiteListDetails.objects.filter(complexity='complex').count()
    unidentified_sites = SiteListDetails.objects.filter(
        Q(complexity__isnull=True) | 
        Q(complexity='') | 
        ~Q(complexity__in=['simple', 'medium', 'complex'])
    ).count()
    
    # Calculate completion percentage
    completion_percentage = 0
    if total_migrations > 0:
        completion_percentage = round((successful_migrations / total_migrations) * 100, 1)
    
    context = {
        'total_migrations': total_migrations,
        'successful_migrations': successful_migrations,
        'total_tags': total_tags,
        'total_extractors': total_extractors,
        'completion_percentage': completion_percentage,
        'recent_migrations': recent_migrations,
        'recent_extractors': recent_extractors,
        'user': request.user,
        'total_sites': total_sites,
        'total_tag_mapper_blocks': total_tag_mapper_blocks,
        'unidentified_sites': unidentified_sites,
        'simple_sites': simple_sites,
        'medium_sites': medium_sites,
        'complex_sites': complex_sites,
    }
    
    return render(request, 'authentication/tag_manager_dashboard.html', context)

@login_required
def edit_user(request, user_id):
    if request.user.role != 'admin':
        return HttpResponse('Unauthorized', status=403)
    
    user = get_object_or_404(User, id=user_id)
    
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST, instance=user)
        if form.is_valid():
            form.save()
            messages.success(request, f'User "{user.username}" updated successfully!')
            return redirect('admin_dashboard')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = CustomUserCreationForm(instance=user)
    
    return render(request, 'authentication/edit_user.html', {'form': form, 'user_to_edit': user})

@login_required
def delete_user(request, user_id):
    if request.user.role != 'admin':
        return HttpResponse('Unauthorized', status=403)
    
    user = get_object_or_404(User, id=user_id)
    
    # Prevent deletion of the current user
    if user == request.user:
        messages.error(request, "You cannot delete your own account.")
        return redirect('view_user', user_id=user_id)
    
    # Prevent deletion of superusers by non-superusers
    if user.is_superuser and not request.user.is_superuser:
        messages.error(request, "You don't have permission to delete superuser accounts.")
        return redirect('view_user', user_id=user_id)
    
    if request.method == 'POST':
        if request.POST.get('confirm_delete'):
            username = user.username
            user.delete()
            messages.success(request, f'User "{username}" deleted successfully!')
            return redirect('admin_dashboard')
        else:
            messages.error(request, "Please confirm the deletion by checking the checkbox.")
    
    return render(request, 'authentication/delete_user.html', {'user': user})

@login_required
def view_user(request, user_id):
    if request.user.role != 'admin':
        return HttpResponse('Unauthorized', status=403)
    
    user = get_object_or_404(User, id=user_id)
    return render(request, 'authentication/view_user.html', {'user': user})
