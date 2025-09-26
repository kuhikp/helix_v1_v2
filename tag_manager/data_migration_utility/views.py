from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.db import transaction
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from .models import DataMigrationUtility, KnowledgeBase
from .forms import DataMigrationUtilityForm, KnowledgeBaseForm
import requests
import os
import subprocess
import json
# from qdrant_client import QdrantClient

# Import RAG functions
try:
    from api_component.rag import update_rag, reset_rag, get_rag_statistics, force_reload_rag
    RAG_AVAILABLE = True
except ImportError:
    RAG_AVAILABLE = False

import logging
logger = logging.getLogger(__name__)

def update_rag_system_with_feedback(request, action_description="updated"):
    """
    Helper function to update RAG system and provide user feedback.
    
    Args:
        request: Django request object for messages
        action_description: Description of the action performed (e.g., "created", "updated", "deleted")
    
    Returns:
        bool: True if RAG update was successful or not needed, False if failed
    """
    if not RAG_AVAILABLE:
        logger.info("RAG system not available, skipping update")
        return True
    
    try:
        logger.info(f"Updating RAG system after Knowledge Base entry {action_description}")
        update_success = force_reload_rag(use_database=True)
        
        if update_success:
            logger.info("RAG system updated successfully")
            return True
        else:
            logger.warning("RAG system update failed")
            messages.warning(request, f"Knowledge Base entry {action_description}, but RAG system update failed. Please update manually.")
            return False
            
    except Exception as e:
        logger.error(f"Error updating RAG system: {str(e)}")
        messages.warning(request, f"Knowledge Base entry {action_description}, but RAG update failed: {str(e)}")
        return False


def get_ollama_info():
    """
    Fetch the Ollama list using terminal command and other information via API.
    Returns a dictionary containing the results of all operations.
    """
    base_url = os.getenv('OLLAMA_BASE_URL')
    
    result = {
        'ollama_list': {'models': []},
        'ollama_status': {},
        'endpoint_response': {},
        'ollama_error': None,
        'model_names': [],
        'ollama_running': False,
    }

    if not base_url:
        result['ollama_error'] = "OLLAMA_BASE_URL environment variable is not set."
        return result

    headers = {}
    api_key = os.getenv('OLLAMA_API_KEY')
    if api_key:
        headers['Authorization'] = f"Bearer {api_key}"

    # Single try-except block for all API calls
    try:
        # Fetch models
        endpoint_response = requests.get(f"{base_url}/api/tags", headers=headers, timeout=10)
        if endpoint_response.status_code == 200:
            endpoint_data = endpoint_response.json()
            result['endpoint_response'] = endpoint_data
            
            # Process models more efficiently
            api_models = endpoint_data.get('models', [])
            formatted_models = [
                {'name': model.get('name', ''), 'size': model.get('size', 'Unknown')}
                for model in api_models if model.get('name')
            ]
            
            result['ollama_list'] = {'models': formatted_models}
            result['model_names'] = [model['name'] for model in formatted_models]
        else:
            result['ollama_error'] = f"Models API returned status code: {endpoint_response.status_code}"

        # Fetch status
        status_response = requests.get(f"{base_url}/api/version", headers=headers, timeout=10)
        if status_response.status_code == 200:
            status_data = status_response.json()
            result['ollama_status'] = status_data
            result['ollama_running'] = bool(status_data)
        else:
            print(f"Status API returned status code: {status_response.status_code}")

    except requests.RequestException as e:
        result['ollama_error'] = f"Request to Ollama API failed {e}" 
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
                try:
                    # Try to parse the response as JSON
                    data = response.json()
                except json.JSONDecodeError as e:
                    # If extra data error, try to parse only the first JSON object
                    raw = response.text
                    first_brace = raw.find('{')
                    last_brace = raw.find('}', first_brace)
                    if first_brace != -1 and last_brace != -1:
                        try:
                            data = json.loads(raw[first_brace:last_brace+1])
                        except Exception as e2:
                            messages.error(request, f"Error parsing Ollama API response: {str(e2)}")
                            return render(request, 'data_migration_utility/data_migration_form.html', {'form': form})
                    else:
                        messages.error(request, f"Error parsing Ollama API response: {str(e)}")
                        return render(request, 'data_migration_utility/data_migration_form.html', {'form': form})
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
        'ollama_list': ollama_info.get('ollama_list', {'models': []}),
        'ollama_status': ollama_info.get('ollama_status', {}),
        'endpoint_response': ollama_info.get('endpoint_response', {}),
        'model_names': ollama_info.get('model_names', []),
        'ollama_error': ollama_info.get('ollama_error')
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
            # TODO: Re-enable when QdrantClient dependencies are fixed
            # print("Initializing Qdrant client...")
            # qdrant = QdrantClient(":memory:")
            # collection_name = os.getenv('COLLECTION_NAME', 'migration_collection')
            # collection_info = qdrant.get_collection(collection_name=collection_name)
            # vector_count = collection_info.vectors_count
            # print(f"Collection '{collection_name}' contains {vector_count} vectors.")
            # if vector_count == 0:
            #     messages.info(request, f"Collection '{collection_name}' exists but contains no vector data.")
            # else:
            #     messages.success(request, f"Collection '{collection_name}' contains {vector_count} vectors.")
            messages.info(request, "Clear embeddings functionality temporarily disabled.")

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


# Knowledge Base Views
@login_required
def knowledge_base_list(request):
    """List all Knowledge Base entries with search and pagination."""
    search_query = request.GET.get('search', '')
    entries = KnowledgeBase.objects.all()
    
    if search_query:
        entries = entries.filter(
            Q(title__icontains=search_query) |
            Q(component_name__icontains=search_query) |
            Q(description__icontains=search_query) |
            Q(tags__icontains=search_query)
        )
    
    paginator = Paginator(entries, 10)  # Show 10 entries per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Check if RAG system needs updating
    rag_status = {}
    if RAG_AVAILABLE:
        try:
            stats = get_rag_statistics()
            db_entry_count = KnowledgeBase.objects.filter(is_active=True).count()
            rag_entry_count = stats.get('total_migrations', 0)
            rag_status = {
                'is_synced': db_entry_count == rag_entry_count,
                'db_count': db_entry_count,
                'rag_count': rag_entry_count,
                'available': True
            }
        except:
            rag_status = {'available': False}
    
    context = {
        'page_obj': page_obj,
        'search_query': search_query,
        'total_entries': entries.count(),
        'rag_status': rag_status,
        'can_manage_rag': request.user.is_staff or getattr(request.user, 'role', '') == 'admin'
    }
    return render(request, 'data_migration_utility/knowledge_base_list.html', context)


@login_required
def knowledge_base_create(request):
    """Create a new Knowledge Base entry. Only accessible to admin users."""
    if not request.user.is_staff and getattr(request.user, 'role', None) != 'admin':
        messages.error(request, "You don't have permission to create Knowledge Base entries.")
        return redirect('knowledge_base_list')
    
    if request.method == 'POST':
        form = KnowledgeBaseForm(request.POST)
        if form.is_valid():
            entry = form.save(commit=False)
            entry.created_by = request.user
            entry.save()
            
            # Update RAG system with new entry
            rag_updated = update_rag_system_with_feedback(request, "created")
            if rag_updated and RAG_AVAILABLE:
                messages.success(request, "Knowledge Base entry created successfully and RAG system updated.")
            else:
                messages.success(request, "Knowledge Base entry created successfully.")
            
            return redirect('knowledge_base_detail', pk=entry.pk)
    else:
        form = KnowledgeBaseForm()
    
    context = {
        'form': form,
        'title': 'Create Knowledge Base Entry',
        'submit_text': 'Create Entry'
    }
    return render(request, 'data_migration_utility/knowledge_base_form.html', context)


@login_required
def knowledge_base_detail(request, pk):
    """View a specific Knowledge Base entry."""
    entry = get_object_or_404(KnowledgeBase, pk=pk)
    context = {
        'object': entry,  # Use 'object' to match template expectations
        'entry': entry   # Keep 'entry' for backward compatibility
    }
    return render(request, 'data_migration_utility/knowledge_base_detail.html', context)


@login_required
def knowledge_base_edit(request, pk):
    """Edit a Knowledge Base entry. Only accessible to admin users or the creator."""
    entry = get_object_or_404(KnowledgeBase, pk=pk)
    
    # Check permissions
    if not (request.user.is_staff or 
            getattr(request.user, 'role', None) == 'admin' or 
            entry.created_by == request.user):
        messages.error(request, "You don't have permission to edit this Knowledge Base entry.")
        return redirect('knowledge_base_detail', pk=pk)
    
    if request.method == 'POST':
        form = KnowledgeBaseForm(request.POST, instance=entry)
        if form.is_valid():
            # Check if critical fields changed that affect RAG
            original_entry = KnowledgeBase.objects.get(pk=pk)
            critical_fields_changed = any([
                form.cleaned_data['v1_code'] != original_entry.v1_code,
                form.cleaned_data['v2_code'] != original_entry.v2_code,
                form.cleaned_data['component_name'] != original_entry.component_name,
                form.cleaned_data['is_active'] != original_entry.is_active,
                form.cleaned_data['title'] != original_entry.title,
                form.cleaned_data['description'] != original_entry.description,
                form.cleaned_data['tags'] != original_entry.tags
            ])
            
            form.save()
            
            # Update RAG system if critical fields changed
            if critical_fields_changed:
                rag_updated = update_rag_system_with_feedback(request, "updated")
                if rag_updated and RAG_AVAILABLE:
                    messages.success(request, "Knowledge Base entry updated successfully and RAG system refreshed.")
                else:
                    messages.success(request, "Knowledge Base entry updated successfully.")
            else:
                messages.success(request, "Knowledge Base entry updated successfully.")
            
            return redirect('knowledge_base_detail', pk=entry.pk)
    else:
        form = KnowledgeBaseForm(instance=entry)
    
    context = {
        'form': form,
        'entry': entry,
        'title': 'Edit Knowledge Base Entry',
        'submit_text': 'Update Entry'
    }
    return render(request, 'data_migration_utility/knowledge_base_form.html', context)


@login_required
def knowledge_base_delete(request, pk):
    """Delete a Knowledge Base entry. Only accessible to admin users or the creator."""
    entry = get_object_or_404(KnowledgeBase, pk=pk)
    
    # Check permissions
    if not (request.user.is_staff or 
            getattr(request.user, 'role', None) == 'admin' or 
            entry.created_by == request.user):
        messages.error(request, "You don't have permission to delete this Knowledge Base entry.")
        return redirect('knowledge_base_detail', pk=pk)
    
    if request.method == 'POST':
        # Store entry info before deletion for RAG update
        entry_title = entry.title
        entry_component = entry.component_name
        
        entry.delete()
        
        # Update RAG system after deletion
        rag_updated = update_rag_system_with_feedback(request, f"'{entry_title}' deleted")
        if rag_updated and RAG_AVAILABLE:
            messages.success(request, f"Knowledge Base entry '{entry_title}' deleted successfully and RAG system updated.")
        else:
            messages.success(request, f"Knowledge Base entry '{entry_title}' deleted successfully.")
        
        return redirect('knowledge_base_list')
    
    context = {
        'entry': entry
    }
    return render(request, 'data_migration_utility/knowledge_base_confirm_delete.html', context)


# RAG System Management Views
@login_required
def rag_system_status(request):
    """Display RAG system status and provide management options."""
    # Check if user is admin
    if not (request.user.is_staff or getattr(request.user, 'role', '') == 'admin'):
        messages.error(request, "Access denied. Admin permissions required.")
        return redirect('data_migration_list')
    
    context = {
        'rag_available': RAG_AVAILABLE,
        'error': None
    }
    
    if RAG_AVAILABLE:
        try:
            stats = get_rag_statistics()
            context['stats'] = stats
        except Exception as e:
            context['error'] = str(e)
    else:
        context['error'] = "RAG system not available - check dependencies"
    
    return render(request, 'data_migration_utility/rag_system_status.html', context)

@login_required
def update_rag_system(request):
    """Update the RAG system with latest Knowledge Base data."""
    # Check if user is admin
    if not (request.user.is_staff or getattr(request.user, 'role', '') == 'admin'):
        messages.error(request, "Access denied. Admin permissions required.")
        return redirect('data_migration_list')
    
    if request.method == 'POST':
        if not RAG_AVAILABLE:
            messages.error(request, "RAG system not available.")
            return redirect('rag_system_status')
        
        try:
            # Force reload RAG with database data
            success = force_reload_rag(use_database=True)
            
            if success:
                messages.success(request, "RAG system updated successfully with latest Knowledge Base data.")
            else:
                messages.error(request, "Failed to update RAG system. Check logs for details.")
                
        except Exception as e:
            messages.error(request, f"Error updating RAG system: {str(e)}")
        
        return redirect('rag_system_status')
    
    # GET request - show confirmation page
    context = {
        'action_title': 'Update RAG System',
        'action_description': 'This will update the RAG system with the latest Knowledge Base entries from the database.',
        'warning_message': 'The system will reload all data and rebuild the search index. This may take a few moments.',
        'confirm_url': 'update_rag_system',
        'cancel_url': 'rag_system_status'
    }
    return render(request, 'data_migration_utility/confirm_action.html', context)

@login_required  
def reset_rag_system(request):
    """Reset the RAG system completely."""
    # Check if user is admin
    if not (request.user.is_staff or getattr(request.user, 'role', '') == 'admin'):
        messages.error(request, "Access denied. Admin permissions required.")
        return redirect('data_migration_list')
    
    if request.method == 'POST':
        if not RAG_AVAILABLE:
            messages.error(request, "RAG system not available.")
            return redirect('rag_system_status')
        
        try:
            # Reset RAG system
            success = reset_rag(use_database=True)
            
            if success:
                messages.success(request, "RAG system reset and reinitialized successfully.")
            else:
                messages.error(request, "Failed to reset RAG system. Check logs for details.")
                
        except Exception as e:
            messages.error(request, f"Error resetting RAG system: {str(e)}")
        
        return redirect('rag_system_status')
    
    # GET request - show confirmation page
    context = {
        'action_title': 'Reset RAG System',
        'action_description': 'This will completely reset the RAG system, deleting all cached data and rebuilding from scratch.',
        'warning_message': 'This action will delete all cached embeddings and force a complete rebuild. This cannot be undone.',
        'confirm_url': 'reset_rag_system',
        'cancel_url': 'rag_system_status'
    }
    return render(request, 'data_migration_utility/confirm_action.html', context)

@login_required
def rag_system_api(request):
    """JSON API endpoint for RAG system status and statistics."""
    # Check if user is admin
    if not (request.user.is_staff or getattr(request.user, 'role', '') == 'admin'):
        return JsonResponse({'error': 'Access denied'}, status=403)
    
    if not RAG_AVAILABLE:
        return JsonResponse({'error': 'RAG system not available'}, status=500)
    
    try:
        stats = get_rag_statistics()
        return JsonResponse({
            'status': 'success',
            'data': stats
        })
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'error': str(e)
        }, status=500)
