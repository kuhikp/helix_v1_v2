from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse
from pytz import timezone
from .models import Tag, TagsExtractor, TagMapper, ComplexityParameter
from django.db.models import Q
import os
from dotenv import load_dotenv
import re
import requests
from django.conf import settings
from .forms import TagForm, TagsExtractorForm, TagMapperForm, ComplexityMappingForm, ComplexityParameterForm
import logging
from collections import defaultdict
from django.db import transaction
import csv
from difflib import SequenceMatcher
import io
from django.db import models
from django.conf import settings


logging.basicConfig(level=logging.CRITICAL)
logger = logging.getLogger(__name__)



def get_complexity_recommendations(complexity_type):
    """Get recommendations based on complexity type"""
    recommendations = {
        'simple': {
            'description': 'Recommended for basic websites with minimal interactive features',
            'pages': '1-50 pages',
            'components': 'Basic components with standard functionality',
            'timeline': '2-4 weeks development time',
            'resources': 'Small team (1-2 developers)'
        },
        'medium': {
            'description': 'Suitable for business websites with moderate functionality',
            'pages': '50-200 pages',
            'components': 'Mix of standard and custom components',
            'timeline': '1-3 months development time',
            'resources': 'Medium team (2-4 developers)'
        },
        'complex': {
            'description': 'For enterprise applications with advanced features',
            'pages': '200+ pages',
            'components': 'Extensive custom components and integrations',
            'timeline': '3-6 months development time',
            'resources': 'Large team (4+ developers)'
        }
    }
    return recommendations.get(complexity_type, recommendations['medium'])

# Load pagination limit from .env
load_dotenv()
PAGINATION_LIMIT = int(os.getenv('GITHUB_PAGINATION_LIMIT', 10))

@login_required
def tag_list_by_version(request):
    if request.user.role not in ['tag_manager', 'admin']:
        return HttpResponse('Unauthorized', status=403)
    tags = Tag.objects.all().order_by('name')
    return render(request, 'tag_manager_component/tag_list_by_version.html', {'tags': tags})


@login_required
def tag_list(request):
    if request.user.role not in ['tag_manager', 'admin']:
        return HttpResponse('Unauthorized', status=403)
    
    # Get filter parameters
    query = request.GET.get('q', '').strip()
    version_filter = request.GET.get('version', '')
    complexity_filter = request.GET.get('complexity', '')
    theme_type_filter = request.GET.get('theme_type', '')
    managed_by_filter = request.GET.get('managed_by', '')
    
    # Base queryset
    tags = Tag.objects.select_related('tags_extractor').all()
    
    # Apply search query
    if query:
        tags = tags.filter(
            Q(name__icontains=query) |
            Q(path__icontains=query) |
            Q(theme_type__icontains=query) |
            Q(details__icontains=query) |
            Q(version__icontains=query)
        )
    
    # Apply filters
    if version_filter:
        tags = tags.filter(version=version_filter)
    
    if complexity_filter:
        tags = tags.filter(complexity=complexity_filter)
    
    if theme_type_filter:
        tags = tags.filter(theme_type__icontains=theme_type_filter)
    
    if managed_by_filter:
        tags = tags.filter(is_managed_by=managed_by_filter)
    
    tags = tags.order_by('version', 'theme_type', 'name')
    
    # Get distinct values for filter dropdowns
    versions = Tag.objects.values_list('version', flat=True).distinct().order_by('version')
    complexities = Tag.objects.values_list('complexity', flat=True).distinct().order_by('complexity')
    theme_types = Tag.objects.exclude(theme_type__isnull=True).exclude(theme_type='').values_list('theme_type', flat=True).distinct().order_by('theme_type')
    managed_by_options = Tag.objects.values_list('is_managed_by', flat=True).distinct().order_by('is_managed_by')
    
    context = {
        'tags': tags,
        'versions': versions,
        'complexities': complexities,
        'theme_types': theme_types,
        'managed_by_options': managed_by_options,
        'current_filters': {
            'query': query,
            'version': version_filter,
            'complexity': complexity_filter,
            'theme_type': theme_type_filter,
            'managed_by': managed_by_filter,
        }
    }

    return render(request, 'tag_manager_component/tag_list.html', context)

@login_required
def tag_create(request):
    if request.user.role not in ['tag_manager', 'admin']:
        return HttpResponse('Unauthorized', status=403)
    if request.method == 'POST':
        form = TagForm(request.POST)
        if form.is_valid():
            tag = form.save(commit=False)
            tag.created_by = request.user
            tag.updated_by = request.user
            tag.save()
            return redirect('tag_list')
    else:
        form = TagForm()
    return render(request, 'tag_manager_component/tag_form.html', {'form': form})

@login_required
def tag_edit(request, pk):
    if request.user.role not in ['tag_manager', 'admin']:
        return HttpResponse('Unauthorized', status=403)
    tag = get_object_or_404(Tag, pk=pk)
    if request.method == 'POST':
        form = TagForm(request.POST, instance=tag)
        if form.is_valid():
            tag = form.save(commit=False)
            tag.updated_by = request.user
            tag.save()
            return redirect('tag_list')
    else:
        form = TagForm(instance=tag)
    return render(request, 'tag_manager_component/tag_form.html', {'form': form})

@login_required
def tag_delete(request, pk):
    if request.user.role not in ['tag_manager', 'admin']:
        return HttpResponse('Unauthorized', status=403)
    tag = get_object_or_404(Tag, pk=pk)
    if request.method == 'POST':
        tag.delete()
        return redirect('tag_list')
    return render(request, 'tag_manager_component/tag_confirm_delete.html', {'tag': tag})

def process_extractor_pages(request, extractor, start_page=1, update_db=True):
    """
    Processes .tsx files for a given TagsExtractor instance from start_page to total_pages.
    If update_db is True, updates start_page and imported fields in the DB.
    Returns a tuple: (message, tags_found)
    """
    message = None
    tags_found = []
    owner, repo = None, None
    match = re.match(r'https://github.com/([^/]+)/([^/]+)', extractor.repo_url)
    if not match:
        return 'Invalid GitHub repository URL.', []
    owner, repo = match.group(1), match.group(2)
    headers = {'Authorization': f'token {settings.GITHUB_TOKEN}'}
    if not settings.GITHUB_TOKEN:
        return 'GitHub token is not set in settings.', []
    repo_api_url = f'https://api.github.com/repos/{owner}/{repo}'
    repo_resp = requests.get(repo_api_url, headers=headers)
    if repo_resp.status_code != 200:
        return 'Cannot access repository or repository does not exist.', []
    # Get total pages if not set
    if extractor.total_pages == 0:
        search_url = f'https://api.github.com/search/code?q=repo:{owner}/{repo}+extension:tsx'
        search_resp = requests.get(search_url, headers=headers)
        if search_resp.status_code == 200:
            total_count = search_resp.json().get('total_count', 0)
            total_pages = (total_count // PAGINATION_LIMIT) + (1 if total_count % PAGINATION_LIMIT > 0 else 0)
            extractor.total_pages = total_pages
            if update_db:
                extractor.save()
        else:
            return 'Failed to retrieve total pages for .tsx files.', []
    all_items = []
    page = start_page
    processed_page = page - 1
    while page <= extractor.total_pages:
        search_url = f'https://api.github.com/search/code?q=repo:{owner}/{repo}+extension:tsx&per_page={PAGINATION_LIMIT}&page={page}'
        print(f"search_url {search_url}")
        search_resp = requests.get(search_url, headers=headers)
        if search_resp.status_code != 200:
            message = 'Failed to search for .tsx files in the repository.'
            break
        data = search_resp.json()
        items = data.get('items', [])
        for item in items:
            item['page_number'] = page
        all_items.extend(items)
        if update_db and page != processed_page:
            extractor.start_page = page
            extractor.save()
            processed_page = page
        page += 1
    if not all_items:
        message = 'No .tsx files found in the repository.'
    else:
        for item in all_items:
            file_url = item['url']
            file_resp = requests.get(file_url, headers=headers)
            if file_resp.status_code == 200:
                file_content_url = file_resp.json().get('download_url')
                if file_content_url:
                    content_resp = requests.get(file_content_url)
                    if content_resp.status_code == 200:
                        content = content_resp.text
                        tags = re.findall(r"@Component\s*\(\s*{[^}]*tag:\s*'([^']+)'", content)
                        tags_found.extend(tags)
                        path_parts = item['path'].split('/')
                        theme_type = path_parts[1] if len(path_parts) > 1 else 'default'
                        for tag in tags:
                            Tag.objects.get_or_create(
                                name=tag,
                                defaults={
                                    'path': f"{item['path']}",
                                    'details': f'Auto-generated tag for {tag}',
                                    'version': getattr(extractor, 'version_value', 'V1'),
                                    'created_by': request.user,
                                    'updated_by': request.user,
                                    'complexity': 'simple',
                                    'is_managed_by': 'automated',
                                    'tags_extractor_id': extractor.id,
                                    'theme_type': theme_type
                                }
                            )
        if tags_found:
            message = f"Extracted tags: {', '.join(tags_found)}"
        else:
            message = 'No tags found in .tsx files.'
    if update_db:
        extractor.start_page = extractor.total_pages
        extractor.imported = True
        extractor.save()
    return message, tags_found

# In tags_extractor_create, replace the main logic with a call to process_extractor_pages
@login_required
def tags_extractor_create(request):
    if request.user.role not in ['tag_manager', 'admin']:
        return HttpResponse('Unauthorized', status=403)
    message = None
    tags_found = []
    if request.method == 'POST':
        form = TagsExtractorForm(request.POST)
        if form.is_valid():
            repo_url = form.cleaned_data['repo_url']
            form.instance.imported = False
            from .models import TagsExtractor
            if TagsExtractor.objects.filter(repo_url=repo_url).exists():
                message = 'This repository URL already exists as an extractor.'
            else:
                extractor = form.save(commit=False)
                extractor.save()
                message, tags_found = process_extractor_pages(request, extractor, start_page=1, update_db=True)
                form.instance.description = message
                form.instance.imported = True
                form.save()
                return redirect('tags_extractor_list')
    else:
        form = TagsExtractorForm()
    return render(request, 'tag_manager_component/tags_extractor_form.html', {'form': form, 'message': message, 'tags_found': tags_found})

# In process_pending_items, call the same function for pending pages
@login_required
def process_pending_items(request, extractor_id):
    if request.user.role not in ['tag_manager', 'admin']:
        return HttpResponse('Unauthorized', status=403)
    extractor = get_object_or_404(TagsExtractor, id=extractor_id)
    print(f"Processing extractor: {extractor.repo_url} from page {extractor.start_page}")
    message, tags_found = process_extractor_pages(request, extractor, start_page=extractor.start_page, update_db=True)
    return redirect('tags_extractor_list')

@login_required
def tags_extractor_list(request):
    if request.user.role not in ['tag_manager', 'admin']:
        return HttpResponse('Unauthorized', status=403)
    extractors = TagsExtractor.objects.all()
    extractor_info = [
        {
            'extractor': extractor,
            'total_pages': getattr(extractor, 'total_pages', None),
            'start_page': getattr(extractor, 'start_page', None)
        }
        for extractor in extractors
    ]
    return render(request, 'tag_manager_component/tags_extractor_list.html', {'extractor_info': extractor_info})

@login_required
def tags_extractor_detail(request, extractor_id):
    if request.user.role not in ['tag_manager', 'admin']:
        return HttpResponse('Unauthorized', status=403)
    
    extractor = get_object_or_404(TagsExtractor, id=extractor_id)
    
    # Get related tags
    related_tags = Tag.objects.filter(tags_extractor=extractor).order_by('name')
    
    # Calculate statistics
    total_tags = related_tags.count()
    completion_percentage = 0
    remaining_pages = 0
    if extractor.total_pages > 0:
        completion_percentage = round((extractor.start_page / extractor.total_pages) * 100)
        remaining_pages = max(0, extractor.total_pages - extractor.start_page)
    
    context = {
        'extractor': extractor,
        'related_tags': related_tags,
        'total_tags': total_tags,
        'completion_percentage': completion_percentage,
        'remaining_pages': remaining_pages,
        'has_pending_pages': extractor.start_page < extractor.total_pages if extractor.total_pages else False,
    }
    
    return render(request, 'tag_manager_component/tags_extractor_detail.html', context)

@login_required
def tag_mapper(request):
    if request.user.role not in ['tag_manager', 'admin']:
        return HttpResponse('Unauthorized', status=403)
    v1_tags = Tag.objects.filter(version='V1').order_by('name')
    v2_tags = Tag.objects.filter(version='V2').order_by('name')
    # Build current mapping: {v1_name: [v2_name, ...]}
    v1_to_v2_map = {}
    for v1 in v1_tags:
        mappings = TagMapper.objects.filter(v1_component_name=v1.name)
        v1_to_v2_map[v1.name] = [{'v2_name': m.v2_component_name, 'weight': m.weight} for m in mappings]
    message = None
    if request.method == 'POST':
        with transaction.atomic():
            for v1 in v1_tags:
                v2_names = request.POST.get(f'v2_component_names_{v1.id}', '').strip()
                weight = request.POST.get(f'weight_{v1.id}', '1')
                # Remove old mappings for this v1
                TagMapper.objects.filter(v1_component_name=v1.name).delete()
                if v2_names:
                    for v2_name in [v.strip() for v in v2_names.split(',') if v.strip()]:
                        TagMapper.objects.create(
                            v1_component_name=v1.name,
                            v2_component_name=v2_name,
                            weight=int(weight) if weight.isdigit() else 1
                        )
            messages.success(request, 'Mappings updated successfully.')
            return redirect('tag_mapper')
        # Refresh mapping after update
        for v1 in v1_tags:
            mappings = TagMapper.objects.filter(v1_component_name=v1.name)
            v1_to_v2_map[v1.name] = [m.v2_component_name for m in mappings]
    # Helper for template to get mapping list
    def get_item(d, key):
        return d.get(key, [])
    total_v1_tags = v1_tags.count() 
    total_mappings = sum(len(v) for v in v1_to_v2_map.values())
    return render(request, 'tag_manager_component/tag_mapper.html', {
        'v1_tags': v1_tags,
        'v2_tags': v2_tags,
        'v1_to_v2_map': v1_to_v2_map,
        'get_item': get_item,
        'message': message,
        'total_v1_tags': total_v1_tags,
        'total_mappings': total_mappings
    })

@login_required
def tag_mapper_create(request):
    if request.user.role not in ['tag_manager', 'admin']:
        return HttpResponse('Unauthorized', status=403)
    if request.method == 'POST':
        form = TagMapperForm(request.POST)
        if form.is_valid():
            form.instance.v1_component_name = form.cleaned_data['v1_component_name'].strip()
            form.instance.v2_component_name = form.cleaned_data['v2_component_name'].strip()
            form.save()
            messages.success(request, "Record added successfully.")
            return redirect('tag_mapper_list')
    else:
        form = TagMapperForm()
    return render(request, 'tag_manager/tag_mapper_form.html', {'form': form})

@login_required
def export_v1_tags(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="v1_tags.csv"'
    writer = csv.writer(response)
    writer.writerow(['name', 'path', 'details', 'version', 'complexity', 'is_managed_by', 'theme_type'])
    for tag in Tag.objects.filter(version='V1').order_by('name'):
        writer.writerow([
            tag.name, tag.path, tag.details, tag.version,
            tag.complexity, tag.is_managed_by, tag.theme_type
        ])
    return response

@login_required
def export_v2_tags(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="v2_tags.csv"'
    writer = csv.writer(response)
    writer.writerow(['name', 'path', 'details', 'version', 'complexity', 'is_managed_by', 'theme_type'])
    for tag in Tag.objects.filter(version='V2').order_by('name'):
        writer.writerow([
            tag.name, tag.path, tag.details, tag.version,
            tag.complexity, tag.is_managed_by, tag.theme_type
        ])
    return response

@login_required
def export_tag_mapper_records(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="tag_mapper_records.csv"'
    writer = csv.writer(response)
    writer.writerow(['V1 Component Name', 'V2 Component Name', 'Weight'])

    for record in TagMapper.objects.all():
        writer.writerow([record.v1_component_name, record.v2_component_name, record.weight])

    return response

@login_required
def export_non_tag_mapper_records(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="non_tag_mapper_records.csv"'
    writer = csv.writer(response)
    writer.writerow(['Tag Name', 'Version', 'Theme Type', 'Path', 'Details'])

    mapped_tags = TagMapper.objects.values_list('v1_component_name', flat=True)
    non_mapped_tags = Tag.objects.exclude(name__in=mapped_tags)

    for tag in non_mapped_tags:
        writer.writerow([tag.name, tag.version, tag.theme_type, tag.path, tag.details])

    return response

@login_required
def export_non_tag_mapper_v1_records(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="non_tag_mapper_v1_records.csv"'
    writer = csv.writer(response)
    writer.writerow(['Tag Name', 'Version', 'Theme Type', 'Path', 'Details'])

    mapped_tags = TagMapper.objects.values_list('v1_component_name', flat=True)
    non_mapped_v1_tags = Tag.objects.filter(version='V1').exclude(name__in=mapped_tags)

    for tag in non_mapped_v1_tags:
        writer.writerow([tag.name, tag.version, tag.theme_type, tag.path, tag.details])

    return response

@login_required
def export_non_tag_mapper_v1_records_with_repo(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="non_tag_mapper_v1_records_with_repo.csv"'
    writer = csv.writer(response)
    writer.writerow(['Tag Name', 'Version', 'Theme Type', 'Path', 'Details', 'Repo URL'])

    mapped_tags = TagMapper.objects.values_list('v1_component_name', flat=True)
    non_mapped_v1_tags = Tag.objects.filter(version='V1').exclude(name__in=mapped_tags)

    for tag in non_mapped_v1_tags:
        repo_url = tag.tags_extractor.repo_url if tag.tags_extractor else 'N/A'
        writer.writerow([tag.name, tag.version, tag.theme_type, tag.path, tag.details, repo_url])

    return response

@login_required
def auto_map_v1_to_v2_tags(request):
    if request.user.role not in ['tag_manager', 'admin']:
        return HttpResponse('Unauthorized', status=403)
    v1_tags = Tag.objects.filter(version='V1').order_by('name')
    v2_tags = Tag.objects.filter(version='V2').order_by('name')
    mappings_created = 0
    for v1 in v1_tags:
        best_match = None
        best_score = 0.0
        for v2 in v2_tags:
            score = SequenceMatcher(None, v1.name, v2.name).ratio()
            if score > best_score:
                best_score = score
                best_match = v2
        if best_match and best_score > 0.7:
            TagMapper.objects.update_or_create(
                v1_component_name=v1.name.strip(),
                v2_component_name=best_match.name.strip(),
                defaults={'weight': int(best_score * 100)}
            )
            best_match.details = f"Auto-mapped to V1: {v1.name} (score: {best_score:.2f})"
            best_match.save()
            mappings_created += 1
    message = f"Auto-mapped V1 tags to V2 tags based on similarity checks."
    messages.success(request, message)
    return redirect('tag_mapper')

@login_required
def export_all_tags_with_mapped_attributes_and_repo(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="all_tags_with_mapped_attributes_and_repo.csv"'
    writer = csv.writer(response)
    writer.writerow(['Tag Name', 'Version', 'Theme Type', 'Path', 'Details', 'Mapped Attributes', 'Repo URL'])

    tags = Tag.objects.select_related('tags_extractor').all()

    for tag in tags:
        mapped_attributes = ', '.join(
            [f"{mapper.v2_component_name} (Weight: {mapper.weight})" for mapper in TagMapper.objects.filter(v1_component_name=tag.name)]
        )
        repo_url = tag.tags_extractor.repo_url if tag.tags_extractor else 'N/A'
        writer.writerow([tag.name, tag.version, tag.theme_type, tag.path, tag.details, mapped_attributes, repo_url])

    return response


@login_required
def complexity_mapping_upload(request):
    """
    View to handle CSV upload for bulk complexity mapping of tags.
    Expected CSV format: tag_name, complexity
    """
    if request.user.role not in ['tag_manager', 'admin']:
        return HttpResponse('Unauthorized', status=403)
    
    if request.method == 'POST':
        print(f"POST request received: {request.FILES}")  # Debug line
        form = ComplexityMappingForm(request.POST, request.FILES)
        print(f"Form is valid: {form.is_valid()}")  # Debug line
        
        if form.is_valid():
            csv_file = request.FILES['csv_file']
            print(f"Processing file: {csv_file.name}")  # Debug line
            
            try:
                # Read CSV file
                file_data = csv_file.read().decode('utf-8')
                csv_data = csv.reader(io.StringIO(file_data))
                
                # Skip header row if present
                headers = next(csv_data, None)
                print(headers)
                # If headers are present, validate them
                print(f"Headers found: {headers}")  # Debug line
                if headers:
                    headers = [h.strip().lower() for h in headers]
                    
                    # Validate headers
                    required_headers = ['tag_name', 'complexity']
                    if not all(header in headers for header in required_headers):
                        messages.error(request, 
                            f'CSV must contain columns: {", ".join(required_headers)}. '
                            f'Found: {", ".join(headers)}')
                        return render(request, 'tag_manager_component/complexity_mapping_upload.html', {'form': form})
                    
                    tag_name_idx = headers.index('tag_name')
                    complexity_idx = headers.index('complexity')
                else:
                    # Assume first column is tag_name, second is complexity
                    tag_name_idx = 0
                    complexity_idx = 1
                
                # Valid complexity choices
                valid_complexities = [choice[0] for choice in Tag.COMPLEXITY_CHOICES]
                
                # Process CSV data
                updated_count = 0
                error_count = 0
                errors = []
                
                with transaction.atomic():
                    for row_num, row in enumerate(csv_data, start=2):  # Start from 2 because of header
                        if len(row) < 2:
                            errors.append(f'Row {row_num}: Insufficient columns')
                            error_count += 1
                            continue
                        
                        tag_name = row[tag_name_idx].strip()
                        complexity = row[complexity_idx].strip().lower()
                        
                        # Validate complexity
                        if complexity not in valid_complexities:
                            errors.append(f'Row {row_num}: Invalid complexity "{complexity}". Valid options: {", ".join(valid_complexities)}')
                            error_count += 1
                            continue
                        
                        # Update tags with matching name
                        tags_updated = Tag.objects.filter(name__iexact=tag_name).update(
                            complexity=complexity,
                            updated_by=request.user
                        )
                        
                        if tags_updated == 0:
                            errors.append(f'Row {row_num}: Tag "{tag_name}" not found')
                            error_count += 1
                        else:
                            updated_count += tags_updated
                
                # Show results
                if updated_count > 0:
                    messages.success(request, f'Successfully updated complexity for {updated_count} tags.')
                
                if error_count > 0:
                    error_message = f'{error_count} errors occurred:\n' + '\n'.join(errors[:10])
                    if len(errors) > 10:
                        error_message += f'\n... and {len(errors) - 10} more errors.'
                    messages.error(request, error_message)
                
                if updated_count > 0:
                    return redirect('tag_list')
                    
            except Exception as e:
                messages.error(request, f'Error processing CSV file: {str(e)}')
                print(f"Exception occurred: {e}")  # Debug line
        else:
            print(f"Form errors: {form.errors}")  # Debug line
            messages.error(request, 'Please correct the errors below.')
    else:
        print("GET request received")  # Debug line
        form = ComplexityMappingForm()
    
    return render(request, 'tag_manager_component/complexity_mapping_upload.html', {'form': form})


@login_required
def download_complexity_mapping_template(request):
    """
    Download a CSV template for complexity mapping with comprehensive examples.
    """
    if request.user.role not in ['tag_manager', 'admin']:
        return HttpResponse('Unauthorized', status=403)
    
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="complexity_mapping_template.csv"'
    
    writer = csv.writer(response)
    
    # Write header
    writer.writerow(['tag_name', 'complexity'])
    
    # Simple complexity examples
    writer.writerow(['# SIMPLE COMPONENTS (Basic UI elements)', ''])
    writer.writerow(['helix-button', 'simple'])
    writer.writerow(['helix-label', 'simple'])
    writer.writerow(['helix-icon', 'simple'])
    writer.writerow(['helix-badge', 'simple'])
    writer.writerow(['helix-separator', 'simple'])
    writer.writerow(['helix-spacer', 'simple'])
    writer.writerow(['helix-avatar', 'simple'])
    writer.writerow(['helix-tooltip', 'simple'])
    writer.writerow(['helix-spinner', 'simple'])
    
    # Medium complexity examples
    writer.writerow(['# MEDIUM COMPONENTS (Interactive elements)', ''])
    writer.writerow(['helix-input', 'medium'])
    writer.writerow(['helix-textarea', 'medium'])
    writer.writerow(['helix-select', 'medium'])
    writer.writerow(['helix-checkbox', 'medium'])
    writer.writerow(['helix-radio', 'medium'])
    writer.writerow(['helix-slider', 'medium'])
    writer.writerow(['helix-toggle', 'medium'])
    writer.writerow(['helix-dropdown', 'medium'])
    writer.writerow(['helix-modal', 'medium'])
    writer.writerow(['helix-accordion', 'medium'])
    writer.writerow(['helix-tabs', 'medium'])
    writer.writerow(['helix-carousel', 'medium'])
    writer.writerow(['helix-pagination', 'medium'])
    writer.writerow(['helix-breadcrumb', 'medium'])
    writer.writerow(['helix-progress', 'medium'])
    
    # Complex complexity examples
    writer.writerow(['# COMPLEX COMPONENTS (Advanced functionality)', ''])
    writer.writerow(['helix-data-table', 'complex'])
    writer.writerow(['helix-data-grid', 'complex'])
    writer.writerow(['helix-tree-view', 'complex'])
    writer.writerow(['helix-navigation', 'complex'])
    writer.writerow(['helix-form-builder', 'complex'])
    writer.writerow(['helix-calendar', 'complex'])
    writer.writerow(['helix-date-picker', 'complex'])
    writer.writerow(['helix-time-picker', 'complex'])
    writer.writerow(['helix-file-upload', 'complex'])
    writer.writerow(['helix-rich-text-editor', 'complex'])
    writer.writerow(['helix-chart', 'complex'])
    writer.writerow(['helix-dashboard', 'complex'])
    writer.writerow(['helix-workflow', 'complex'])
    writer.writerow(['helix-filter-panel', 'complex'])
    writer.writerow(['helix-search-advanced', 'complex'])
    
    # Instructions
    writer.writerow(['# INSTRUCTIONS:', ''])
    writer.writerow(['# 1. Replace the sample tag names with your actual tag names', ''])
    writer.writerow(['# 2. Set complexity to one of: simple, medium, complex', ''])
    writer.writerow(['# 3. Remove all comment lines (starting with #)', ''])
    writer.writerow(['# 4. Save the file and upload it', ''])
    writer.writerow(['# 5. Tag names are case-insensitive', ''])
    
    return response



@login_required
def complexity_parameter_config(request):
    """
    View for managing complexity parameter configuration for each type.
    Each tab (simple, medium, complex) has its own config.
    """
    if request.user.role not in ['tag_manager', 'admin']:
        return HttpResponse('Unauthorized', status=403)


    # Determine active tab/type
    if request.method == 'POST':
        active_type = request.POST.get('complexity_type', 'simple')
    else:
        active_type = request.GET.get('complexity_type', 'simple')

    # Prepare configs and forms for all types
    configs = {}
    forms = {}
    for ctype in ['simple', 'medium', 'complex']:
        configs[ctype] = ComplexityParameter.objects.filter(complexity_type=ctype).first()
        forms[ctype] = ComplexityParameterForm(instance=configs[ctype])

    # Handle POST for the active tab only
    if request.method == 'POST':
        form = ComplexityParameterForm(request.POST, instance=configs[active_type])
        if form.is_valid():
            try:
                with transaction.atomic():
                    complexity_config = form.save(commit=False)
                    complexity_config.complexity_type = active_type
                    complexity_config.updated_by = request.user
                    complexity_config.save()

                    total_components = (
                        complexity_config.number_of_helix_v2_compatible +
                        complexity_config.number_of_helix_v2_non_compatible +
                        complexity_config.number_of_custom_components
                    )

                    messages.success(
                        request,
                        f'✅ {complexity_config.get_complexity_type_display()} complexity configuration saved successfully! '
                        f'Configuration updated with {complexity_config.number_of_pages} pages, '
                        f'{total_components} total components, and updated complexity distribution.'
                    )
                return redirect(f"{request.path}?complexity_type={active_type}")
            except Exception as e:
                logger.error(f"Error saving complexity configuration: {str(e)}")
                messages.error(
                    request,
                    f'❌ Error saving configuration: {str(e)}. Please try again.'
                )
        else:
            error_messages = []
            for field, errors in form.errors.items():
                field_label = form.fields[field].label if field in form.fields else field
                for error in errors:
                    error_messages.append(f"{field_label}: {error}")
            messages.error(
                request,
                f'❌ Please correct the following errors: {"; ".join(error_messages)}'
            )
        # Update the forms dict with the (possibly invalid) posted form
        forms[active_type] = form

    # Calculate totals for display (handle None config)
    config = configs[active_type]
    total_components = (
        (config.number_of_helix_v2_compatible if config else 0) +
        (config.number_of_helix_v2_non_compatible if config else 0) +
        (config.number_of_custom_components if config else 0)
    )
    total_by_complexity = (
        (config.total_simple_components if config else 0) +
        (config.total_medium_components if config else 0) +
        (config.total_complex_components if config else 0)
    )

    context = {
        'forms': forms,
        'configs': configs,
        'config': config,
        'total_components': total_components,
        'total_by_complexity': total_by_complexity,
        'page_title': 'Complexity Parameter Configuration',
        'last_updated': config.updated_at if config else None,
        'last_updated_by': config.updated_by if config else None,
        'is_new_config': not bool(config),
        'complexity_type_display': config.get_complexity_type_display() if config else active_type.title(),
        'complexity_recommendations': get_complexity_recommendations(active_type),
        'active_type': active_type,
    }
    return render(request, 'tag_manager_component/complexity_parameter_config.html', context)


# Utility: Determine website complexity by comparing site data to config thresholds
def get_website_complexity(site_data, return_config=False):
    """
    Determine the complexity type ('simple', 'medium', 'complex') for a website
    based on its values and the thresholds in ComplexityParameter.
    Checks configurations in order: simple → medium → complex.
    Returns the first configuration that the site satisfies.
    
    site_data: dict with keys like 'number_of_pages', 'number_of_helix_v2_compatible', etc.
    return_config: if True, returns tuple (complexity, config_data), otherwise just complexity
    """
 
    
    # Get all configurations
    configs = {c.complexity_type: c for c in ComplexityParameter.objects.all()}
    if not configs:
        return (None, None) if return_config else None
    
    def site_matches_config(site, config):
        """
        Check if a site matches or is within the configuration thresholds.
        A site matches if its values are less than or equal to the config thresholds.
        """
      
        checks = [
            int(site.get('number_of_pages', 0)) <= getattr(config, 'number_of_pages', 0) if getattr(config, 'number_of_pages', 0) > 0 else True,
            int(site.get('number_of_helix_v2_compatible', 0)) <= getattr(config, 'number_of_helix_v2_compatible', 0) if getattr(config, 'number_of_helix_v2_compatible', 0) > 0 else True,
            int(site.get('number_of_helix_v2_non_compatible', 0)) <= getattr(config, 'number_of_helix_v2_non_compatible', 0) if getattr(config, 'number_of_helix_v2_non_compatible', 0) > 0 else True,
            int(site.get('number_of_custom_components', 0)) <= getattr(config, 'number_of_custom_components', 0) if getattr(config, 'number_of_custom_components', 0) > 0 else True,
            int(site.get('total_simple_components', 0)) <= getattr(config, 'total_simple_components', 0) if getattr(config, 'total_simple_components', 0) > 0 else True,
            int(site.get('total_medium_components', 0)) <= getattr(config, 'total_medium_components', 0) if getattr(config, 'total_medium_components', 0) > 0 else True,
            int(site.get('total_complex_components', 0)) <= getattr(config, 'total_complex_components', 0) if getattr(config, 'total_complex_components', 0) > 0 else True,
        ]
        return all(checks)
    
    def config_to_dict(config):
        """Convert ComplexityParameter object to dictionary for storage"""
        return {
            'complexity_type': config.complexity_type,
            'number_of_pages': config.number_of_pages,
            'number_of_helix_v2_compatible': config.number_of_helix_v2_compatible,
            'number_of_helix_v2_non_compatible': config.number_of_helix_v2_non_compatible,
            'number_of_custom_components': config.number_of_custom_components,
            'total_simple_components': config.total_simple_components,
            'total_medium_components': config.total_medium_components,
            'total_complex_components': config.total_complex_components,
            'created_at': config.created_at.isoformat() if config.created_at else None,
            'updated_at': config.updated_at.isoformat() if config.updated_at else None,
        }
    
    # Check configurations in order: simple → medium → complex
    complexity_order = ['simple', 'medium', 'complex']
    
    for complexity_type in complexity_order:
        if complexity_type in configs:
            config = configs[complexity_type]
            if site_matches_config(site_data, config):
                print(f"Site matches {complexity_type} configuration")
                if return_config:
                    return complexity_type, config_to_dict(config)
                return complexity_type
    
    # If no configuration matches, default to complex
    print("Site doesn't match any configuration, defaulting to complex")
    if return_config:
        # Return complex config if available, otherwise default config
        if 'complex' in configs:
            return 'complex', config_to_dict(configs['complex'])
        return 'complex', {'complexity_type': 'complex', 'reason': 'default_fallback'}
    return 'complex'

 