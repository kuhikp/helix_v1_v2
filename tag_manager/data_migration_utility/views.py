from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse
from django.db import transaction
from django.core.exceptions import ValidationError
from .models import DataMigrationUtility
from .forms import DataMigrationUtilityForm
import requests
import os

@login_required
def data_migration_create(request):
    if request.method == 'POST':
        print("Received POST request for data migration")
        form = DataMigrationUtilityForm(request.POST)
        print("Received POST request for data migration")
        print(form.is_valid())
        if form.is_valid():
            print("Received POST request for data migration")
            migration = form.save(commit=False)
            payload = {
                'v1_body': form.cleaned_data['v1_body'],
                'v1_css': form.cleaned_data['v1_css'],
                'v1_js': form.cleaned_data['v1_js']
            }
            # Call webservice to convert V1 details to V2 details using Bearer token
            api_url = os.getenv('API_URL')
            bearer_token = os.getenv('BEARER_TOKEN')  # Ensure BEARER_TOKEN is set in your .env file
            headers = {
                'Authorization': f'Bearer {bearer_token}',
                'Content-Type': 'application/json'
            }
            if not bearer_token:
                messages.error(request, "Bearer token is missing. Please check your environment configuration.")
                return render(request, 'data_migration_utility/data_migration_form.html', {'form': form})

             
            response = requests.post(api_url, json=payload, headers=headers)
            
            
            if response.status_code == 403:
                try:
                    error_detail = response.json()
                    messages.error(request, f"Forbidden: {error_detail}")
                except:
                    messages.error(request, f"Forbidden: {response.text}")
                return render(request, 'data_migration_utility/data_migration_form.html', {'form': form})
            elif response.status_code == 401:
                messages.error(request, "Unauthorized: Invalid or expired Bearer token.")
                return render(request, 'data_migration_utility/data_migration_form.html', {'form': form})
            elif response.status_code == 200:
                data = response.json()
                migration.v2_body = data.get('v2_body', '')
                migration.v2_css = data.get('v2_css', '')
                migration.v2_js = data.get('v2_js', '')
                migration.save()
                messages.success(request, "Migration completed successfully.")
                return redirect('data_migration_edit', pk=migration.pk)
            else:
                try:
                    error_detail = response.json()
                    messages.error(request, f"Failed to migrate data. Status: {response.status_code}, Error: {error_detail}")
                except:
                    messages.error(request, f"Failed to migrate data. Status: {response.status_code}, Response: {response.text}")
        else:
            print("Form is invalid")
            print(form.errors)
    else:
        print("Received GET request for data migration")
        form = DataMigrationUtilityForm()
    return render(request, 'data_migration_utility/data_migration_form.html', {'form': form})

@login_required
def data_migration_list(request):
    migrations = DataMigrationUtility.objects.all()
    return render(request, 'data_migration_utility/data_migration_list.html', {'migrations': migrations})

@login_required
def data_migration_edit(request, pk):
    if request.user.role not in ['admin', 'migration_manager']:
        messages.error(request, "You don't have permission to edit migrations.")
        return redirect('data_migration_list')
        
    migration = get_object_or_404(DataMigrationUtility, pk=pk)
    if request.method == 'POST':
        form = DataMigrationUtilityForm(request.POST, instance=migration)
        if form.is_valid():
            try:
                with transaction.atomic():
                    updated_migration = form.save(commit=False)
                    
                    # Store original state for comparison
                    original_state = {
                        'v1_body': migration.v1_body,
                        'v1_css': migration.v1_css,
                        'v1_js': migration.v1_js
                    }
                    
                    # Check if V1 data has changed
                    v1_data_changed = any(
                        form.cleaned_data[field] != original_state[field]
                        for field in original_state
                    )
                    
                    payload = {
                        'v1_body': form.cleaned_data['v1_body'],
                        'v1_css': form.cleaned_data['v1_css'],
                        'v1_js': form.cleaned_data['v1_js']
                    }
                    
                    # Call webservice to convert V1 details to V2 details
                    api_url = os.getenv('API_URL')
                    bearer_token = os.getenv('BEARER_TOKEN')
                    headers = {
                        'Authorization': f'Bearer {bearer_token}',
                        'Content-Type': 'application/json'
                    }
                    
                    if not bearer_token:
                        raise ValidationError("Bearer token is missing. Please check your environment configuration.")
                    
                    try:
                        response = requests.post(api_url, json=payload, headers=headers, timeout=30)
                        if response.status_code == 200:
                            data = response.json()
                            # Store the new V2 content
                            updated_migration.v2_body = data.get('v2_body', '')
                            updated_migration.v2_css = data.get('v2_css', '')
                            updated_migration.v2_js = data.get('v2_js', '')
                            
                            if v1_data_changed:
                                messages.success(request, "V1 content changes detected. Migration re-processed successfully.")
                            else:
                                messages.success(request, "Migration updated successfully.")
                        elif response.status_code == 403:
                            raise ValidationError("Access denied. Please check your authorization token.")
                        elif response.status_code == 401:
                            raise ValidationError("Authentication failed. Please ensure your token is valid.")
                        else:
                            try:
                                error_data = response.json()
                                error_message = error_data.get('error', str(error_data))
                            except:
                                error_message = response.text
                            raise ValidationError(f"API Error (Status {response.status_code}): {error_message}")
                    except requests.Timeout:
                        raise ValidationError("API request timed out. Please try again.")
                    except requests.ConnectionError:
                        raise ValidationError("Could not connect to the API. Please check your network connection.")
                    
                    # Save the changes
                    updated_migration.save()
                    form.save_m2m()
                    
                    if not v1_data_changed:
                        messages.success(request, "Migration details updated successfully.")
                    
                    return redirect('data_migration_detail', pk=migration.pk)
                    
            except ValidationError as e:
                messages.error(request, str(e))
            except requests.RequestException as e:
                messages.error(request, f"Error calling API: {str(e)}")
            except Exception as e:
                messages.error(request, f"Error saving migration: {str(e)}")
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = DataMigrationUtilityForm(instance=migration)
    
    context = {
        'form': form,
        'migration': migration,
        'title': 'Edit Migration',
        'submit_text': 'Save Changes',
        'is_edit': True,
        'show_api_fields': True,
        'has_changes': bool(migration.updated_at and migration.created_at != migration.updated_at)
    }
    
    return render(request, 'data_migration_utility/data_migration_form.html', context)

@login_required
def data_migration_delete(request, pk):
    migration = get_object_or_404(DataMigrationUtility, pk=pk)
    if request.method == 'POST':
        migration.delete()
        messages.success(request, "Migration deleted successfully.")
        return redirect('data_migration_list')
    return render(request, 'data_migration_utility/data_migration_confirm_delete.html', {'migration': migration})

@login_required
def data_migration_detail(request, pk):
    migration = get_object_or_404(DataMigrationUtility, pk=pk)
    return render(request, 'data_migration_utility/data_migration_detail.html', {'migration': migration})
