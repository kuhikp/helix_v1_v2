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
import subprocess
import json
from qdrant_client import QdrantClient


def get_ollama_info():
    """
    Fetch the Ollama list using terminal command and other information via API.
    Returns a dictionary containing the results of all operations.
    """
    base_url = os.getenv('OLLAMA_BASE_URL')
    print(f"Base URL: {base_url}")

    result = {
        'ollama_list': [],
        'ollama_status': {},
        'endpoint_response': {},
        'error': None
    }

    try:
        print("Executing 'ollama list' command...")
        list_result = subprocess.run(
            ['ollama', 'list'],
            capture_output=True,
            text=True,
            timeout=30
        )

        if list_result.returncode == 0:
            output_lines = list_result.stdout.strip().split('\n')
            models = []

            for line in output_lines[1:]:
                if line.strip():
                    parts = line.split()
                    if len(parts) >= 3:
                        model_name = parts[0]
                        model_id = parts[1] if len(parts) > 1 else ""
                        size = parts[2] if len(parts) > 2 else ""
                        modified = " ".join(parts[3:]) if len(parts) > 3 else ""

                        models.append({
                            'name': model_name,
                            'id': model_id,
                            'size': size,
                            'modified': modified
                        })

            result['ollama_list'] = {'models': models}
            print(f"Found {len(models)} Ollama models:", models)
        else:
            print(f"Error executing 'ollama list': {list_result.stderr}")
            result['error'] = f"Command failed: {list_result.stderr}"

    except subprocess.TimeoutExpired:
        print("Ollama list command timed out")
        result['error'] = "Ollama list command timed out"
    except FileNotFoundError:
        print("Ollama command not found. Make sure Ollama is installed and in PATH")
        result['error'] = "Ollama command not found"
    except Exception as e:
        print(f"Error executing ollama list: {e}")
        result['error'] = f"Error executing ollama list: {str(e)}"

    if base_url:
        headers = {
            'Authorization': f"Bearer {os.getenv('OLLAMA_API_KEY')}"
        } if os.getenv('OLLAMA_API_KEY') else {}

        try:
            status_response = requests.get(f"{base_url}/api/version", headers=headers, timeout=10)
            if status_response.status_code == 200:
                result['ollama_status'] = status_response.json()
                print("Ollama Status Response:", result['ollama_status'])
            else:
                print(f"Status API returned status code: {status_response.status_code}")
        except requests.exceptions.RequestException as e:
            print(f"Status API request error: {e}")

        try:
            endpoint_response = requests.get(f"{base_url}/api/tags", headers=headers, timeout=10)
            if endpoint_response.status_code == 200:
                result['endpoint_response'] = endpoint_response.json()
                print("Ollama Endpoint Response:", result['endpoint_response'])
            else:
                print(f"Endpoint API returned status code: {endpoint_response.status_code}")
        except requests.exceptions.RequestException as e:
            print(f"Endpoint API request error: {e}")

    return result


@login_required
def data_migration_create(request):
    if request.method == 'POST':
        form = DataMigrationUtilityForm(request.POST)
        print(form.is_valid())
        if form.is_valid():
            migration = form.save(commit=False)
            payload = {
                'v1_body': form.cleaned_data['v1_body'],
                'v1_css': form.cleaned_data['v1_css'],
                'v1_js': form.cleaned_data['v1_js']
            }

            api_url = os.getenv('API_URL')
            bearer_token = os.getenv('BEARER_TOKEN')
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
                return redirect('data_migration_detail', pk=migration.pk)
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
    ollama_info = get_ollama_info()

    context = {
        'migrations': migrations,
        'ollama_list': ollama_info.get('ollama_list', []),
        'ollama_status': ollama_info.get('ollama_status', {}),
        'endpoint_response': ollama_info.get('endpoint_response', {})
    }

    return render(request, 'data_migration_utility/data_migration_list.html', context)


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

                    original_state = {
                        'v1_body': migration.v1_body,
                        'v1_css': migration.v1_css,
                        'v1_js': migration.v1_js
                    }

                    v1_data_changed = any(
                        form.cleaned_data[field] != original_state[field]
                        for field in original_state
                    )

                    payload = {
                        'v1_body': form.cleaned_data['v1_body'],
                        'v1_css': form.cleaned_data['v1_css'],
                        'v1_js': form.cleaned_data['v1_js']
                    }

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
                            updated_migration.v2_body = data.get('v2_body', '')
                            updated_migration.v2_css = data.get('v2_css', '')
                            updated_migration.v2_js = data.get('v2_js', '')
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


@login_required
def clear_embeddings(request):
    """
    Clear all embeddings from the Qdrant vector database.
    This will remove all stored vectors and force regeneration on next migration.
    """
    if request.method == 'POST':
        try:
            print("Initializing Qdrant client...")
            qdrant = QdrantClient(":memory:")
            collection_name = os.getenv('COLLECTION_NAME', 'migration_collection')

            collection_info = qdrant.get_collection(collection_name=collection_name)
            vector_count = collection_info.vectors_count
            print(f"Collection '{collection_name}' contains {vector_count} vectors.")
            if vector_count == 0:
                messages.info(request, f"Collection '{collection_name}' exists but contains no vector data.")
            else:
                messages.success(request, f"Collection '{collection_name}' contains {vector_count} vectors.")

        except Exception as e:
            print(f"{e}")
            messages.error(request, f"Error clearing embeddings: {str(e)}")
        return redirect('data_migration_list')

    context = {
        'action_title': 'Clear Embeddings',
        'action_description': 'This will remove all stored embeddings from the vector database. The embeddings will be regenerated on the next migration.',
        'warning_message': 'This action cannot be undone. All embeddings will need to be regenerated.',
        'confirm_url': 'clear_embeddings',
        'cancel_url': 'data_migration_list'
    }
    return render(request, 'data_migration_utility/confirm_action.html', context)
