import pandas as pd
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse
from django.utils import timezone
from .models import Tag, TagsExtractor, TagMapper, ComplexityParameter
from django.db.models import Q
import os
import tempfile
import shutil
import subprocess
from dotenv import load_dotenv
import re
import requests
import git
from django.conf import settings
from .forms import TagForm, TagsExtractorForm, TagMapperForm, ComplexityMappingForm, ComplexityParameterForm
import logging
from collections import defaultdict
from django.db import transaction
import csv
from difflib import SequenceMatcher
import io
from django.db import models
import git  # GitPython library
from django.conf import settings
import json


logging.basicConfig(level=logging.CRITICAL)
logger = logging.getLogger(__name__)



def clone_github_repo(repo_url, branch=None):
    """
    Clone a GitHub repository to a temporary directory using Django's temp directory.
    Handles repositories that use Git LFS.
    
    Args:
        repo_url: URL of the GitHub repository to clone
        branch: Optional branch to checkout
        
    Returns:
        tuple: (repo_dir, success, error_message)
            repo_dir: Path to the temporary directory containing the cloned repository
            success: Boolean indicating if the clone was successful
            error_message: String with error details if not successful
    """
    # Use Django's temp directory for storage
    base_temp_dir = os.path.join(settings.BASE_DIR, 'temp_repos')
    os.makedirs(base_temp_dir, exist_ok=True)
    
    # Create a unique subdirectory for this clone
    repo_name = repo_url.rstrip('/').split('/')[-1]
    temp_dir = os.path.join(base_temp_dir, f"{repo_name}_{timezone.now().strftime('%Y%m%d_%H%M%S')}")
    
    
    print(f"Cloning repository {repo_url} to {temp_dir}...")
    
    # Use tempfile to create a truly unique temporary directory
    temp_dir = tempfile.mkdtemp(prefix=f"{repo_name}_", dir=base_temp_dir)

    # Build the git clone command
    clone_cmd = ['git', 'clone']
    if branch:
        clone_cmd.extend(['-b', branch])
    clone_cmd.extend(['--recursive', repo_url, temp_dir])

    # First, check if git-lfs is installed and install if needed
    try:
        lfs_version = subprocess.run(
            ['git', 'lfs', 'version'],
            capture_output=True,
            text=True,
            check=False
        )
        if lfs_version.returncode != 0:
            print("Git LFS not found, attempting to install...")
            try:
                # Try brew installation first
                brew_install = subprocess.run(
                    ['brew', 'install', 'git-lfs'],
                    capture_output=True,
                    text=True,
                    check=False
                )
                if brew_install.returncode == 0:
                    print("Git LFS installed via brew")
                else:
                    # If brew fails, try pip
                    pip_install = subprocess.run(
                        ['pip3', 'install', 'git-lfs'],
                        capture_output=True,
                        text=True,
                        check=False
                    )
                    if pip_install.returncode == 0:
                        print("Git LFS installed via pip")
                    else:
                        print("Warning: Could not install git-lfs automatically")
            except Exception as e:
                print(f"Warning: Error during git-lfs installation: {e}")
    except Exception as e:
        print(f"Warning: Error checking git-lfs: {e}")

    # Run clone command and capture output
    try:
        # Initialize git-lfs globally before cloning
        subprocess.run(['git', 'lfs', 'install'], check=False)
        
        clone_result = subprocess.run(
            clone_cmd, 
            capture_output=True, 
            text=True,
            check=False
        )
    except Exception as e:
        error_message = f"Exception during git clone: {str(e)}"
        print(error_message)
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)
        return None, False, error_message

    # Check for the specific checkout failure message
    if "Clone succeeded, but checkout failed" in clone_result.stderr:
        print("Clone succeeded but checkout failed. Attempting to fix...")
        try:
            # Initialize Git LFS in the cloned repository
            subprocess.run(
                ['git', 'lfs', 'install'],
                cwd=temp_dir,
                check=False
            )
            
            # Pull LFS files
            subprocess.run(
                ['git', 'lfs', 'pull'],
                cwd=temp_dir,
                check=False
            )
            
            # Run git status to inspect the state
            status_result = subprocess.run(
                ['git', 'status'], 
                cwd=temp_dir,
                capture_output=True, 
                text=True,
                check=False
            )
            print(f"Git status output:\n{status_result.stdout}")

            # Fetch all remote branches
            subprocess.run(
                ['git', 'fetch', '--all'],
                cwd=temp_dir,
                check=False
            )
            
            # Reset to the latest state of the current branch
            subprocess.run(
                ['git', 'reset', '--hard', 'HEAD'],
                cwd=temp_dir,
                check=False
            )
            
            # Clean the working directory
            subprocess.run(
                ['git', 'clean', '-fd'],
                cwd=temp_dir,
                check=False
            )

            # Attempt to fix the checkout
            restore_result = subprocess.run(
                ['git', 'restore', '--source=HEAD', ':/'],
                cwd=temp_dir,
                capture_output=True,
                text=True,
                check=False
            )
            
            if restore_result.returncode == 0:
                print("Successfully restored working directory")
            else:
                print(f"Warning: Restore command output: {restore_result.stderr}")
                # Try alternative fix if restore fails
                subprocess.run(
                    ['git', 'checkout', '-f', 'HEAD'],
                    cwd=temp_dir,
                    check=False
                )
                
            # Verify the fix worked by checking git status again
            verify_status = subprocess.run(
                ['git', 'status'],
                cwd=temp_dir,
                capture_output=True,
                text=True,
                check=False
            )
            if "working tree clean" in verify_status.stdout:
                print("Working directory is now clean")
                
                # Do one final LFS pull to ensure all files are present
                subprocess.run(
                    ['git', 'lfs', 'pull'],
                    cwd=temp_dir,
                    check=False
                )
            else:
                print("Warning: Working directory may still have issues")
                
        except Exception as restore_error:
            error_message = f"Failed to restore working directory: {restore_error}"
            print(error_message)
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)
            return None, False, error_message
            
    elif clone_result.returncode != 0:
        error_message = f"Git clone failed: {clone_result.stderr}"
        print(error_message)
        print("PARAG K7")
        # if os.path.exists(temp_dir):
        #     shutil.rmtree(temp_dir, ignore_errors=True)
        return None, False, error_message

    # # Initialize Git LFS and pull LFS files in the cloned repo
    # try:
    #     subprocess.run(['git', 'lfs', 'install'], cwd=temp_dir, check=True)
    #     subprocess.run(['git', 'lfs', 'pull'], cwd=temp_dir, check=True)
    # except subprocess.CalledProcessError as e:
    #     print(f"Warning: LFS operations failed: {e}")
    # except Exception as e:
    #     print(f"Unexpected error during LFS operations: {e}")

    # Verify the clone was successful by checking .git directory
    if not os.path.isdir(os.path.join(temp_dir, '.git')):
        # shutil.rmtree(temp_dir, ignore_errors=True)
        print("PARAG K8")
        return None, False, "Git repository was not cloned properly"

    return temp_dir, True, None

def find_tsx_files(repo_dir):
    """
    Find all TSX files in the repository directory
    
    Args:
        repo_dir: Path to the repository directory
        
    Returns:
        list: List of paths to TSX files relative to repo_dir
    """
    tsx_files = []
    print("repo_dir")
    print(repo_dir)
    for root, dirs, files in os.walk(repo_dir):
        for file in files:
            if file.endswith('.tsx'):
                # Get path relative to repo_dir
                rel_path = os.path.relpath(os.path.join(root, file), repo_dir)
                tsx_files.append(rel_path)
    return tsx_files

def extract_tags_from_file(file_path):
    """
    Extract component tags from a TSX file
    
    Args:
        file_path: Path to the TSX file
        
    Returns:
        list: List of tags found in the file
    """
    tags = []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            # Find all tags in the format @Component({ tag: 'tag-name' })
            found_tags = re.findall(r"@Component\s*\(\s*{[^}]*tag:\s*'([^']+)'", content)
            tags.extend(found_tags)
    except Exception as e:
        print(f"Error reading file {file_path}: {str(e)}")
    return tags

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
    sort_by = request.GET.get('sort_by', '')
    
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
    
    # Apply sorting
    if sort_by == 'usage_desc':
        tags = tags.order_by('-used_in_website', 'version', 'name')
    elif sort_by == 'usage_asc':
        tags = tags.order_by('used_in_website', 'version', 'name')
    else:
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
        'sort_options': [
            {'value': '', 'label': 'Default'},
            {'value': 'usage_desc', 'label': 'Usage (High to Low)'},
            {'value': 'usage_asc', 'label': 'Usage (Low to High)'}
        ],
        'current_filters': {
            'query': query,
            'version': version_filter,
            'complexity': complexity_filter,
            'theme_type': theme_type_filter,
            'managed_by': managed_by_filter,
            'sort_by': sort_by,
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


def extract_tags_from_tsx(directory, extractor, request):
    """
    Extracts tag names from @Component decorators in .tsx files within a directory.
    :param directory: Directory to scan for .tsx files.
    :param output_json: Path to save the JSON list of tag names.
    """
    
    tag_pattern = re.compile(r"@Component\s*\(\s*\{[^}]*tag:\s*'([^']+)'", re.MULTILINE)

    tsx_count = 0
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith('.tsx'):
                tsx_count += 1
                file_path = os.path.join(root, file)
                print(f"Processing file: {file_path}")
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                        matches = tag_pattern.findall(content)
                        for tag in matches:
                            rel_path = os.path.relpath(file_path, directory)
                            parts = rel_path.split(os.sep)
                            version = getattr(extractor, 'version_value', 'V1')
                            if "packages" in rel_path:
                                theme_type = parts[1] if len(parts) > 1 else ""
                            elif "src/components" in rel_path or "src/pages" in rel_path or "src/events" in rel_path or "src/validation" in rel_path:
                                theme_type = parts[2] if len(parts) > 2 else ""
                            else:
                                theme_type = ""

                            if "helix-web-components" in extractor.repo_url:
                                theme_type = f"helix-web-components>>{theme_type}" if theme_type else theme_type
                            elif "helix-extras" in extractor.repo_url:
                                theme_type = f"helix-extras>>{theme_type}" if theme_type else theme_type
                            
                            try:
                                Tag.objects.get_or_create(
                                    name=tag,
                                    theme_type=theme_type,
                                    defaults={
                                        'path': rel_path,
                                        'details': f'Auto-generated tag for {tag}',
                                        'version': version,
                                        'created_by': request.user,
                                        'updated_by': request.user,
                                        'complexity': 'simple',
                                        'is_managed_by': 'automated',
                                        'tags_extractor_id': extractor.id,
                                        'theme_type': theme_type
                                    }
                                )
                            except Exception as e:
                                print(f"Error creating tag '{tag}': {str(e)}")
                except Exception as e:
                    print(f"Error reading {file_path}: {e}")
    return tsx_count

    # Save tag list to JSON
   
def process_extractor_pages(request, extractor, start_page=1, update_db=True):
    """
    Processes .tsx files for a given TagsExtractor instance from start_page to total_pages.
    If update_db is True, updates start_page and imported fields in the DB.
    
    Supports two extraction methods:
    - GITAPI: Uses GitHub API to retrieve files (default)
    - CLONE: Clones the repository locally and processes files
    
    Returns a tuple: (message, tags_found)
    """
    print("process_extractor_pages")
    print(extractor)
    print("PARAG HERE")
    message = None
    tags_found = []
    owner, repo = None, None
    match = re.match(r'https://github.com/([^/]+)/([^/]+)', extractor.repo_url)
    if not match:
        return 'Invalid GitHub repository URL. Please enter a valid GitHub URL (e.g., https://github.com/username/repository).', []
    
    owner, repo = match.group(1), match.group(2)
    
    # Clean up the repo name by removing any trailing segments
    repo = repo.split('/')[0]

    print(f"NAME {extractor.extraction_method}")

    # If extraction method is CLONE, use the local clone approach directly
    if extractor.extraction_method == 'CLONE':
        print(f"Using local repository clone as requested by extraction_method: {extractor.extraction_method}")
        repo_dir, clone_success, clone_error = clone_github_repo(extractor.repo_url)
        
        if not clone_success:
            return f"Clone failed: {clone_error}", []
        
        # Process the local clone using extract_tags_from_tsx
        
        total_count = extract_tags_from_tsx(repo_dir, extractor, request)
        # shutil.rmtree(repo_dir, ignore_errors=True)

        print(f"Found {total_count} TSX files in repository")
        # Store the total TSX count in the description field temporarily
        tsx_count_info = f"TSX files found: {total_count}"
        extractor.description = tsx_count_info
        print(tsx_count_info)
        extractor.total_pages = 0  # Ensure at least 1 page
        extractor.imported = True
        extractor.save()
        messages.success(request, "Tags extracted successfully from local clone. You can view them below.")
       
        return redirect('tags_extractor_detail', extractor_id=extractor.id)
    
    # Default to GITAPI method (GitHub API)
    # Set up headers for GitHub API
    headers = {}
    if hasattr(settings, 'GITHUB_TOKEN') and settings.GITHUB_TOKEN:
        headers['Authorization'] = f'token {settings.GITHUB_TOKEN}'
    else:
        print("Warning: GitHub token not found in settings. API rate limits will be lower.")
    
    repo_api_url = f'https://api.github.com/repos/{owner}/{repo}'
    print(f"Checking repository: {repo_api_url}")
    try:
        repo_resp = requests.get(repo_api_url, headers=headers, timeout=10)

        print(repo_resp)
        
        if repo_resp.status_code == 404:
            print(f'Repository not found: {owner}/{repo}. Please check if the repository exists and is public.')
            return f'Repository not found: {owner}/{repo}. Please check if the repository exists and is public.', []
        elif repo_resp.status_code == 403:
            print('GitHub API rate limit exceeded. Please try again later or configure a GitHub token.')
            return 'GitHub API rate limit exceeded. Please try again later or configure a GitHub token.', []
        elif repo_resp.status_code != 200:
            error_msg = repo_resp.json().get('message', 'Unknown error') if repo_resp.content else 'Unknown error'
            print(f'Cannot access repository: {error_msg} (Status code: {repo_resp.status_code})')
            return f'Cannot access repository: {error_msg} (Status code: {repo_resp.status_code})', []
    except requests.RequestException as e:
        print(f'Error connecting to GitHub API: {str(e)}')
        return f'Error connecting to GitHub API: {str(e)}', []
    
    print(extractor.total_pages)
    # Get total pages if not set
    if extractor.total_pages == 0:
        try:
            search_url = f'https://api.github.com/search/code?q=repo:{owner}/{repo}+extension:tsx'
            print(f"Searching for TSX files: {search_url}")
            search_resp = requests.get(search_url, headers=headers, timeout=15)
            
            if search_resp.status_code == 200:
                search_json = search_resp.json()
                print(f"GitHub search response: {search_json}")  # Debug: print full response
                total_count = search_json.get('total_count', 0)
                print(f"Found {total_count} TSX files in repository")
                # Store the total TSX count in the description field temporarily
                tsx_count_info = f"TSX files found: {total_count}"
                if extractor.description:
                    if "TSX files found:" not in extractor.description:
                        extractor.description = f"{tsx_count_info}\n{extractor.description}"
                else:
                    extractor.description = tsx_count_info
                
                total_pages = (total_count // PAGINATION_LIMIT) + (1 if total_count % PAGINATION_LIMIT > 0 else 0)
                extractor.total_pages = max(1, total_pages)  # Ensure at least 1 page
                if update_db:
                    extractor.save()
            elif search_resp.status_code == 403:
                return 'GitHub API rate limit exceeded while searching for TSX files. Please try again later.', []
            else:
                error_msg = search_resp.json().get('message', 'Unknown error') if search_resp.content else 'Unknown error'
                return f'Failed to search for TSX files: {error_msg} (Status code: {search_resp.status_code})', []
        except requests.RequestException as e:
            return f'Error while searching for TSX files: {str(e)}', []
    all_items = []
    page = start_page
    processed_page = page - 1
    while page <= extractor.total_pages:
        search_url = f'https://api.github.com/search/code?q=repo:{owner}/{repo}+extension:tsx&per_page={PAGINATION_LIMIT}&page={page}'
        print(f"Processing page {page}/{extractor.total_pages}: {search_url}")
        
        try:
            search_resp = requests.get(search_url, headers=headers, timeout=15)
            
            if search_resp.status_code == 200:
                pass  # Continue with processing
            elif search_resp.status_code == 403:
                message = 'GitHub API rate limit exceeded while fetching TSX files. Please try again later.'
                print(message)
                break
            else:
                error_msg = search_resp.json().get('message', 'Unknown error') if search_resp.content else 'Unknown error'
                message = f'Failed to fetch TSX files: {error_msg} (Status code: {search_resp.status_code})'
                print(message)
                break
        except requests.RequestException as e:
            message = f'Error while fetching TSX files: {str(e)}'
            print(message)
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
    # Extract TSX count from description if available
    tsx_count = None
    if extractor.description and "TSX files found:" in extractor.description:
        match = re.search(r"TSX files found: (\d+)", extractor.description)
        if match:
            tsx_count = int(match.group(1))
    
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

                        rel_path = item['path']
                        parts = rel_path.split(os.sep)
                        version = getattr(extractor, 'version_value', 'V1')
                        # src/components/ms-config-manager/plumbing/helper.spec.tsx
                        
                        if "packages" in rel_path:
                            theme_type = parts[1] if len(parts) > 1 else ""
                        elif "src/components" in rel_path:
                            # version = 'V2'
                            theme_type = parts[2] if len(parts) > 2 else ""
                        else:
                            theme_type = ""
                      

                        if "cdp-lite-theme" in extractor.repo_url:
                            theme_type = f"cdp-lite-theme>>{theme_type}" if theme_type else theme_type
                        elif "hcp-galaxy-theme" in extractor.repo_url:
                            theme_type = f"hcp-galaxy-theme>>{theme_type}" if theme_type else theme_type

                        for tag in tags:
                            try:
                                Tag.objects.get_or_create(
                                    name=tag,
                                    theme_type=theme_type,
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
                            except Exception as e:
                                print(f"Error creating tag '{tag}': {str(e)}")
        if tags_found:
            tsx_count_info = f" from {tsx_count} TSX files" if tsx_count else ""
            message = f"Extracted {len(tags_found)} tags{tsx_count_info}: {', '.join(tags_found)}"
        else:
            tsx_count_info = f"No tags found in {tsx_count} TSX files." if tsx_count else "No tags found in .tsx files."
            message = tsx_count_info
    if update_db:
        extractor.description = message
        extractor.start_page = extractor.total_pages
        extractor.imported = True
        extractor.save()
    print(f"I M HERE {message} >> {tsx_count}")
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
        print(f"Form submitted: {form.is_bound}")
        print(f"Form data: {request.POST}")
        
        if form.is_valid():
            print("Form is valid")
            repo_url = form.cleaned_data['repo_url']
            version_value = form.cleaned_data['version_value']
            extraction_method = form.cleaned_data['extraction_method']
            print(f"Repository URL: {repo_url}")
            print(f"Version: {version_value}")
            print(f"Extraction Method: {extraction_method}")
            
            from .models import TagsExtractor

            if TagsExtractor.objects.filter(repo_url=repo_url).exists():
                message = 'This repository URL already exists as an extractor.'
                print(message)
            else:
                try:
                    # Save without processing
                    extractor = form.save(commit=False)
                    extractor.imported = False
                    # Set default values for total_pages and start_page
                    extractor.total_pages = 0  # Will be auto-detected
                    extractor.start_page = 1
                    extractor.save()
                    print(f"Created extractor with ID: {extractor.id}")
                    
                    # Skip processing and redirect directly to the details page
                    messages.success(request, 'Tags extractor created successfully. Click "Process Pending" to extract tags.')
                    return redirect('tags_extractor_detail', extractor_id=extractor.id)
                except Exception as e:
                    print(f"Error during extractor creation: {str(e)}")
                    message = f"Error creating extractor: {str(e)}"
                    # If we created an extractor but it failed, clean it up
                    TagsExtractor.objects.filter(repo_url=repo_url).delete()
        else:
            print(f"Form is invalid. Errors: {form.errors}")
    else:
        form = TagsExtractorForm()
    return render(request, 'tag_manager_component/tags_extractor_form.html', {
        'form': form, 
        'message': message, 
        'tags_found': tags_found,
        'is_edit': False
    })

# In process_pending_items, call the same function for pending pages
@login_required
def process_pending_items(request, extractor_id):
    if request.user.role not in ['tag_manager', 'admin']:
        return HttpResponse('Unauthorized', status=403)
    
    extractor = get_object_or_404(TagsExtractor, id=extractor_id)
    print(f"Processing extractor: {extractor.repo_url} from page {extractor.start_page}")
    
    # Check if no tags have been extracted yet
    existing_tags = Tag.objects.filter(tags_extractor=extractor).count()
    if existing_tags == 0:
        # If no tags are found, reset start_page to 1 to reprocess from the beginning
        print(f"No tags found, resetting start_page to 1 for complete reprocessing")
        extractor.start_page = 0
        extractor.imported = False
        extractor.save()
    
    # Process the extractor
    result = process_extractor_pages(request, extractor, start_page=extractor.start_page, update_db=True)
    
    if isinstance(result, tuple):
        if len(result) == 2:
            message, tags_found = result
        elif len(result) == 3:
            _, success, error_message = result
            message = error_message if not success else "Processing completed successfully"
    
    # Redirect to the details page instead of the list
    return redirect('tags_extractor_detail', extractor_id=extractor_id)

@login_required
def tags_extractor_edit(request, extractor_id):
    if request.user.role not in ['tag_manager', 'admin']:
        return HttpResponse('Unauthorized', status=403)
    
    extractor = get_object_or_404(TagsExtractor, id=extractor_id)
    
    # Extract TSX count from current description if it exists
    tsx_count_info = None
    if extractor.description:
        match = re.search(r"TSX files found: (\d+)", extractor.description)
        if match:
            tsx_count_info = match.group(0)
    
    if request.method == 'POST':
        form = TagsExtractorForm(request.POST, instance=extractor)
        if form.is_valid():
            repo_url = form.cleaned_data['repo_url']
            # Check if another extractor (not this one) has this URL
            if TagsExtractor.objects.exclude(id=extractor_id).filter(repo_url=repo_url).exists():
                messages.error(request, 'Another extractor with this repository URL already exists.')
                return render(request, 'tag_manager_component/tags_extractor_form.html', {
                    'form': form,
                    'extractor': extractor,
                    'is_edit': True,
                    'message': 'Another extractor with this repository URL already exists.'
                })
            
            # Get the new description from the form
            new_description = form.cleaned_data.get('description', '')
            
            # Preserve TSX count info if it exists
            if tsx_count_info and tsx_count_info not in new_description:
                if new_description:
                    new_description = f"{tsx_count_info}\n{new_description}"
                else:
                    new_description = tsx_count_info
            
            # Save the form with updated description
            extractor = form.save(commit=False)
            extractor.description = new_description
            extractor.save()
            
            messages.success(request, 'Tags extractor updated successfully.')
            return redirect('tags_extractor_detail', extractor_id=extractor_id)
    else:
        # For GET request, if description contains TSX count, separate it from the user description
        initial_description = extractor.description
        if tsx_count_info:
            initial_description = extractor.description.replace(tsx_count_info, '').strip()
            if initial_description.startswith('\n'):
                initial_description = initial_description[1:]
        
        form = TagsExtractorForm(instance=extractor, initial={'description': initial_description})
    
    # Get related tags count
    tags_count = Tag.objects.filter(tags_extractor=extractor).count()
    
    return render(request, 'tag_manager_component/tags_extractor_form.html', {
        'form': form,
        'extractor': extractor,
        'is_edit': True,
        'tsx_count_info': tsx_count_info,
        'tags_count': tags_count,
    })

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
    
    # Extract TSX count from description if available
    tsx_count = None
    if extractor.description:
        match = re.search(r"TSX files found: (\d+)", extractor.description)
        if match:
            tsx_count = int(match.group(1))
    
    # Map internal extraction_method values to display values
    extraction_method_display = 'API' if extractor.extraction_method == 'GITAPI' else 'CLONE'
    
    context = {
        'extractor': extractor,
        'related_tags': related_tags,
        'total_tags': total_tags,
        'completion_percentage': completion_percentage,
        'remaining_pages': remaining_pages,
        'has_pending_pages': extractor.start_page < extractor.total_pages if extractor.total_pages else False,
        'tsx_count': tsx_count,
        'extraction_method': extraction_method_display,
    }
    
    return render(request, 'tag_manager_component/tags_extractor_detail.html', context)

@login_required
def tag_mapper(request):
    if request.user.role not in ['tag_manager', 'admin']:
        return HttpResponse('Unauthorized', status=403)
    
    # Get sort parameter
    sort_by = request.GET.get('sort_by', '')
    
    # Base query for V1 tags
    v1_tags_query = Tag.objects.filter(version='V1')
    
    # Apply sorting
    if sort_by == 'usage_desc':
        v1_tags = v1_tags_query.order_by('-used_in_website', 'name')
    elif sort_by == 'usage_asc':
        v1_tags = v1_tags_query.order_by('used_in_website', 'name')
    else:
        v1_tags = v1_tags_query.order_by('name')

    
        
    v2_tags = Tag.objects.filter(version='V2').order_by('name')
    # Build current mapping: {v1_name: [v2_name, ...]}
    v1_to_v2_map = {}
    for v1 in v1_tags:
        mappings = TagMapper.objects.filter(v1_component_name=v1.name)
        # If no mappings exist, use the tag's own data from Tag
        if not mappings.exists():
            tag_obj = v1
            v1_to_v2_map[v1.name] = [{
            'v2_name': '',  # No mapped V2 name
            'weight': '',   # No weight
            'used_in_website': tag_obj.used_in_website
            }]
            continue
        v1_to_v2_map[v1.name] = [{'v2_name': m.v2_component_name, 'weight': m.weight, 'used_in_website': m.used_in_website} for m in mappings]
    
  
    message = None
    if request.method == 'POST':
        with transaction.atomic():
            for v1 in v1_tags:
                v2_names = request.POST.get(f'v2_component_names_{v1.id}', '').strip()
                weight = request.POST.get(f'weight_{v1.id}', '1')
                
                # Get the used_in_website count from existing mappings before deleting
                existing_usage = 0
                existing_mapping = TagMapper.objects.filter(v1_component_name=v1.name).first()
                if existing_mapping:
                    existing_usage = existing_mapping.used_in_website
                
                # Remove old mappings for this v1
                TagMapper.objects.filter(v1_component_name=v1.name).delete()
                
                if v2_names:
                    for v2_name in [v.strip() for v in v2_names.split(',') if v.strip()]:
                        # Create new mapping with preserved usage count
                        TagMapper.objects.create(
                            v1_component_name=v1.name,
                            v2_component_name=v2_name,
                            weight=int(weight) if weight.isdigit() else 1,
                            used_in_website=existing_usage
                        )
            messages.success(request, 'Mappings updated successfully.')
            return redirect('tag_mapper')
        # Refresh mapping after update
        for v1 in v1_tags:
            mappings = TagMapper.objects.filter(v1_component_name=v1.name)
            v1_to_v2_map[v1.name] = [{'v2_name': m.v2_component_name, 'weight': m.weight, 'used_in_website': m.used_in_website} for m in mappings]
    # Helper for template to get mapping list
    def get_item(d, key):
        return d.get(key, [])
    total_v1_tags = v1_tags.count() 
    total_mappings = sum(len(v) for v in v1_to_v2_map.values())
    pending_mappings = total_v1_tags - len([k for k, v in v1_to_v2_map.items() if v])
    print("v1_to_v2_map")
    print(v1_to_v2_map)
    return render(request, 'tag_manager_component/tag_mapper.html', {
        'v1_tags': v1_tags,
        'v2_tags': v2_tags,
        'v1_to_v2_map': v1_to_v2_map,
        'get_item': get_item,
        'message': message,
        'current_filters': {
            'sort_by': sort_by,
        },
        'sort_options': [
            {'value': '', 'label': 'Default (Name)'},
            {'value': 'usage_desc', 'label': 'Usage (High to Low)'},
            {'value': 'usage_asc', 'label': 'Usage (Low to High)'}
        ],
        'total_v1_tags': total_v1_tags,
        'total_mappings': total_mappings,
        'pending_mappings': pending_mappings
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

    print("GET WEBSITE COMPLEXITY")
    print(site_data)
    print(f"Return config: {return_config}")  # Debug line to see if config is requested
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
        print("CHECKS")
        print(checks)  # Debug line to see the checks being performed
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

 