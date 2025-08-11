from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
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
    migration = get_object_or_404(DataMigrationUtility, pk=pk)
    if request.method == 'POST':
        form = DataMigrationUtilityForm(request.POST, instance=migration)
        if form.is_valid():
            updated_migration = form.save(commit=False)
            
            # Check if V1 data has changed - if so, re-process through API
            if (form.cleaned_data['v1_body'] != migration.v1_body or 
                form.cleaned_data['v1_css'] != migration.v1_css or 
                form.cleaned_data['v1_js'] != migration.v1_js):
                
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
                    messages.error(request, "Bearer token is missing. Please check your environment configuration.")
                    return render(request, 'data_migration_utility/data_migration_form.html', {'form': form, 'migration': migration})
                
                try:
                    response = requests.post(api_url, json=payload, headers=headers)
                    
                    if response.status_code == 200:
                        data = response.json()
                        updated_migration.v2_body = data.get('v2_body', '')
                        updated_migration.v2_css = data.get('v2_css', '')
                        updated_migration.v2_js = data.get('v2_js', '')
                        messages.success(request, "Migration updated and re-processed successfully.")
                    else:
                        messages.error(request, f"Failed to re-process migration. Status: {response.status_code}")
                        return render(request, 'data_migration_utility/data_migration_form.html', {'form': form, 'migration': migration})
                except requests.RequestException as e:
                    messages.error(request, f"Error calling API: {str(e)}")
                    return render(request, 'data_migration_utility/data_migration_form.html', {'form': form, 'migration': migration})
            else:
                messages.success(request, "Migration updated successfully.")
            
            updated_migration.save()
            return redirect('data_migration_list')
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = DataMigrationUtilityForm(instance=migration)
    
    return render(request, 'data_migration_utility/data_migration_form.html', {'form': form, 'migration': migration})

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
