# Standard library imports
import csv
import json
import logging
import re
import threading
import time
import xml.etree.ElementTree as ET
from urllib.parse import urlparse
import subprocess
import sys
import os
import tempfile
from dotenv import load_dotenv

# Django imports
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.sessions.models import Session
from django.db import models
from django.db.models import Sum, Count, Q
from django.http import HttpResponse, JsonResponse, FileResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt, csrf_protect
from django.db import connection
from django.views.decorators.http import require_POST, require_http_methods, require_GET
import signal
from django.conf import settings

# Third-party imports
import requests
import urllib3
from bs4 import BeautifulSoup

# Project-specific imports
from .models import SiteListDetails, SiteMetaDetails
from .forms import SiteListDetailsForm, SiteMetaDetailsForm
from tag_manager_component.models import Tag, TagMapper
from tag_manager_component.views import get_website_complexity
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv

# Disable SSL warnings for sites with certificate issues
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Load environment variables from .env file
load_dotenv()

username = os.getenv('USERNAME')
password = os.getenv('PASSWORD')
sitename = os.getenv('SITENAME')
instance_id = os.getenv('INSTANCE_ID')

@login_required
def site_list(request):
    """
    Display a list of websites with search and complexity filtering functionality
    """
    query = request.GET.get('search', '').strip()
    complexity = request.GET.get('complexity', '').strip()
    
    # Start with all sites
    sites = SiteListDetails.objects.all()
    
    # Initialize filtered_sites with all sites
    filtered_sites = sites
    
    # Apply search filter if provided
    if query:
        filtered_sites = filtered_sites.filter(website_url__icontains=query)
    
    # Apply complexity filter if provided
    if complexity:
        if complexity == 'unidentified':
            # Handle unidentified sites (empty, null, or not in standard categories)
            filtered_sites = filtered_sites.filter(
                Q(complexity__isnull=True) | 
                Q(complexity='') | 
                ~Q(complexity__in=['simple', 'medium', 'complex'])
            )
        else:
            # Filter by specific complexity
            filtered_sites = filtered_sites.filter(complexity=complexity)
    
    # Order the results
    filtered_sites = filtered_sites.order_by('website_url')
    
    # Count total sites for each complexity
    complexity_counts = {
        'simple': sites.filter(complexity='simple').count(),
        'medium': sites.filter(complexity='medium').count(),
        'complex': sites.filter(complexity='complex').count(),
        'unidentified': sites.filter(
            Q(complexity__isnull=True) | 
            Q(complexity='') | 
            ~Q(complexity__in=['simple', 'medium', 'complex'])
        ).count(),
    }
    
    return render(request, 'site_manager/site_list.html', {
        'sites': sites,
        'filtered_sites': filtered_sites,
        'search': query,
        'complexity': complexity,
        'complexity_counts': complexity_counts,
    })


@login_required
def cleanup_site_data(request):
    """
    Clean all site details and site meta details:
    1. Reset site analysis data (complexity, component counts, etc.)
    2. Delete all site meta details
    3. Mark all sites as not imported
    """
    if request.method == 'POST':
        try:
            # Get counts before cleanup
            sites_count = SiteListDetails.objects.count()
            meta_details_count = SiteMetaDetails.objects.count()
            
            # Step 1: Reset site analysis data
            SiteListDetails.objects.update(
                helix_v1_component=None,
                helix_v2_compatible_component=None,
                helix_v2_non_compatible_component=None,
                custom_component=0,
                v2_compatible_count=0,
                v2_non_compatible_count=0,
                total_pages=0,
                complexity="",
                complexity_configuration=None,
                is_imported=False,
                last_analyzed=None
            )
            
            # Step 2: Delete all site meta details
            SiteMetaDetails.objects.all().delete()
            
            # Log the cleanup
            logger.info(f"Cleaned up {sites_count} sites and deleted {meta_details_count} meta details")
            
            messages.success(
                request, 
                f"Successfully cleaned up {sites_count} sites and deleted {meta_details_count} meta details"
            )
        except Exception as e:
            logger.error(f"Error during cleanup: {str(e)}")
            messages.error(request, f"Error during cleanup: {str(e)}")
            
        return redirect('site_list')
    
    # GET request - show confirmation page
    total_sites = SiteListDetails.objects.count()
    total_meta_details = SiteMetaDetails.objects.count()
    
    return render(request, 'site_manager/cleanup_confirmation.html', {
        'total_sites': total_sites,
        'total_meta_details': total_meta_details,
    })


@login_required
def batch_analyze_sitemaps(request):
    """
    Initiate batch analysis with progress tracking
    """
    logger.info(f"Batch analyze sitemaps called with method: {request.method}")
    
    if request.method == 'POST':
        # Initialize progress in session
        request.session['batch_analysis_progress'] = {
            'status': 'starting',
            'current': 0,
            'total': 0,
            'current_site': '',
            'completed_sites': [],
            'failed_sites': [],
            'start_time': time.time()
        }
        
        # Save session explicitly to ensure it's persisted
        request.session.save()
        
        logger.info(f"Starting batch analysis thread with session key: {request.session.session_key}")
        
        # Start background processing
        thread = threading.Thread(target=process_batch_analysis, args=(request.session.session_key,))
        thread.daemon = True
        thread.start()
        
        return render(request, 'site_manager/batch_analysis_progress.html')
    
    # GET request - show the batch analysis initiation page
    sites = SiteListDetails.objects.filter(is_imported=False)
    
    sites_count = sites.count()
     
    return render(request, 'site_manager/batch_analysis_start.html', {
        'websites': sites,
        'sites_count': sites_count,
    })

@login_required
def batch_analysis_progress(request):
    """
    AJAX endpoint to get current progress
    """
    logger.info(f"Progress check requested with session key: {request.session.session_key}")
    
    # Get progress data from session
    progress_data = request.session.get('batch_analysis_progress', {
        'status': 'not_started',
        'current': 0,
        'total': 0,
        'current_site': '',
        'completed_sites': [],
        'failed_sites': []
    })
    
    logger.info(f"Current progress data: status={progress_data.get('status')}, "
               f"current={progress_data.get('current')}, total={progress_data.get('total')}")
    
    # Calculate percentage
    if progress_data.get('total', 0) > 0:
        percentage = round((progress_data.get('current', 0) / progress_data.get('total')) * 100, 1)
    else:
        percentage = 0
    
    progress_data['percentage'] = percentage
    
    # Calculate elapsed time if started
    if 'start_time' in progress_data and progress_data['start_time']:
        elapsed_time = time.time() - progress_data['start_time']
        progress_data['elapsed_time'] = round(elapsed_time, 1)
        
        # Estimate remaining time
        if progress_data['current'] > 0:
            avg_time_per_site = elapsed_time / progress_data['current']
            remaining_sites = progress_data['total'] - progress_data['current']
            estimated_remaining = avg_time_per_site * remaining_sites
            progress_data['estimated_remaining'] = round(estimated_remaining, 1)
    
    return JsonResponse(progress_data)

def process_batch_analysis(session_key):
    """
    Background process for batch analysis with progress updates
    """
    try:
        logger.info(f"Starting batch analysis process with session key: {session_key}")
        
        # Get session
        session = SessionStore(session_key=session_key)
        if not session:
            logger.error(f"Could not load session with key: {session_key}")
            return
            
        # Get all sites that need analysis
        sites = SiteListDetails.objects.filter(is_imported=False)
        total_sites = sites.count()
        
        logger.info(f"Found {total_sites} sites to analyze")
        
        # Update progress
        progress = session.get('batch_analysis_progress', {})
        progress.update({
            'status': 'processing',
            'total': total_sites,
            'current': 0
        })
        session['batch_analysis_progress'] = progress
        session.save()
        
        logger.info("Updated session with initial progress")
        
        # Get all tag mappings at once to avoid repeated queries
        v1_to_v2_map = {}
        
        # Get all tag mappings efficiently
        all_tag_mappings = TagMapper.objects.all()
        if all_tag_mappings.exists():
            logger.info(f"Found {all_tag_mappings.count()} tag mappings")
            
        # Build mapping dictionary
        for mapping in all_tag_mappings:
            v1_name = mapping.v1_component_name
            if v1_name not in v1_to_v2_map:
                v1_to_v2_map[v1_name] = []
            v1_to_v2_map[v1_name].append({
                'v2_name': mapping.v2_component_name, 
                'weight': mapping.weight
            })
        
        # Sort all mappings by weight in descending order
        for v1_name in v1_to_v2_map:
            v1_to_v2_map[v1_name] = sorted(
                v1_to_v2_map[v1_name], 
                key=lambda x: x['weight'], 
                reverse=True
            )
        
        completed_sites = []
        failed_sites = []
        
        for index, site in enumerate(sites):
            try:
                # Update current site being processed
                progress = session.get('batch_analysis_progress', {})
                progress.update({
                    'current': index,
                    'current_site': site.website_url,
                    'status': 'processing'
                })
                session['batch_analysis_progress'] = progress
                session.save()
                
                # Process the site
                print("Processing site:", site.website_url)
                sitemap_urls = fetch_sitemap_urls(site.website_url)
                if not sitemap_urls:
                    failed_sites.append({'url': site.website_url, 'error': 'No sitemap found'})
                    continue
                
                # Prepare for bulk creation of meta details
                meta_details_to_create = []
                
                for sitemap_url in sitemap_urls:
                    soup, page_source, error = fetch_page(sitemap_url)
                    if error:
                        logger.warning(f"Error fetching {sitemap_url}: {error}")
                        continue
                        
                    custom_elements = find_enhanced_custom_class_elements(soup, "custom-block-element")
                    helix_elements = find_enhanced_helix_elements(soup, page_source)
                    
                    # Process compatible components
                    helix_v2_compatible_component_data = []
                    helix_v2_non_compatible_component_data = []
                    
                    # Process all v1 components at once
                    for v1_component_name in helix_elements:
                        if v1_component_name in v1_to_v2_map and v1_to_v2_map[v1_component_name]:
                            # Get highest weighted v2 component
                            helix_v2_compatible_component_data.append(v1_to_v2_map[v1_component_name][0]['v2_name'])
                        else:
                            # No mapping found
                            helix_v2_non_compatible_component_data.append(v1_component_name)
                    
                    # Create unique, comma-separated strings
                    helix_v1_component_str = ",".join([e for e in set(helix_elements) if e])
                    helix_v2_compatible_component_str = ",".join([e for e in set(helix_v2_compatible_component_data) if e])
                    helix_v2_non_compatible_component_str = ",".join([e for e in set(helix_v2_non_compatible_component_data) if e])
                    custom_component_str = ",".join([e for e in set(custom_elements) if e])
                    
                    # Add to batch for bulk creation
                    meta_details_to_create.append(
                        SiteMetaDetails(
                            site_list_details=site,
                            site_url=sitemap_url,
                            helix_v1_component=helix_v1_component_str,
                            helix_v2_compatible_component=helix_v2_compatible_component_str,
                            helix_v2_non_compatible_component=helix_v2_non_compatible_component_str,
                            custom_component=custom_component_str,
                            v2_compatible_count=len([e for e in helix_v2_compatible_component_data if e]),
                            v2_non_compatible_count=len([e for e in helix_v2_non_compatible_component_data if e]),
                            custom_component_count=len([e for e in custom_elements if e]),
                        )
                    )
                
                # Update site details after analysis
                # Remove duplicates and blank values, store as comma-separated string
                # Bulk create all meta details for this site
                if meta_details_to_create:
                    SiteMetaDetails.objects.bulk_create(meta_details_to_create)
                
                # Use more efficient queries with annotate and aggregate
                site_meta_details = SiteMetaDetails.objects.filter(site_list_details=site)
                
                # Aggregate all unique v1 components
                helix_v1_components_raw = site_meta_details.filter(
                    helix_v1_component__isnull=False
                ).values_list('helix_v1_component', flat=True)

                unique_v1_components = set()
                for value in helix_v1_components_raw:
                    components = [comp.strip() for comp in value.split(',') if comp.strip()]
                    unique_v1_components.update(components)

                site.helix_v1_component = json.dumps(sorted(unique_v1_components))
                
                # Aggregate v2 compatible components
                helix_v2_compatible_raw = site_meta_details.filter(
                    helix_v2_compatible_component__isnull=False
                ).values_list('helix_v2_compatible_component', flat=True)
                
                unique_v2_compatible = set()
                for value in helix_v2_compatible_raw:
                    components = [comp.strip() for comp in value.split(',') if comp.strip()]
                    unique_v2_compatible.update(components)
                
                site.helix_v2_compatible_component = json.dumps(sorted(unique_v2_compatible))
                
                # Aggregate v2 non-compatible components
                helix_v2_non_compatible_raw = site_meta_details.filter(
                    helix_v2_non_compatible_component__isnull=False
                ).values_list('helix_v2_non_compatible_component', flat=True)
                
                unique_v2_non_compatible = set()
                for value in helix_v2_non_compatible_raw:
                    components = [comp.strip() for comp in value.split(',') if comp.strip()]
                    unique_v2_non_compatible.update(components)
                
                site.helix_v2_non_compatible_component = json.dumps(sorted(unique_v2_non_compatible))
                
                # Use single query with aggregation for counts
                aggregated_counts = site_meta_details.aggregate(
                    custom_component_count=Sum('custom_component_count'),
                    v2_compatible_count=Sum('v2_compatible_count'),
                    v2_non_compatible_count=Sum('v2_non_compatible_count'),
                    total_pages=Count('id')
                )
                
                site.custom_component = aggregated_counts['custom_component_count'] or 0
                site.v2_compatible_count = aggregated_counts['v2_compatible_count'] or 0
                site.v2_non_compatible_count = aggregated_counts['v2_non_compatible_count'] or 0
                site.total_pages = aggregated_counts['total_pages']
                
                # Calculate and update complexity based on site data
                try:
                    # Use the pre-calculated set of unique v2 components
                    # Count complexity levels based on V2 component complexity
                    complexity_counts = {
                        'simple': 0,
                        'medium': 0,
                        'complex': 0
                    }
                    
                    # Get all V2 tags with their complexity in a single query
                    v2_tags_complexity = {
                        tag.name: tag.complexity 
                        for tag in Tag.objects.filter(
                            version='V2', 
                            name__in=unique_v2_compatible
                        ).only('name', 'complexity')
                    }
                    
                    # Count components by complexity
                    for component_name in unique_v2_compatible:
                        complexity = v2_tags_complexity.get(component_name)
                        if complexity in complexity_counts:
                            complexity_counts[complexity] += 1
                    
                    # Prepare site data for complexity calculation
                    site_data = {
                        'number_of_pages': site.total_pages,
                        'number_of_helix_v2_compatible': site.v2_compatible_count,
                        'number_of_helix_v2_non_compatible': site.v2_non_compatible_count,
                        'number_of_custom_components': site.custom_component if isinstance(site.custom_component, int) else 0,
                        'total_simple_components': complexity_counts['simple'],
                        'total_medium_components': complexity_counts['medium'],
                        'total_complex_components': complexity_counts['complex'],
                    }
                    
                    # Calculate website complexity
                    complexity_result = get_website_complexity(site_data, return_config=True)
                    
                    if complexity_result and len(complexity_result) == 2:
                        calculated_complexity, config_data = complexity_result
                        
                        if calculated_complexity:
                            site.complexity = calculated_complexity
                            
                            # Store configuration data with audit trail
                            if config_data:
                                full_config_data = {
                                    'configuration_used': config_data,
                                    'site_data_at_calculation': site_data,
                                    'calculation_timestamp': timezone.now().isoformat(),
                                    'complexity_determined': calculated_complexity
                                }
                                site.complexity_configuration = json.dumps(full_config_data)
                            
                            logger.info(f"Updated complexity for {site.website_url}: {calculated_complexity} "
                                        f"(simple: {complexity_counts['simple']}, medium: {complexity_counts['medium']}, "
                                        f"complex: {complexity_counts['complex']})")
                        else:
                            logger.info(f"Could not determine complexity for {site.website_url}, keeping default")
                    else:
                        logger.info(f"Could not determine complexity for {site.website_url}, keeping default")
                
                except Exception as complexity_error:
                    logger.warning(f"Error calculating complexity for {site.website_url}: {complexity_error}")
                
                site.is_imported = True
                site.last_analyzed = timezone.now()
                site.save()
                
                completed_sites.append(site.website_url)
                
            except Exception as e:
                logger.warning(f"Error analyzing site {site.website_url}: {e}")
                failed_sites.append({'url': site.website_url, 'error': str(e)})
            
            # Update progress after each site - refresh session to avoid conflicts
            try:
                # Get a fresh session instance to avoid conflicts
                session = SessionStore(session_key=session_key)
                progress = session.get('batch_analysis_progress', {})
                progress.update({
                    'current': index + 1,
                    'completed_sites': completed_sites,
                    'failed_sites': failed_sites
                })
                session['batch_analysis_progress'] = progress
                session.save()
                logger.info(f"Updated progress: {index + 1}/{total_sites}")
            except Exception as session_err:
                logger.error(f"Error updating session: {session_err}")
        
        # Mark as completed - get fresh session
        try:
            session = SessionStore(session_key=session_key)
            progress = session.get('batch_analysis_progress', {})
            progress.update({
                'status': 'completed',
                'current': total_sites,
                'current_site': '',
                'end_time': time.time()
            })
            session['batch_analysis_progress'] = progress
            session.save()
            logger.info(f"Batch analysis completed for {total_sites} sites")
        except Exception as final_err:
            logger.error(f"Error updating final progress: {final_err}")
        
    except Exception as e:
        logger.error(f"Error in batch analysis process: {e}")
        # Mark as failed
        try:
            session = SessionStore(session_key=session_key)
            progress = session.get('batch_analysis_progress', {})
            progress.update({
                'status': 'failed',
                'error': str(e)
            })
            session['batch_analysis_progress'] = progress
            session.save()
            logger.error(f"Batch analysis failed: {str(e)}")
        except Exception as err:
            logger.error(f"Could not update session with failure status: {err}")


@login_required
def import_websites_csv(request):
    
    if request.method == 'POST' and request.FILES.get('csv_file'):
        csv_file = request.FILES['csv_file']
        decoded_file = csv_file.read().decode('utf-8').splitlines()
        reader = csv.reader(decoded_file)
        count = 0
        rows = list(reader)
        # Validate that the first row is a header with 'website_url'
        if not rows or not rows[0] or rows[0][0].strip().lower() != 'website_url':
            messages.error(request, "CSV header must start with 'website_url'. Please use the provided template.")
            return render(request, 'site_manager/import_websites_csv.html')
        rows = rows[1:]  # Exclude header row
        for row in rows:
            if not row or not row[0].strip() or row[0].strip().startswith('#'):
                continue  # Skip empty or comment lines
            url = row[0].strip()
            if not url.startswith('http://') and not url.startswith('https://'):
                url = 'https://' + url
            print(f"Processing URL: {url}")
            if url and not SiteListDetails.objects.filter(website_url=url).exists():
                SiteListDetails.objects.create(website_url=url)
                count += 1
        messages.success(request, f"Imported {count} websites.")
        return redirect('site_list')
    return render(request, 'site_manager/import_websites_csv.html')

@login_required
def site_create(request):
    if request.method == 'POST':
        form = SiteListDetailsForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Record added successfully.")
            return redirect('site_list')
    else:
        form = SiteListDetailsForm()
    return render(request, 'site_manager/site_form.html', {'form': form})

@login_required
def site_edit(request, pk):
    site = get_object_or_404(SiteListDetails, pk=pk)
    if request.method == 'POST':
        form = SiteListDetailsForm(request.POST, instance=site)
        if form.is_valid():
            form.save()
            messages.success(request, "Record updated successfully.")
            return redirect('site_list')
    else:
        form = SiteListDetailsForm(instance=site)
    return render(request, 'site_manager/site_form.html', {'form': form})

@login_required
def site_delete(request, pk):
    site = get_object_or_404(SiteListDetails, pk=pk)
    if request.method == 'POST':
        site.delete()
        messages.success(request, "Record deleted successfully.")
        return redirect('site_list')
    return render(request, 'site_manager/site_confirm_delete.html', {'site': site})

@login_required
def site_meta_list(request, site_id):
    site = get_object_or_404(SiteListDetails, pk=site_id)
    meta_details = site.meta_details.all()
    return render(request, 'site_manager/site_meta_list.html', {
        'site': site,
        'meta_details': meta_details
    })

@login_required
def site_meta_create(request, site_id):
    site = get_object_or_404(SiteListDetails, pk=site_id)
    if request.method == 'POST':
        form = SiteMetaDetailsForm(request.POST)
        if form.is_valid():
            meta_detail = form.save(commit=False)
            meta_detail.site_list_details = site
            meta_detail.save()
            return redirect('site_meta_list', site_id=site.id)
    else:
        form = SiteMetaDetailsForm()
    return render(request, 'site_manager/site_meta_form.html', {'form': form, 'site': site})

@login_required
def site_meta_edit(request, site_id, pk):
    site = get_object_or_404(SiteListDetails, pk=site_id)
    meta_detail = get_object_or_404(SiteMetaDetails, pk=pk, site_list_details=site)
    if request.method == 'POST':
        form = SiteMetaDetailsForm(request.POST, instance=meta_detail)
        if form.is_valid():
            form.save()
            return redirect('site_meta_list', site_id=site.id)
    else:
        form = SiteMetaDetailsForm(instance=meta_detail)
    return render(request, 'site_manager/site_meta_form.html', {'form': form, 'site': site})

@login_required
def site_meta_delete(request, site_id, pk):
    site = get_object_or_404(SiteListDetails, pk=site_id)
    meta_detail = get_object_or_404(SiteMetaDetails, pk=pk, site_list_details=site)
    if request.method == 'POST':
        meta_detail.delete()
        return redirect('site_meta_list', site_id=site.id)
    return render(request, 'site_manager/site_meta_confirm_delete.html', {'meta_detail': meta_detail, 'site': site})

@login_required
def analyze_sitemap(request, site_id):
    """
    Analyze sitemap URLs for a specific site and create meta details
    """
    # Get the site
    site = get_object_or_404(SiteListDetails, pk=site_id)
    logger.info(f"Starting sitemap analysis for site: {site.website_url}")
    
    # Fetch sitemap URLs
    sitemap_urls = fetch_sitemap_urls(site.website_url)
    
    if not sitemap_urls:
        logger.warning(f"No sitemap URLs found for site: {site.website_url}")
        return render(request, 'site_manager/error.html', {'error': 'No sitemap URLs found.'})

    # Get all tag mappings for efficiency
    v1_to_v2_map = {}
    all_tag_mappings = TagMapper.objects.all()
    for mapping in all_tag_mappings:
        v1_name = mapping.v1_component_name
        if v1_name not in v1_to_v2_map:
            v1_to_v2_map[v1_name] = []
        v1_to_v2_map[v1_name].append({'v2_name': mapping.v2_component_name, 'weight': mapping.weight})
    for v1_name in v1_to_v2_map:
        v1_to_v2_map[v1_name] = sorted(v1_to_v2_map[v1_name], key=lambda x: x['weight'], reverse=True)

    meta_details_to_create = []

    for sitemap_url in sitemap_urls:
        try:
            soup, page_source, error = fetch_page(sitemap_url)
            if error:
                logger.warning(f"Error fetching {sitemap_url}: {error}")
                continue

            custom_elements = find_enhanced_custom_class_elements(soup, "custom-block-element")
            helix_elements = find_enhanced_helix_elements(soup, page_source)

            helix_v2_compatible_component_data = []
            helix_v2_non_compatible_component_data = []

            for v1_component_name in helix_elements:
                if v1_component_name in v1_to_v2_map and v1_to_v2_map[v1_component_name]:
                    helix_v2_compatible_component_data.append(v1_to_v2_map[v1_component_name][0]['v2_name'])
                else:
                    helix_v2_non_compatible_component_data.append(v1_component_name)

            def explode_and_unique_comma_separated(values):
                unique = set()
                for item in values:
                    if item:
                        unique.update([v.strip() for v in item.split(',') if v.strip()])
                return ",".join(sorted(unique))

            meta_details_to_create.append(
                SiteMetaDetails(
                    site_list_details=site,
                    site_url=sitemap_url,
                    helix_v1_component=explode_and_unique_comma_separated([",".join(helix_elements)]),
                    helix_v2_compatible_component=explode_and_unique_comma_separated([",".join([e for e in helix_v2_compatible_component_data if e])]),
                    helix_v2_non_compatible_component=explode_and_unique_comma_separated([",".join([e for e in helix_v2_non_compatible_component_data if e])]),
                    custom_component=explode_and_unique_comma_separated([",".join([e for e in custom_elements if e])]),
                    v2_compatible_count=len([e for e in helix_v2_compatible_component_data if e]),
                    v2_non_compatible_count=len([e for e in helix_v2_non_compatible_component_data if e]),
                    custom_component_count=len([e for e in custom_elements if e]),
                )
            )
        except requests.exceptions.RequestException as e:
            return render(request, 'site_manager/error.html', {'error': str(e)})

    if meta_details_to_create:
        SiteMetaDetails.objects.bulk_create(meta_details_to_create)

    def explode_and_unique_comma_separated_list(values):
        unique = set()
        for item in values:
            if item:
                unique.update([v.strip() for v in item.split(',') if v.strip()])
        return sorted(unique)

    helix_v1_components_raw = SiteMetaDetails.objects.filter(
        site_list_details=site, helix_v1_component__isnull=False
    ).values_list('helix_v1_component', flat=True)
    site.helix_v1_component = json.dumps(explode_and_unique_comma_separated_list(helix_v1_components_raw))

    helix_v2_compatible_raw = SiteMetaDetails.objects.filter(
        site_list_details=site, helix_v2_compatible_component__isnull=False
    ).values_list('helix_v2_compatible_component', flat=True)
    site.helix_v2_compatible_component = json.dumps(explode_and_unique_comma_separated_list(helix_v2_compatible_raw))

    helix_v2_non_compatible_raw = SiteMetaDetails.objects.filter(
        site_list_details=site, helix_v2_non_compatible_component__isnull=False
    ).values_list('helix_v2_non_compatible_component', flat=True)
    site.helix_v2_non_compatible_component = json.dumps(explode_and_unique_comma_separated_list(helix_v2_non_compatible_raw))

    aggregated_counts = SiteMetaDetails.objects.filter(site_list_details=site).aggregate(
        custom_component_count=models.Sum('custom_component_count'),
        v2_compatible_count=models.Sum('v2_compatible_count'),
        v2_non_compatible_count=models.Sum('v2_non_compatible_count'),
        total_pages=models.Count('id')
    )
    site.custom_component = aggregated_counts['custom_component_count'] or 0
    site.v2_compatible_count = aggregated_counts['v2_compatible_count'] or 0
    site.v2_non_compatible_count = aggregated_counts['v2_non_compatible_count'] or 0
    site.total_pages = aggregated_counts['total_pages']

    # Calculate and update complexity based on site data
    try:
        # Aggregate all unique v2 compatible components
        helix_v2_compatible_raw = SiteMetaDetails.objects.filter(
            site_list_details=site, helix_v2_compatible_component__isnull=False
        ).values_list('helix_v2_compatible_component', flat=True)
        unique_v2_compatible = set()
        for value in helix_v2_compatible_raw:
            components = [comp.strip() for comp in value.split(',') if comp.strip()]
            unique_v2_compatible.update(components)

        # Count complexity levels based on V2 component complexity
        complexity_counts = {
            'simple': 0,
            'medium': 0,
            'complex': 0
        }
        v2_tags_complexity = {
            tag.name: tag.complexity
            for tag in Tag.objects.filter(
                version='V2',
                name__in=unique_v2_compatible
            ).only('name', 'complexity')
        }
        for component_name in unique_v2_compatible:
            complexity = v2_tags_complexity.get(component_name)
            if complexity in complexity_counts:
                complexity_counts[complexity] += 1

        site_data = {
            'number_of_pages': site.total_pages,
            'number_of_helix_v2_compatible': site.v2_compatible_count,
            'number_of_helix_v2_non_compatible': site.v2_non_compatible_count,
            'number_of_custom_components': site.custom_component if isinstance(site.custom_component, int) else 0,
            'total_simple_components': complexity_counts['simple'],
            'total_medium_components': complexity_counts['medium'],
            'total_complex_components': complexity_counts['complex'],
        }

        complexity_result = get_website_complexity(site_data, return_config=True)
        if complexity_result and len(complexity_result) == 2:
            calculated_complexity, config_data = complexity_result
            if calculated_complexity:
                site.complexity = calculated_complexity
                if config_data:
                    full_config_data = {
                        'configuration_used': config_data,
                        'site_data_at_calculation': site_data,
                        'calculation_timestamp': timezone.now().isoformat(),
                        'complexity_determined': calculated_complexity
                    }
                    site.complexity_configuration = json.dumps(full_config_data)
    except Exception as complexity_error:
        logger.warning(f"Error calculating complexity for {site.website_url}: {complexity_error}")

    site.is_imported = True
    site.last_analyzed = timezone.now()
    site.save()

    return redirect('site_meta_list', site_id=site.id)


@login_required
def export_sites_csv(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="sites.csv"'

    writer = csv.writer(response)
    # Dynamically fetch all fields from the SiteListDetails model
    fields = [field.name for field in SiteListDetails._meta.fields]
    writer.writerow(fields)

    sites = SiteListDetails.objects.all()
    for site in sites:
        writer.writerow([getattr(site, field) for field in fields])

    return response

@login_required
def download_sites_import_template(request):
    """
    Download a CSV template for importing sites with comprehensive examples.
    """
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="sites_import_template.csv"'
    
    writer = csv.writer(response)
    
    # Write header
    writer.writerow(['website_url'])
    
    # Write sample data with various types of websites
    sample_sites = [
        '# CORPORATE WEBSITES',
        'https://company.com',
        'https://enterprise-corp.net',
        'https://global-solutions.org',
        'https://business-hub.com',
        '',
        '# E-COMMERCE PLATFORMS',
        'https://shop.example.com',
        'https://marketplace.store',
        'https://retail-platform.co',
        'https://online-boutique.net',
        '',
        '# PORTFOLIO/AGENCY SITES',
        'https://design-agency.com',
        'https://creative-studio.io',
        'https://portfolio-site.net',
        'https://digital-agency.co',
        '',
        '# SAAS PLATFORMS',
        'https://app.saas-platform.com',
        'https://dashboard.service.io',
        'https://platform.tech-solution.com',
        'https://cloud.enterprise-app.net',
        '',
        '# EDUCATIONAL/NON-PROFIT',
        'https://university.edu',
        'https://online-learning.org',
        'https://nonprofit-foundation.org',
        'https://research-institute.edu',
        '',
        '# NEWS/MEDIA SITES',
        'https://news-portal.com',
        'https://media-company.net',
        'https://blog-platform.io',
        'https://magazine-site.com',
        '',
        '# INSTRUCTIONS:',
        '# 1. Replace sample URLs with your actual website URLs',
        '# 2. Ensure URLs are properly formatted (include https://)',
        '# 3. Remove all comment lines (starting with #)',
        '# 4. One URL per line in the website_url column',
        '# 5. Save the file and upload it via Import CSV',
    ]
    
    for site in sample_sites:
        if site.startswith('#') or site == '':
            writer.writerow([site])
        else:
            writer.writerow([site])
    
    return response


# Common request headers for all HTTP requests
DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Accept': 'application/xml, text/xml, application/json, text/html, */*',
    'Accept-Language': 'en-US,en;q=0.9,*;q=0.8',
    'Cache-Control': 'no-cache',
    'Connection': 'keep-alive'
}

def fetch_sitemap_urls(base_url):
    """
    Fetch all URLs from sitemap(s) for the given website
    Returns a list of URLs found in sitemaps
    """
    urls_found = []

    try:
        # Common sitemap locations
        sitemap_urls = [f"{base_url}/sitemap.xml"]
        
        # Check robots.txt for sitemap references
        robots_url = f"{base_url}/robots.txt"
        try:
            robots_response = requests.get(
                robots_url, 
                headers=DEFAULT_HEADERS, 
                timeout=10, 
                verify=False
            )
            
            if robots_response.status_code == 200:
                robots_content = robots_response.text
                # Look for sitemap directives
                for line in robots_content.split('\n'):
                    if line.lower().startswith('sitemap:'):
                        sitemap_url = line.split(':', 1)[1].strip()
                        if sitemap_url not in sitemap_urls:
                            sitemap_urls.append(sitemap_url)
                            
        except requests.RequestException as e:
            logger.warning(f"Could not fetch robots.txt from {base_url}: {e}")

        # Process each sitemap URL
        for sitemap_url in sitemap_urls:
            try:
                logger.info(f"Fetching sitemap: {sitemap_url}")
                
                response = requests.get(
                    sitemap_url, 
                    headers=DEFAULT_HEADERS, 
                    timeout=15, 
                    verify=False
                )
                
                if response.status_code == 200:
                    urls_from_sitemap = parse_sitemap(response.content, base_url)
                    urls_found.extend(urls_from_sitemap)
                    logger.info(f"Found {len(urls_from_sitemap)} URLs in {sitemap_url}")
                else:
                    logger.warning(f"Sitemap {sitemap_url} returned status code {response.status_code}")

            except requests.RequestException as e:
                logger.warning(f"Error fetching sitemap {sitemap_url}: {e}")
                continue
        
        # Filter for unique, valid URLs
        valid_urls = list({url for url in urls_found if url.startswith(('http://', 'https://'))})
        
        logger.info(f"Total unique valid URLs found: {len(valid_urls)}")
        return valid_urls

    except Exception as e:
        logger.error(f"Error in sitemap processing for {base_url}: {e}")
        return []


def parse_sitemap(sitemap_content, base_url):
    """
    Parse sitemap XML content and extract URLs
    Handles both regular sitemaps and sitemap index files
    """
    urls = []
    
    try:
        # Decode content if needed
        if isinstance(sitemap_content, bytes):
            try:
                sitemap_content = sitemap_content.decode('utf-8')
            except UnicodeDecodeError:
                sitemap_content = sitemap_content.decode('utf-8', errors='ignore')
        
        # Parse the XML
        root = ET.fromstring(sitemap_content)
        
        # Handle namespaces properly
        namespaces = {}
        # Extract namespace from root element
        if root.tag.startswith('{'):
            namespace_uri = root.tag[1:root.tag.find('}')]
            namespaces['ns'] = namespace_uri
        
        # Use a more consistent approach to find elements with or without namespaces
        def find_elements_with_tag(root, tag_name):
            # Try with namespace
            if namespaces:
                try:
                    return root.findall(f'.//{{*}}{tag_name}')
                except:
                    pass
            
            # Try without namespace
            try:
                return root.findall(f'.//{tag_name}')
            except:
                pass
            
            # Try with local-name function as last resort
            try:
                return root.findall(f'.//*[local-name()="{tag_name}"]')
            except:
                return []
        
        # Check if this is a sitemap index
        sitemap_elements = find_elements_with_tag(root, 'sitemap')
        
        if sitemap_elements:
            logger.info(f"Found sitemap index with {len(sitemap_elements)} sub-sitemaps")
            
            for sitemap_elem in sitemap_elements:
                # Find location element
                loc_elems = find_elements_with_tag(sitemap_elem, 'loc')
                
                if loc_elems and loc_elems[0].text:
                    sub_sitemap_url = loc_elems[0].text.strip()
                    logger.info(f"Processing sub-sitemap: {sub_sitemap_url}")
                    
                    try:
                        # Fetch the sub-sitemap
                        sub_response = requests.get(
                            sub_sitemap_url, 
                            headers=DEFAULT_HEADERS, 
                            timeout=15, 
                            verify=False
                        )
                        
                        if sub_response.status_code == 200:
                            # Process recursively
                            sub_urls = parse_sitemap(sub_response.content, base_url)
                            urls.extend(sub_urls)
                            logger.info(f"Found {len(sub_urls)} URLs in sub-sitemap")
                        else:
                            logger.warning(f"Sub-sitemap returned status {sub_response.status_code}")
                            
                    except requests.RequestException as e:
                        logger.warning(f"Error fetching sub-sitemap: {e}")
        
        # Find URL elements in regular sitemap
        url_elements = find_elements_with_tag(root, 'url')
        
        # Process each URL element
        for url_elem in url_elements:
            loc_elems = find_elements_with_tag(url_elem, 'loc')
            
            if loc_elems and loc_elems[0].text:
                url = loc_elems[0].text.strip()
                
                # Validate URL
                if url and is_valid_url(url, base_url):
                    urls.append(url)
        
        # Return unique URLs
        return list(set(urls))
        
    except ET.ParseError as e:
        logger.warning(f"Error parsing sitemap XML: {e}")
        # Use regex fallback
        return extract_urls_with_regex(sitemap_content, base_url)
    except Exception as e:
        logger.error(f"Unexpected error parsing sitemap: {e}")
        return []


def is_valid_url(url, base_url):
    """
    Validate if URL is properly formatted and belongs to the same domain or subdomain
    """
    if not url or not isinstance(url, str):
        return False
    
    # Basic URL validation
    if not url.startswith(('http://', 'https://')):
        return False
    
    # Parse URLs to compare domains
    try:
        base_parsed = urlparse(base_url)
        url_parsed = urlparse(url)
        
        # Normalize domains (remove www. prefix)
        base_domain = base_parsed.netloc.lower()
        url_domain = url_parsed.netloc.lower()
        
        if base_domain.startswith('www.'):
            base_domain = base_domain[4:]
        if url_domain.startswith('www.'):
            url_domain = url_domain[4:]
        
        # Allow domain or subdomain matches
        return url_domain == base_domain or url_domain.endswith('.' + base_domain)
            
    except Exception as e:
        logger.warning(f"Error validating URL {url}: {e}")
        return False


def extract_urls_with_regex(content, base_url):
    """
    Extract URLs using regex as fallback when XML parsing fails
    """
    urls = []
    
    try:
        # Ensure content is string
        if isinstance(content, bytes):
            content = content.decode('utf-8', errors='ignore')
        
        # Use more comprehensive pattern for different sitemap formats
        loc_patterns = [
            r'<loc[^>]*>(.*?)</loc>',  # Standard format
            r'<link[^>]*>(.*?)</link>', # Alternative format
            r'href=["\']([^"\']+)["\']' # HTML links
        ]
        
        for pattern in loc_patterns:
            matches = re.findall(pattern, content, re.IGNORECASE | re.DOTALL)
            
            for match in matches:
                url = match.strip()
                if is_valid_url(url, base_url):
                    urls.append(url)
        
        logger.info(f"Regex fallback found {len(urls)} URLs")
        
    except Exception as e:
        logger.error(f"Error in regex URL extraction: {e}")
    
    return list(set(urls))  # Return unique URLs


def find_enhanced_custom_class_elements(soup, class_filter="custom-block-element"):
    """
    Find HTML elements with custom block classes
    
    Args:
        soup: BeautifulSoup object representing the parsed HTML
        class_filter: String to filter class names
        
    Returns:
        List of element tag names with the specified class
    """
    # Create a more efficient CSS selector
    class_selector = f'[class*="{class_filter.lower()}"]'
    
    try:
        # Find all elements with the target class in one operation
        elements = soup.select(class_selector)
        
        # Extract tag names
        return [element.name for element in elements if element.name]
    except Exception as e:
        logger.warning(f"Error finding custom elements: {e}")
        return []


def find_enhanced_helix_elements(soup, page_source):
    """
    Find Helix-specific elements in the HTML
    
    Args:
        soup: BeautifulSoup object representing the parsed HTML
        page_source: Raw HTML source (used for regex fallbacks if needed)
        
    Returns:
        List of Helix element names
    """
    try:
        # More efficient selector for helix tags
        helix_elements = set()
        
        # Method 1: Use CSS selector for element names starting with "helix"
        try:
            # Note: Not all parsers support this type of CSS selector
            helix_tags = soup.select('[tag^="helix"], [name^="helix"]')
            for tag in helix_tags:
                if tag.name.startswith('helix'):
                    helix_elements.add(tag.name)
        except:
            pass
            
        # Method 2: Use find_all with lambda (more compatible but slower)
        if not helix_elements:
            helix_tags = soup.find_all(lambda tag: tag.name and tag.name.startswith('helix'))
            for tag in helix_tags:
                helix_elements.add(tag.name)
                
        # Method 3: Regex fallback if needed
        if not helix_elements and page_source:
            import re
            helix_pattern = r'<(helix-[a-zA-Z0-9-]+)'
            matches = re.findall(helix_pattern, page_source)
            helix_elements.update(matches)
            
        return list(helix_elements)
        
    except Exception as e:
        logger.warning(f"Error finding helix elements: {e}")
        return []


def fetch_page(url):
    """
    Fetch webpage content using requests with optimized error handling
    
    Args:
        url: The URL to fetch
        
    Returns:
        tuple: (BeautifulSoup object, page source text, error message)
    """
    try:
        # Use our predefined headers with HTML-specific Accept header
        headers = DEFAULT_HEADERS.copy()
        headers.update({
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Encoding': 'gzip, deflate',
            'Upgrade-Insecure-Requests': '1'
        })
        
        # Set a reasonable timeout to avoid hanging
        response = requests.get(url, headers=headers, timeout=30, verify=False)
        response.raise_for_status()
        
        # Use html.parser for better compatibility and performance
        soup = BeautifulSoup(response.content, 'html.parser')
        return soup, response.text, None
        
    except requests.exceptions.Timeout:
        logger.error(f"Timeout fetching {url}")
        return None, None, "Request timed out"
    except requests.exceptions.TooManyRedirects:
        logger.error(f"Too many redirects for {url}")
        return None, None, "Too many redirects"
    except requests.exceptions.HTTPError as e:
        logger.error(f"HTTP error fetching {url}: {e}")
        return None, None, f"HTTP error: {e}"
    except requests.exceptions.RequestException as e:
        logger.error(f"Request error fetching {url}: {e}")
        return None, None, f"Request error: {e}"
    except Exception as e:
        logger.error(f"Unexpected error fetching {url}: {e}")
        return None, None, f"Unexpected error: {e}"


# Block category keywords for efficient classification
BLOCK_CATEGORIES = {
    'Navigation/Header': ['header', 'navigation', 'menu', 'nav'],
    'Hero/Banner': ['hero', 'banner', 'jumbotron', 'showcase'],
    'Footer': ['footer', 'site-footer', 'page-footer'],
    'Content Block': ['content', 'article', 'post', 'entry'],
    'Sidebar': ['sidebar', 'aside', 'widget-area'],
    'Form Element': ['form', 'input', 'contact', 'subscribe'],
    'Media Block': ['media', 'image', 'video', 'gallery', 'slider'],
    'Card/Tile': ['card', 'tile', 'panel', 'box'],
    'Layout/Grid': ['list', 'grid', 'row', 'column', 'layout']
}

def determine_block_category(element, classes):
    """
    Determine the category of a custom block based on its classes
    
    Args:
        element: HTML element
        classes: List of class names
        
    Returns:
        String representing the category of the block
    """
    class_string = ' '.join(classes).lower() if classes else ''
    
    # Use predefined keywords for more efficient categorization
    for category, keywords in BLOCK_CATEGORIES.items():
        if any(keyword in class_string for keyword in keywords):
            return category
            
    return 'Generic Block'


def generate_enhanced_label(element, classes, helix_children):
    """
    Generate a descriptive label for an HTML block
    
    Args:
        element: HTML element
        classes: List of class names
        helix_children: List of child helix elements
        
    Returns:
        String with formatted description of the element
    """
    if not element:
        return "Unknown Element"
        
    tag = element.name.upper()
    element_id = element.get('id', 'no-id')
    
    # Get a preview of text content
    text_content = element.get_text(strip=True, separator=' ')[:50]
    if len(text_content) > 47:
        text_preview = f" - '{text_content}...'"
    elif text_content:
        text_preview = f" - '{text_content}'"
    else:
        text_preview = " - (no text)"
    
    # Add helix child information if present
    helix_info = ""
    if helix_children:
        # Use set comprehension for efficiency
        helix_types = {child.name for child in helix_children if hasattr(child, 'name')}
        if helix_types:
            helix_info = f" [Contains: {', '.join(sorted(helix_types))}]"
    
    return f"{tag}#{element_id}{text_preview}{helix_info}"


def calculate_content_metrics(element):
    """
    Calculate metrics about the content of an HTML element
    
    Args:
        element: HTML element to analyze
        
    Returns:
        Dictionary of content metrics
    """
    if not element:
        return {}
        
    # Get text content once
    text_content = element.get_text(strip=True, separator=' ')
    word_count = len(text_content.split()) if text_content else 0
    
    # Use CSS selectors for more efficient element finding
    images = element.select('img')
    links = element.select('a')
    form_elements = element.select('form, input, textarea, select')
    
    return {
        'total_text_length': len(text_content),
        'word_count': word_count,
        'image_count': len(images),
        'has_images': bool(images),
        'link_count': len(links),
        'has_links': bool(links),
        'form_element_count': len(form_elements),
        'has_forms': bool(form_elements),
        'nesting_depth': calculate_nesting_depth(element)
    }


def calculate_nesting_depth(element, max_depth=20):
    """
    Calculate the maximum nesting depth of an element with limits
    
    Args:
        element: HTML element to analyze
        max_depth: Maximum depth to check (prevents stack overflow)
        
    Returns:
        Integer representing the maximum nesting depth
    """
    # Use an iterative approach to avoid recursion issues
    if not element or not hasattr(element, 'descendants'):
        return 0
        
    # Map to track depth of each element
    depth_map = {element: 0}
    max_found_depth = 0
    
    # Process each descendant
    for descendant in element.descendants:
        if not hasattr(descendant, 'parent'):
            continue
            
        parent = descendant.parent
        if parent in depth_map:
            current_depth = depth_map[parent] + 1
            depth_map[descendant] = current_depth
            max_found_depth = max(max_found_depth, current_depth)
            
            # Limit maximum depth to prevent performance issues
            if max_found_depth >= max_depth:
                return max_depth
    
    return max_found_depth


def extract_tag_name_from_match(html_match):
    """
    Extract tag name from a regex match string
    
    Args:
        html_match: HTML string containing a tag
        
    Returns:
        String with the extracted tag name
    """
    if not html_match or not isinstance(html_match, str):
        return 'helix-unknown'
        
    match = re.match(r'<(helix-[^>\s]+)', html_match, re.IGNORECASE)
    return match.group(1) if match else 'helix-unknown'


def extract_text_from_helix_match(html_match):
    """
    Extract text content from an HTML string
    
    Args:
        html_match: HTML string
        
    Returns:
        String with extracted text content
    """
    if not html_match or not isinstance(html_match, str):
        return ''
        
    try:
        # Use a lightweight parser for better performance
        soup = BeautifulSoup(html_match, 'html.parser')
        return soup.get_text(strip=True, separator=' ')
    except Exception:
        return ''


@login_required
def batch_update_complexity(request):
    """
    Update complexity for all sites without full analysis
    """
    print("Batch update complexity started")
    if request.method == 'POST':
        # Initialize progress in session
        request.session['batch_complexity_progress'] = {
            'status': 'starting',
            'current': 0,
            'total': 0,
            'current_site': '',
            'updated_sites': [],
            'failed_sites': [],
            'start_time': time.time()
        }
        
        # Start background processing
        thread = threading.Thread(target=process_batch_complexity_update, args=(request.session.session_key,))
        thread.daemon = True
        thread.start()
        
        return render(request, 'site_manager/batch_complexity_progress.html', {
            'is_complexity_only': True
        })
    
    # GET request - show the batch complexity update initiation page
    sites = SiteListDetails.objects.all()
    return render(request, 'site_manager/batch_complexity_start.html', {
        'sites': sites,
        'total_sites': sites.count(),
        'is_complexity_only': True
    })


@login_required
def batch_complexity_progress(request):
    """
    AJAX endpoint to get current complexity update progress
    """
    progress_data = request.session.get('batch_complexity_progress', {
        'status': 'not_started',
        'current': 0,
        'total': 0,
        'current_site': '',
        'updated_sites': [],
        'failed_sites': [],
        'start_time': time.time()
    })
    
    # Calculate elapsed time and estimated remaining time
    if progress_data.get('start_time'):
        elapsed_time = time.time() - progress_data['start_time']
        progress_data['elapsed_time'] = round(elapsed_time, 1)
        
        if progress_data['current'] > 0:
            avg_time_per_site = elapsed_time / progress_data['current']
            remaining_sites = progress_data['total'] - progress_data['current']
            estimated_remaining = avg_time_per_site * remaining_sites
            progress_data['estimated_remaining'] = round(estimated_remaining, 1)
    
    return JsonResponse(progress_data)


def process_batch_complexity_update(session_key):
    """
    Background process for batch complexity update only
    """
    try:
        # Get session
        session = SessionStore(session_key=session_key)
        print("process_batch_complexity_update started")
        # Get all sites
        sites = SiteListDetails.objects.all()
        total_sites = sites.count()
        
        # Update progress
        progress = session.get('batch_complexity_progress', {})
        progress.update({
            'status': 'processing',
            'total': total_sites,
            'current': 0
        })
        session['batch_complexity_progress'] = progress
        session.save()
        
        updated_sites = []
        failed_sites = []
        
        for index, site in enumerate(sites):
            try:
                # Update current site being processed
                progress = session.get('batch_complexity_progress', {})
                progress.update({
                    'current': index,
                    'current_site': site.website_url,
                    'status': 'processing'
                })
                session['batch_complexity_progress'] = progress
                session.save()
                
                # Calculate complexity based on existing site data
                try:
                    # Calculate component complexity counts by analyzing existing components
                    simple_count = 0
                    medium_count = 0
                    complex_count = 0
                    
                    # Get all unique V2 compatible components for this site
                    site_meta_details = SiteMetaDetails.objects.filter(site_list_details=site)
                    all_v2_components = []
                    
                    for meta in site_meta_details:
                        if meta.helix_v2_compatible_component:
                            try:
                                components = json.loads(meta.helix_v2_compatible_component)
                                if isinstance(components, list):
                                    all_v2_components.extend(components)
                            except (json.JSONDecodeError, TypeError):
                                pass
                    
                    # Remove duplicates
                    unique_v2_components = list(set(all_v2_components))
                    
                    # Count complexity levels based on V2 component complexity
                    for component_name in unique_v2_components:
                        tag = Tag.objects.filter(name=component_name, version='V2').first()
                        if tag and tag.complexity:
                            if tag.complexity == 'simple':
                                simple_count += 1
                            elif tag.complexity == 'medium':
                                medium_count += 1
                            elif tag.complexity == 'complex':
                                complex_count += 1
                    
                    site_data = {
                        'number_of_pages': site.total_pages,
                        'number_of_helix_v2_compatible': site.v2_compatible_count,
                        'number_of_helix_v2_non_compatible': site.v2_non_compatible_count,
                        'number_of_custom_components': site.custom_component if isinstance(site.custom_component, int) else 0,
                        'total_simple_components': simple_count,
                        'total_medium_components': medium_count,
                        'total_complex_components': complex_count,
                    }
                    
                    # Get complexity and configuration data
                    complexity_result = get_website_complexity(site_data, return_config=True)
                    if complexity_result and len(complexity_result) == 2:
                        calculated_complexity, config_data = complexity_result
                        
                        if calculated_complexity:
                            old_complexity = site.complexity
                            site.complexity = calculated_complexity
                            
                            # Store the configuration data used for this complexity determination
                            import json
                            if config_data:
                                # Add site data to config for complete audit trail
                                full_config_data = {
                                    'configuration_used': config_data,
                                    'site_data_at_calculation': site_data,
                                    'calculation_timestamp': timezone.now().isoformat(),
                                    'complexity_determined': calculated_complexity
                                }
                                site.complexity_configuration = json.dumps(full_config_data)
                            
                            site.save()
                            
                            updated_sites.append({
                                'url': site.website_url,
                                'old_complexity': old_complexity,
                                'new_complexity': calculated_complexity
                            })
                            print(f"Updated complexity for {site.website_url}: {old_complexity} → {calculated_complexity}")
                            logger.info(f"Updated complexity for {site.website_url}: {old_complexity} → {calculated_complexity}")
                        else:
                            failed_sites.append({'url': site.website_url, 'error': 'Could not determine complexity'})
                    else:
                        failed_sites.append({'url': site.website_url, 'error': 'Could not determine complexity'})
                        
                        
                except Exception as complexity_error:
                    logger.warning(f"Error calculating complexity for {site.website_url}: {complexity_error}")
                    failed_sites.append({'url': site.website_url, 'error': str(complexity_error)})
                
            except Exception as e:
                logger.warning(f"Error processing site {site.website_url}: {e}")
                failed_sites.append({'url': site.website_url, 'error': str(e)})
            
            # Update progress after each site
            progress = session.get('batch_complexity_progress', {})
            progress.update({
                'current': index + 1,
                'updated_sites': updated_sites,
                'failed_sites': failed_sites
            })
            session['batch_complexity_progress'] = progress
            session.save()
        
        # Mark as completed
        progress = session.get('batch_complexity_progress', {})
        progress.update({
            'status': 'completed',
            'current': total_sites,
            'current_site': '',
            'end_time': time.time()
        })
        session['batch_complexity_progress'] = progress
        session.save()
        
    except Exception as e:
        logger.error(f"Error in batch complexity update process: {e}")
        # Mark as failed
        try:
            progress = session.get('batch_complexity_progress', {})
            progress.update({
                'status': 'failed',
                'error': str(e)
            })
            session['batch_complexity_progress'] = progress
            session.save()
        except:
            pass

@login_required
def trigger_webbuilder_site_creation(request, site_id):
    """
    AJAX endpoint to create a webbuilder site via webbuilder_site_creation.py and save the returned site ID.
    """
    if request.method == "POST":
        site = get_object_or_404(SiteListDetails, pk=site_id)
        try:
            # Run the webbuilder_site_creation.py script and capture output
            result = subprocess.run(
                [sys.executable, "site_manager/webbuilder_site_creation.py"], capture_output=True, text=True, check=True
            )
            output = result.stdout.strip().splitlines()
            # Extract the site ID from the URL using regex
            url = output[-1]
            match = re.search(r'/website/(\d+)/', url)
            if match:
                webbuilder_site_id = int(match.group(1))
                site.webbuilder_site_id = webbuilder_site_id
                site.webbuilder_site_url = url  # Save the full URL
                site.save()
                return JsonResponse({"success": True, "site_id": webbuilder_site_id, "site_url": url})
            else:
                return JsonResponse({"success": False, "error": "Site ID not found in URL output: " + url})
        except subprocess.CalledProcessError as e:
            error_message = e.stderr or str(e)
            return JsonResponse({"success": False, "error": error_message})
        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)})
    return JsonResponse({"success": False, "error": "Invalid request"})

def import_webbuilder_config(request, site_id):
    """Handle CSV upload and import webbuilder config for a site using script_import_data.py."""
    if not site_id:
        from django.contrib import messages
        messages.error(request, 'Site ID is missing. Cannot import config.')
        return redirect('site_list')
    if request.method == 'POST' and request.FILES.get('config_file'):
        config_file = request.FILES['config_file']
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False, suffix='.csv') as temp_config:
            for chunk in config_file.chunks():
                temp_config.write(chunk)
            temp_config_path = temp_config.name
        try:
            # Run the import script with the uploaded output.csv
            result = subprocess.run(
                [sys.executable, os.path.join(os.path.dirname(__file__), '../script_import_data.py'), temp_config_path],
                capture_output=True, text=True, check=True
            )
            messages.success(request, 'Import completed successfully.')
        except subprocess.CalledProcessError as e:
            messages.error(request, f'Import failed: {e.stderr or str(e)}')
        except Exception as e:
            messages.error(request, f'Import failed: {str(e)}')
        finally:
            os.unlink(temp_config_path)
        return redirect('site_meta_list', site_id=site.id)
    return render(request, 'site_manager/import_webbuilder_config.html', {'site_id': site_id})

def export_webbuilder_config(request, site_id):
    """Export webbuilder config for a site as CSV by running the export script with uploaded input.csv."""
    if request.method == 'POST' and request.FILES.get('input_csv'):
        input_file = request.FILES['input_csv']
        with tempfile.NamedTemporaryFile(delete=False, suffix='.csv') as temp_input:
            for chunk in input_file.chunks():
                temp_input.write(chunk)
            temp_input_path = temp_input.name
        try:
            # Run the export script with the uploaded input CSV
            result = subprocess.run(
                [sys.executable, os.path.join(os.path.dirname(__file__), '../script_to_export.py'), temp_input_path],
                capture_output=True, text=True, check=True
            )
            output_lines = result.stdout.strip().splitlines()
            # The script should print the output CSV path as the last line
            output_csv_path = output_lines[-1]
            abs_output_csv_path = os.path.abspath(output_csv_path)
            if not os.path.exists(abs_output_csv_path):
                return HttpResponse('Export failed: output.csv not found.', status=500)
            with open(abs_output_csv_path, 'rb') as f:
                response = HttpResponse(f.read(), content_type='text/csv')
                response['Content-Disposition'] = 'attachment; filename="output.csv"'
                return response
        except subprocess.CalledProcessError as e:
            return HttpResponse(f'Export failed: {e.stderr or str(e)}', status=500)
        except Exception as e:
            return HttpResponse(f'Export failed: {str(e)}', status=500)
        finally:
            os.unlink(temp_input_path)
    return HttpResponse('No file uploaded.', status=400)

@login_required
def export_site_meta(request, site_id):
    """
    Accepts v1_site_id and v2_site_id from POST, writes to input.csv, and triggers script_to_export.py asynchronously.
    Stores PID and status in a status file for progress tracking and cancellation.
    """
    v1_site_id = request.POST.get('v1_site_id')
    v2_site_id = request.POST.get('v2_site_id')
    if not v1_site_id or not v2_site_id:
        return JsonResponse({'success': False, 'error': 'Both v1_site_id and v2_site_id are required.'})
    input_csv_path = os.path.join(settings.BASE_DIR, 'input.csv')
    status_file = os.path.join(settings.BASE_DIR, f"site_{site_id}_meta_export.status")
    try:
        with open(input_csv_path, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(['v1_site_id', 'v2_site_id'])
            writer.writerow([v1_site_id, v2_site_id])
    except Exception as e:
        return JsonResponse({'success': False, 'error': f'Failed to write CSV: {e}'})
    script_path = os.path.join(settings.BASE_DIR, 'script_to_export.py')
    # Start the export script asynchronously
    try:
        process = subprocess.Popen(['python3', script_path, str(site_id)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        # Write PID and initial status to status file
        with open(status_file, 'w') as f:
            f.write(json.dumps({'pid': process.pid, 'status': 'running', 'progress': 0}))
    except Exception as e:
        return JsonResponse({'success': False, 'error': f'Failed to start export: {e}'})
    return JsonResponse({'success': True, 'message': 'Export started.'})

@login_required
def check_export_status(request, site_id):
    """
    Check the status of the export process for a given site_id.
    Returns JSON: {"ready": bool, "status": str, "progress": int, "running": bool}
    """
    output_file = os.path.join(settings.BASE_DIR, f"site_{site_id}_meta_export.csv")
    status_file = os.path.join(settings.BASE_DIR, f"site_{site_id}_meta_export.status")
    status = 'not_started'
    progress = 0
    running = False
    if os.path.exists(status_file):
        with open(status_file, 'r') as f:
            try:
                status_data = json.load(f)
                status = status_data.get('status', 'not_started')
                progress = status_data.get('progress', 0)
                pid = status_data.get('pid')
                if pid:
                    # Check if process is still running
                    try:
                        os.kill(pid, 0)
                        running = True
                    except OSError:
                        running = False
            except Exception:
                pass
    is_ready = os.path.exists(output_file)
    return JsonResponse({'ready': is_ready, 'status': status, 'progress': progress, 'running': running})

@login_required
@require_POST
def cancel_export(request, site_id):
    """
    Cancel the export process for a given site_id by killing the process and updating the status file.
    """
    status_file = os.path.join(settings.BASE_DIR, f"site_{site_id}_meta_export.status")
    if not os.path.exists(status_file):
        return JsonResponse({'success': False, 'error': 'No export process found.'})
    try:
        with open(status_file, 'r') as f:
            status_data = json.load(f)
        pid = status_data.get('pid')
        if pid:
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass  # Process may have already exited
        # Update status file
        status_data['status'] = 'cancelled'
        status_data['progress'] = 0
        with open(status_file, 'w') as f:
            json.dump(status_data, f)
        return JsonResponse({'success': True, 'message': 'Export cancelled.'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
def export_meta_page(request, site_id):
    """
    Render the export meta page for a given site_id.
    """
    from django.urls import reverse
    import os
    export_ready = False
    download_url = None
    output_file = os.path.join(settings.BASE_DIR, f"site_{site_id}_meta_export.csv")
    if os.path.exists(output_file):
        export_ready = True
        download_url = reverse('download_exported_meta', args=[site_id])
    return render(request, 'site_manager/export_meta.html', {
        'site_id': site_id,
        'export_ready': export_ready,
        'download_url': download_url,
    })

@login_required
def import_site_meta(request, site_id):
    """
    Accepts a POST request with a CSV file and processes it for meta import for the given site_id.
    Now runs the import in the background and returns immediately.
    """
    import tempfile
    from django.contrib import messages
    status_file = os.path.join(settings.BASE_DIR, f"site_{site_id}_meta_import.status")
    if request.method == 'POST' and request.FILES.get('import_file'):
        import_file = request.FILES['import_file']
        with tempfile.NamedTemporaryFile(delete=False, suffix='.csv') as temp_file:
            for chunk in import_file.chunks():
                temp_file.write(chunk)
            temp_file_path = temp_file.name
        # Start background thread
        thread = threading.Thread(target=run_import_script_in_background, args=(site_id, temp_file_path, status_file))
        thread.daemon = True
        thread.start()
        response_data = {'success': True, 'message': 'Import started. You can check the status below.'}
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            from django.http import JsonResponse
            return JsonResponse(response_data)
        messages.info(request, 'Import started. You can check the status below.')
        return redirect('export_meta_page', site_id=site_id)
    return render(request, 'site_manager/import_meta.html', {'site_id': site_id})

def run_import_script_in_background(site_id, temp_file_path, status_file):
    try:
        script_path = os.path.join(settings.BASE_DIR, 'script_import_data.py')
        # Write status: running
        with open(status_file, 'w') as f:
            f.write(json.dumps({'status': 'running', 'message': 'Import in progress...'}))
        result = subprocess.run(['python3', script_path, temp_file_path], capture_output=True, text=True)
        if result.returncode == 0:
            status = {'status': 'completed', 'message': 'Import completed successfully.'}
        else:
            status = {'status': 'failed', 'message': result.stderr or 'Import failed.'}
        with open(status_file, 'w') as f:
            f.write(json.dumps(status))
    except Exception as e:
        with open(status_file, 'w') as f:
            f.write(json.dumps({'status': 'failed', 'message': str(e)}))
    finally:
        os.unlink(temp_file_path)

@login_required
def check_import_status(request, site_id):
    """
    Check the status of the import process for a given site_id.
    Returns JSON: {"status": str, "message": str}
    """
    status_file = os.path.join(settings.BASE_DIR, f"site_{site_id}_meta_import.status")
    status = {'status': 'not_started', 'message': 'No import in progress.'}
    if os.path.exists(status_file):
        with open(status_file, 'r') as f:
            try:
                status = json.load(f)
            except Exception:
                pass
    return JsonResponse(status)

@login_required
def download_exported_meta(request, site_id):
    """
    Serve the exported meta CSV file for download for the given site_id.
    """
    import os
    from django.http import FileResponse, Http404
    output_file = os.path.join(settings.BASE_DIR, f"site_{site_id}_meta_export.csv")
    if not os.path.exists(output_file):
        raise Http404("Exported file not found.")
    response = FileResponse(open(output_file, 'rb'), as_attachment=True, filename=f"site_{site_id}_meta_export.csv")
    return response


"""
    Block Import Functionality
    1. def import_block() --> For the UI of the Button
    2. def run_import_block() --> For initiating the function
    3. def process_blocks() & create_block() --> Used to add the conditions for various blocks
"""

@login_required
def import_block(request, site_id):
    """
    View to handle block import for a given site.
    """
    if request.method == 'POST':
        # Start the import in a background thread
        threading.Thread(target=run_import_block, args=(site_id,)).start()
        return JsonResponse({'status': 'started', 'message': 'Block import is in progress.'})
    return render(request, 'site_manager/import_block.html', {'site_id': site_id})


def run_import_block(site_id):
    site = get_object_or_404(SiteListDetails, pk=site_id)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        csv_filename = f"v2_{instance_id}_duplicate_blocks_list.csv"

        # Create the CSV file once if it doesn't exist
        # CSV File is for noting the Duplicate Files
        if not os.path.exists(csv_filename):
            with open(csv_filename, mode='w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(["Duplicate Block Name"])  # Header row

        # Go to dashboard
        page.goto("https://webbuilder.pfizer/webbuilder/dashboard")

        # Click the Webbuilder Login button
        page.click('xpath=//*[@id="app"]/div[1]/div[1]/div[1]/div/div[2]/a')
        page.wait_for_load_state("networkidle")

        # Fill in login credentials
        if page.locator('xpath=//*[@id="username"]').is_visible():
            page.fill('xpath=//*[@id="username"]', username)
            page.fill('xpath=//*[@id="password"]', password)
            page.press('xpath=//*[@id="password"]', "Enter")

        # Call the main processing functions in synchronous order
        process_blocks(page, sitename, instance_id,
                       blocks_folder=os.path.join(settings.BASE_DIR, 'site_manager', 'static', 'block_import',
                       'data','modules'))

        browser.close()


def create_block(page, b_title, b_description, b_category, b_protected, b_files, b_auto_attach, b_auto_attach_location,
                 b_auto_attach_exceptions, b_auto_attach_to_error_pages, b_css, b_html):
    # Fill title
    b_title_field = page.locator(
        'xpath=//*[@id="webbuilder-editor-content-wrapper"]/div/div[1]/div/div/div[3]/div/div[2]/div/div[1]/div[2]/div[1]/div[1]/input')
    b_title_field.click()
    page.keyboard.press("Control+A")
    b_title_field.fill(b_title)
    page.wait_for_timeout(1000)

    # Fill Description
    b_description_field = page.locator(
        'xpath=//*[@id="webbuilder-editor-content-wrapper"]/div/div[1]/div/div/div[3]/div/div[2]/div/div[1]/div[2]/div[1]/div[2]/input')
    b_description_field.click()
    page.keyboard.press("Control+A")
    b_description_field.fill(b_description)
    page.wait_for_timeout(1000)

    # Fill category
    page.locator(
        'xpath=//*[@id="webbuilder-editor-content-wrapper"]/div/div[1]/div/div/div[3]/div/div[2]/div/div[1]/div[2]/div[1]/div[3]/div/div[2]').click()
    b_category_field = page.locator(
        'xpath=//*[@id="webbuilder-editor-content-wrapper"]/div/div[1]/div/div/div[3]/div/div[2]/div/div[1]/div[2]/div[1]/div[3]/div/div[2]/input')
    b_category_field.fill(b_category)
    page.keyboard.press("Enter")
    page.wait_for_timeout(1000)

    # If protected, perform extended logic
    if b_protected:
        page.locator(
            'xpath=//*[@id="webbuilder-editor-content-wrapper"]/div/div[1]/div/div/div[3]/div/div[2]/div/div[1]/div[2]/div[2]/div/label/input').click()
        page.wait_for_timeout(1000)

        if isinstance(b_files, list) and b_files:
            for file_value in b_files:
                page.locator(
                    'xpath=//*[@id="webbuilder-editor-content-wrapper"]/div/div[1]/div/div/div[3]/div/div[2]/div/div[1]/section/section/div/div[3]').click()
                file_input = page.locator(
                    'xpath=//*[@id="webbuilder-editor-content-wrapper"]/div/div[1]/div/div/div[3]/div/div[2]/div/div[1]/section/section/div/div[3]/input')
                file_input.fill(file_value)
                page.keyboard.press("Enter")
                page.wait_for_timeout(1000)

        if b_auto_attach:
            page.locator(
                'xpath=//*[@id="webbuilder-editor-content-wrapper"]/div/div[1]/div/div/div[3]/div/div[2]/div/div[1]/div[2]/div[2]/div[2]/label/input').click()
            page.wait_for_timeout(1000)

            if b_auto_attach_location:
                location_select = page.locator(
                    'xpath=//*[@id="webbuilder-editor-content-wrapper"]/div/div[1]/div/div/div[3]/div/div[2]/div/div[1]/div[2]/div[2]/div[3]/select')
                options = location_select.locator('option').all()
                for option in options:
                    option_text = option.text_content()
                    if option_text.strip() == b_auto_attach_location.strip():
                        option.click()
                        page.wait_for_timeout(1000)
                        break

            if isinstance(b_auto_attach_exceptions, list) and b_auto_attach_exceptions:
                exception_container = page.locator(
                    'xpath=//*[@id="webbuilder-editor-content-wrapper"]/div/div[1]/div/div/div[3]/div/div[2]/div/div[1]/div[2]/div[2]/div[4]/div/div[2]')
                page.wait_for_timeout(1000)
                for exception in b_auto_attach_exceptions:
                    exception_container.click()
                    exception_input = page.locator(
                        'xpath=//*[@id="webbuilder-editor-content-wrapper"]/div/div[1]/div/div/div[3]/div/div[2]/div/div[1]/div[2]/div[2]/div[4]/div/div[2]/input')
                    exception_input.fill(exception)
                    page.keyboard.press("Enter")
                    page.wait_for_timeout(1000)

        if b_auto_attach_to_error_pages:
            page.locator('xpath=b_auto_attach_to_error_pages').click()
            page.wait_for_timeout(1000)

    # Proceed with block import
    # import_btn = page.locator('.fa-download')
    import_btn = page.locator('[data-tooltip="Import"]')
    import_btn.click()  # click import button
    page.wait_for_timeout(1000)
    text_field = page.locator('xpath=//*[@id="gjs-mdl-c"]/div/div/div[6]/div[1]/div/div/div/div[5]/div/pre')
    text_field.click()  # click the text area
    page.wait_for_timeout(1000)
    text_fill = page.locator('xpath=//*[@id="gjs-mdl-c"]/div/div/div[1]/textarea')
    text_fill.fill(b_html + "\n" + "<style>\n" + b_css + "\n</style>")  # fill the text area
    page.wait_for_timeout(2000)
    page.locator('.gjs-btn-import').click()  # click import save button
    page.wait_for_timeout(1000)
    page.locator('xpath=//*[@id="wrapper"]/nav/div[2]/div[1]/div[2]/div/div/button[1]').click()  # click the save button
    page.wait_for_timeout(4000)
    page.locator('.btn-back-tiered-menu ').click()  # click back button
    page.wait_for_timeout(5000)

def process_blocks(page, sitename, instance_id, blocks_folder):
    page.goto(f"https://{sitename}/builder/website/{instance_id}?panel=left-sidebar-settings--elements")
    page.wait_for_timeout(10000)

    skipped_csv = f"v2_{instance_id}_skipped_blocks.csv"

    for block_name in os.listdir(blocks_folder):
        # if block_name.endswith(".json"):
        if not block_name.endswith(".json") or block_name.startswith("processed_"):
            continue
        
        else:
            block_path = os.path.join(blocks_folder, block_name)
            with open(block_path, "r", encoding="utf-8") as f:
                block_data = json.load(f)
                f.close()

                # Skip if the entire document is an empty array
                if isinstance(block_data, list) and len(block_data) == 0:
                    print(f"Skipping empty array JSON file: {block_name}")
                    print("xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")

                    # After successful processing, rename the file
                    new_block_name = f"processed_{block_name}"
                    new_block_path = os.path.join(blocks_folder, new_block_name)
                    os.rename(block_path, new_block_path)

                    continue

                else:
                    try:
                        print(f"Reading JSON File : '{block_name}")

                        # Safely extract storage and settings dictionaries
                        storage = block_data.get("storage", {})
                        settings = block_data.get("settings", {})
                        settings_settings = settings.get("settings", {}) if isinstance(settings.get("settings", {}), dict) else {}

                        # Safely extract values from settings and settings.settings
                        b_title = settings.get("title", "") if isinstance(settings, dict) else ""
                        b_description = settings_settings.get("description", "") if isinstance(settings_settings, dict) else ""
                        b_deleted_by = settings_settings.get("deleted_by", "") if isinstance(settings_settings, dict) else ""
                        b_category = settings.get("category", "") if isinstance(settings, dict) else ""
                        b_protected = settings.get("protected", "") if isinstance(settings, dict) else ""
                        b_files = settings.get("files", []) if isinstance(settings, dict) else []
                        b_auto_attach = settings_settings.get("auto_attach", False) if isinstance(settings_settings, dict) else False
                        b_auto_attach_location = settings_settings.get("auto_attach_location", "") if isinstance(settings_settings, dict) else ""
                        b_auto_attach_exceptions = settings_settings.get("auto_attach_exceptions", []) if isinstance(settings_settings, dict) else []
                        b_auto_attach_to_error_pages = settings_settings.get("auto_attach_to_error_pages", False) if isinstance(settings_settings, dict) else False

                        # Safely extract values from storage.data
                        if isinstance(storage, dict):
                            data = storage.get("data", {})
                            if isinstance(data, dict):
                                b_css = data.get("css", "")
                                b_html = data.get("html", "")
                            else:
                                b_css = ""
                                b_html = ""
                        else:
                            b_css = ""
                            b_html = ""
                        #Adding logic to migrate v1 HTML/CSS components to v2.
                        payload = {
                            'v1_body': b_html,
                            'v1_css': b_css,
                            'v1_js': ''
                        }

                        api_url = os.getenv('API_URL')
                        bearer_token = os.getenv('BEARER_TOKEN')
                        headers = {
                            'Authorization': f'Bearer {bearer_token}',
                            'Content-Type': 'application/json'
                        }

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
                            b_html = data.get('v2_body', '')
                            b_css = data.get('v2_css', '')
                            b_js = data.get('v2_js', '')

                        if not b_deleted_by:
                            print(f"found block : {b_title} at JSON {block_name}")

                            add_block_button = page.locator('xpath=//*[@id="webbuilder-modal-block-list"]/div/div/div/div[1]/div[2]/a')
                            fresh_site_button = page.locator('xpath=//*[@id="webbuilder-modal-block-list"]/div/div/div/a')

                            if add_block_button.is_visible() and not b_deleted_by:
                                add_block_button.click()
                                print("Clicked Add block list button.")
                                page.wait_for_timeout(1000)
                                create_block(page, b_title, b_description, b_category, b_protected, b_files, b_auto_attach, b_auto_attach_location, b_auto_attach_exceptions, b_auto_attach_to_error_pages, b_css, b_html)
                                print(f"'{b_title} Created for the JSON File '{block_name}'")
                                print("========================================")

                                # After successful processing, rename the file
                                new_block_name = f"processed_{block_name}"
                                new_block_path = os.path.join(blocks_folder, new_block_name)
                                os.rename(block_path, new_block_path)

                            elif fresh_site_button.is_visible() and not b_deleted_by:
                                fresh_site_button.click()
                                print("Clicked New site block list button.")
                                page.wait_for_timeout(1000)
                                create_block(page, b_title, b_description, b_category, b_protected, b_files, b_auto_attach, b_auto_attach_location, b_auto_attach_exceptions, b_auto_attach_to_error_pages, b_css, b_html)
                                print(f"'{b_title} Created for the JSON File '{block_name}'")
                                print("========================================")

                                # After successful processing, rename the file
                                new_block_name = f"processed_{block_name}"
                                new_block_path = os.path.join(blocks_folder, new_block_name)
                                os.rename(block_path, new_block_path)
                            else:
                                print("Neither block list button was found.")
                                print(f"'{b_title}' Skipped the JSON File '{block_name}'")
                                print("xxx---xxxx---xxx---xxx---xxx---xxx---xxx")

                                file_exists = os.path.isfile(skipped_csv)
                                with open(skipped_csv, mode='a', newline='', encoding='utf-8') as csvfile:
                                    writer = csv.writer(csvfile)
                                    if not file_exists:
                                        writer.writerow(["Block Title", "Block JSON", "Error Message"])
                                    writer.writerow([b_title, block_name, "Check the Block Individually"])

                                # After successful processing, rename the file
                                new_block_name = f"processed_{block_name}"
                                new_block_path = os.path.join(blocks_folder, new_block_name)
                                os.rename(block_path, new_block_path)

                        elif b_deleted_by:
                            file_exists = os.path.isfile(skipped_csv)
                            with open(skipped_csv, mode='a', newline='', encoding='utf-8') as csvfile:
                                writer = csv.writer(csvfile)
                                if not file_exists:
                                    writer.writerow(["Block Title", "Block JSON", "Error Message"])
                                writer.writerow([b_title, block_name, "Deleted by : " + b_deleted_by])

                            # After successful processing, rename the file
                            new_block_name = f"processed_{block_name}"
                            new_block_path = os.path.join(blocks_folder, new_block_name)
                            os.rename(block_path, new_block_path)

                            continue


                    except KeyError:
                        print(f"Certain Field Not Found : '{block_name}'")


"""
    Files Import Functionality
    1. def import_file_attribute() --> For the UI of the Button
    2. def run_import_file_attribute() --> For initiating the function
    3. def process_files() --> Used to add the conditions for various files
"""

@login_required
def import_file_attribute(request, site_id):
    """
    Trigger file attribute import automation for a site. No file upload required.
    Shows only an Import button and triggers the process on submit.
    """
    site = get_object_or_404(SiteListDetails, pk=site_id)
    if request.method == 'POST':
        threading.Thread(target=run_import_file_attribute, args=(site,)).start()
        messages.info(request, 'File attribute import started. You can navigate away; the process will continue in the background.')
    return render(request, 'site_manager/import_file_attribute.html', {'site': site})


def run_import_file_attribute(site_id):
    # Optionally: fetch site-specific info from DB if needed

    files_folder = os.path.join(settings.BASE_DIR, 'site_manager', 'static', 'block_import', 'data',
                                'files')
    pages_folder = os.path.join(settings.BASE_DIR, 'site_manager', 'static', 'block_import', 'data',
                                'pages')

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)  # Show browser window
            page = browser.new_page()

            # Login steps
            page.goto("https://webbuilder.pfizer/webbuilder/dashboard")

            # Click the Webbuilder Login button
            page.click('xpath=//*[@id="app"]/div[1]/div[1]/div[1]/div/div[2]/a')
            page.wait_for_load_state("networkidle")

            if page.locator('xpath=//*[@id="username"]').is_visible():
                page.fill('xpath=//*[@id="username"]', username)
                page.fill('xpath=//*[@id="password"]', password)
                page.press('xpath=//*[@id="password"]', "Enter")
            page.wait_for_timeout(2000)

            process_files(page, sitename, instance_id, files_folder, pages_folder)

            browser.close()

    except Exception as e:
        logging.error(f"Error in run_import_file_attribute: {e}")

def process_files(page, sitename, instance_id, files_folder, pages_folder):
    # Navigate to Content > Files
    page.goto(f"https://{sitename}/builder/website/{instance_id}?panel=left-sidebar-settings--file-manager")
    page.wait_for_timeout(5000)

    skipped_file_csv = f"v2_{instance_id}_skipped_files.csv"
    duplicate_file_csv = f"v2_{instance_id}_duplicate_files_list.csv"

    all_files = [f for f in os.listdir(files_folder) if f.endswith(".json") and not f.startswith("processed_")]
    files_count = len(all_files)

    # If more than 50 files, divide into batches
    batch_size = 50
    batches = [all_files[i:i + batch_size] for i in range(0, files_count, batch_size)]

    for batch_index, batch_files in enumerate(batches):
        print(f"Processing batch {batch_index + 1} of {len(batches)}")

        for file_name in batch_files:
            print(f"Remianing Files to Scan : {files_count}")
            files_count -= 1
            file_found = 0

            file_path = os.path.join(files_folder, file_name)
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            f_name = ""
            f_path = ""
            f_url = ""
            f_category = ""
            f_only_on_deploy = ""
            f_deploy_on = ""
            f_weight = ""
            f_pages = []
            f_private = ""
            f_footer = ""
            f_header = ""
            f_async = ""
            f_modular = ""
            f_deleted_at = ""

            index = 0 # needed for multiple entries in search result

            f_name = data["details"]["filename"]
            f_path = data["details"]["filepath"]
            f_url = data["details"]["url"]
            f_only_on_deploy = data["details"]["only_on_deployment"]
            f_deploy_on = data["details"]["deploy_on"]
            f_category = data["details"]["category"]
            f_weight = data["details"]["weight"]
            f_pages = data["details"]["pages"]
            f_private = data["details"]["private"]
            f_footer = data["details"]["footer_file"]
            f_header = data["details"]["header_file"]
            f_async = data["details"]["async"]
            f_modular = data["details"]["modular"]

            # Convert the Variables to String
            f_path_str = str(f_path)
            f_url_str = str(f_url)
            f_only_on_deploy_str = str(f_only_on_deploy)
            f_deploy_on_str = str(f_deploy_on)
            f_category_str = str(f_category)
            f_weight_str = str(f_weight)
            f_private_str = str(f_private)
            f_footer_str = str(f_footer)
            f_header_str = str(f_header)

            print(f"File is : '{f_name}' for JSON file '{file_name}'")

            # Search for file name
            search_box = page.locator('xpath=//*[@id="file-search-text-input"]')
            search_box.click()
            page.keyboard.press("Control+A")
            search_box.fill(f_name)
            search_box.press("Enter")
            page.wait_for_timeout(3000)

            # Check if file name appears in page
            file_visible = page.locator(f"text={f_name}")
            file_visible_count = file_visible.count()
            if file_visible_count > 1:
                print(f"Duplicate File Name : '{f_name}' is DUPLICATE hence SKIPPING !!")

                if not os.path.exists(duplicate_file_csv):
                    with open(duplicate_file_csv, mode='w', newline='', encoding='utf-8') as csvfile:
                        writer = csv.writer(csvfile)
                        writer.writerow(["Duplicate File Name"])  # Header row

                with open(duplicate_file_csv, mode='a', newline='', encoding='utf-8') as csvfile:
                    writer = csv.writer(csvfile)
                    writer.writerow([f_name])

                new_file_name = f"processed_{file_name}"
                new_file_path = os.path.join(files_folder, new_file_name)
                os.rename(file_path, new_file_path)

            else:
                if page.locator(f"text={f_name}").is_visible():
                    rows = page.query_selector_all('table[data-v-c28095ba] tbody tr')

                    # Scan each row for the exact value from Table
                    for i, row in enumerate(rows):
                        first_column = row.query_selector("td:nth-child(1)")
                        if first_column.inner_text().strip() == f_name:
                            index = i + 1
                            file_found = 1
                            break
                        elif i+1 == len(rows):
                            file_found = 0

                    if file_found == 1:
                        print(f"File Name '{f_name}' FOUND !!!! at Index {index}")

                        # Click edit icon of File
                        page.locator(f'xpath=//*[@id="webbuilder-editor-content-wrapper"]/div/div[1]/div/div/div[3]/div[2]/div/div/div[2]/table/tbody/tr[{index}]/td[7]/div/span[1]/a/i').click()
                        page.wait_for_timeout(2000)

                        # Paste the pages data in the file config
                        for key, value in f_pages.items():
                            pages_count = len(f_pages)
                            if pages_count <= 1:
                                # attach_page = page.locator('xpath=//*[@id="attachToAll"]')
                                if page.locator('xpath=//*[@id="attachToAll"]').is_visible():
                                    page.locator('xpath=//*[@id="attachToAll"]').click()
                                    page.wait_for_timeout(1000)
                            else:
                                for page_path in os.listdir(pages_folder):
                                    # print(index)
                                    if page_path.endswith(".json"):
                                        page_file_path = os.path.join(pages_folder, page_path)
                                        with open(page_file_path, "r", encoding="utf-8") as f:
                                            page_data = json.load(f)
                                            p_title = page_data['settings']['title']
                                            p_uuid = page_data['settings']['uuid']

                                        if key == p_uuid and page.locator('xpath=//*[@id="attachToIndividual"]').is_visible():
                                            page.locator('xpath=//*[@id="attachToIndividual"]').click() #click on Individial Pages Radio Button
                                            if pages_count == 2:
                                                # Locate all <li> elements inside the specified <ul>
                                                li_locator = page.locator('xpath=/html/body/div[1]/div[1]/div[7]/div/div/div[2]/div/div/div[1]/div/div/div[3]/div[2]/div/div[2]/div/div/div/div/div/form/div[2]/div[2]/div[2]/div[3]/div/div[3]/ul/li/span')
                                                span_texts = li_locator.all_text_contents()

                                                if p_title in span_texts:
                                                    page.locator('xpath=//*[@id="attachToIndividual"]').click()  # Click on Individual Pages Radio Button
                                                    page.locator('xpath=//*[@id="webbuilder-editor-content-wrapper"]/div/div[1]/div/div/div[3]/div[2]/div/div[2]/div/div/div/div/div/form/div[2]/div[2]/div[2]/div[3]/div/div[2]').click()
                                                    add_individual_pages = page.locator('xpath=//*[@id="webbuilder-editor-content-wrapper"]/div/div[1]/div/div/div[3]/div[2]/div/div[2]/div/div/div/div/div/form/div[2]/div[2]/div[2]/div[3]/div/div[2]/input')
                                                    add_individual_pages.fill(p_title)
                                                    page.keyboard.press("Enter")
                                                    page.wait_for_timeout(700)
                                                else:
                                                    page.locator('xpath=//*[@id="attachToAll"]').click()
                                                    page.wait_for_timeout(1000)

                                            elif pages_count > 2:
                                                page.locator('xpath=//*[@id="attachToIndividual"]').click()  # Click on Individual Pages Radio Button
                                                page.locator('xpath=//*[@id="webbuilder-editor-content-wrapper"]/div/div[1]/div/div/div[3]/div[2]/div/div[2]/div/div/div/div/div/form/div[2]/div[2]/div[2]/div[3]/div/div[2]').click()
                                                add_individual_pages = page.locator('xpath=//*[@id="webbuilder-editor-content-wrapper"]/div/div[1]/div/div/div[3]/div[2]/div/div[2]/div/div/div/div/div/form/div[2]/div[2]/div[2]/div[3]/div/div[2]/input')
                                                add_individual_pages.fill(p_title)
                                                page.keyboard.press("Enter")
                                                page.wait_for_timeout(700)


                        # Paste file details in field

                        # Only proceed if header or footer is set and the section is visible
                        # if page.locator('xpath=//*[@id="webbuilder-editor-content-wrapper"]/div/div[1]/div/div/div[3]/div[2]/div/div[2]/div/div/div/div/div/form/div[2]/div[2]/div[3]').is_visible():
                        if page.locator("#fileplacementHeader").is_visible():
                            if (f_header_str != "0" or f_footer_str != "0"):
                                # Scope to the specific div containing the radio buttons
                                placement_section = page.locator('xpath=//*[@id="webbuilder-editor-content-wrapper"]/div/div[1]/div/div/div[3]/div[2]/div/div[2]/div/div/div/div/div/form/div[2]/div[2]/div[3]')
                                # Determine which value to select
                                if f_header_str != "0":
                                    placement_value = "header"
                                elif f_footer_str != "0":
                                    placement_value = "footer"
                                else:
                                    placement_value = "none"
                                # Select the correct radio button within the scoped section
                                placement_radio = placement_section.locator(f'input[type="radio"][value="{placement_value}"]')
                                placement_radio.click(force=True)
                                page.wait_for_timeout(1000)
                        else:
                            print("No Header or Footer Element Found")

                        if f_async != False:
                            async_field = page.locator('xpath=//*[@id="cssLoadingAsync"]') # for css file
                            if async_field.is_visible():
                                async_field.click()
                                page.wait_for_timeout(1000)
                            elif page.locator('xpath=//*[@id="fileloadasAsync"]').is_visible():
                                page.locator('xpath=//*[@id="fileloadasAsync"]').click() # for js or any other files
                                page.wait_for_timeout(1000)
                        elif page.locator('xpath=//*[@id="fileloadasDefer"]').is_visible():
                            page.locator('xpath=//*[@id="fileloadasDefer"]').click()
                            page.locator('xpath=//*[@id="fileloadasDefer"]')
                            page.wait_for_timeout(1000)
                        else:
                            page.wait_for_timeout(1000)

                        weight_field = page.locator('xpath=//*[@id="webbuilder-editor-content-wrapper"]/div/div[1]/div/div/div[3]/div[2]/div/div[2]/div/div/div/div/div/form/div[2]/div[3]/div[2]/input')
                        if weight_field.is_visible():
                            weight_field.click()
                            page.keyboard.press("Control+A")
                            weight_field.fill(f_weight_str)
                            page.wait_for_timeout(1000)

                        if f_modular != False:
                            modular_field = page.locator('xpath=//*[@id="modularFile"]')
                            modular_field.click()
                            page.wait_for_timeout(1000)

                        path_field = page.locator("input[name='filepath']")
                        if f_path_str and f_path_str != "None":
                            path_field.click()
                            page.keyboard.press("Control+A")
                            path_field.fill(f_path_str)
                            page.wait_for_timeout(1000)

                        category_span = page.locator('xpath=//*[@id="webbuilder-editor-content-wrapper"]/div/div[1]/div/div/div[3]/div[2]/div/div[2]/div/div/div/div/div/form/div[2]/div[3]/div[3]/div/div[2]/span')
                        if category_span.is_visible():
                            span_text = category_span.inner_text().strip()
                            # Check if f_category_str has a value (not empty and not None)
                            if f_category_str and f_category_str.strip() and f_category_str != span_text and f_category_str.strip() != "None":
                                category_field = page.locator('xpath=//*[@id="webbuilder-editor-content-wrapper"]/div/div[1]/div/div/div[3]/div[2]/div/div[2]/div/div/div/div/div/form/div[2]/div[3]/div[3]/div/div[2]/span')
                                category_field.click()
                                page.wait_for_timeout(1000)
                                category_fill = page.locator('xpath=//*[@id="webbuilder-editor-content-wrapper"]/div/div[1]/div/div/div[3]/div[2]/div/div[2]/div/div/div/div/div/form/div[2]/div[3]/div[3]/div/div[2]/input')
                                category_fill.fill(f_category_str)
                                page.wait_for_timeout(700)
                                page.keyboard.press("Enter")
                                page.wait_for_timeout(1000)

                        if f_private != False:
                            private_field = page.locator('xpath=//*[@id="privateFile"]')
                            if private_field.is_visible():
                                private_field.click()
                                page.wait_for_timeout(1000)


                        # Step 9: Click Save button
                        save_button = page.locator('xpath=//*[@id="webbuilder-editor-content-wrapper"]/div/div[1]/div/div/div[3]/div[2]/div/div[2]/div/div/div/div/div/form/div[1]/div[2]/div[2]/button')
                        cancel_button = page.locator('xpath=//*[@id="webbuilder-editor-content-wrapper"]/div/div[1]/div/div/div[3]/div[2]/div/div[2]/div/div/div/div/div/form/div[1]/div[2]/div[1]/button')
                        error_parent_div_xpath = page.locator('xpath=//*[@id="webbuilder-editor-content-wrapper"]/div/div[1]/div/div/div[3]/div[2]/div/div[2]/div/div/div/div/div/form/div[1]')

                        if save_button.get_attribute("disabled") is not None:
                            # Click the cancel button
                            cancel_button.click()
                            page.wait_for_timeout(1000)

                            # Create the CSV file only once if it doesn't exist
                            if not os.path.exists(skipped_file_csv):
                                with open(skipped_file_csv, mode='w', newline='', encoding='utf-8') as file:
                                    writer = csv.writer(file)
                                    writer.writerow(["Skipped File Name", "Error"])

                            # Append the skipped file name to the CSV
                            with open(skipped_file_csv, mode='a', newline='', encoding='utf-8') as file:
                                writer = csv.writer(file)
                                writer.writerow([f_name, "'Check the Configs Individually'"])

                            new_file_name = f"processed_{file_name}"
                            new_file_path = os.path.join(files_folder, new_file_name)
                            os.rename(file_path, new_file_path)

                        else:
                            # Click the save button
                            save_button.click()
                            page.wait_for_timeout(1000)
                            print("Save Button clicked")

                            # Check for error inside the specified div
                            # We look for any child div with class 'error'
                            error_found = error_parent_div_xpath.locator(".error-message").count() > 0

                            # if save_button.is_visible():
                            if error_found:
                                print("inside else condition to cancel")
                                cancel_button.click()
                                print("Cancel Button Clicked !!")

                                # Create the CSV file only once if it doesn't exist
                                if not os.path.exists(skipped_file_csv):
                                    with open(skipped_file_csv, mode='w', newline='', encoding='utf-8') as file:
                                        writer = csv.writer(file)
                                        writer.writerow(["Skipped File Name", "Error"])

                                # Append the skipped file name to the CSV
                                with open(skipped_file_csv, mode='a', newline='', encoding='utf-8') as file:
                                    writer = csv.writer(file)
                                    writer.writerow([f_name, 'File could not be Saved !!'])

                            new_file_name = f"processed_{file_name}"
                            new_file_path = os.path.join(files_folder, new_file_name)
                            os.rename(file_path, new_file_path)

                    else:
                        print(f"File : '{f_name}' Not in The WB Page")
                        # Create the CSV file only once if it doesn't exist
                        if not os.path.exists(skipped_file_csv):
                            with open(skipped_file_csv, mode='w', newline='', encoding='utf-8') as file:
                                writer = csv.writer(file)
                                writer.writerow(["Skipped File Name", "Error"])

                        # Append the skipped file name to the CSV
                        with open(skipped_file_csv, mode='a', newline='', encoding='utf-8') as file:
                            writer = csv.writer(file)
                            writer.writerow([f_name, 'File could not be Saved !!'])

                        new_file_name = f"processed_{file_name}"
                        new_file_path = os.path.join(files_folder, new_file_name)
                        os.rename(file_path, new_file_path)

                else:
                    # Create the CSV file only once if it doesn't exist
                    if not os.path.exists(skipped_file_csv):
                        with open(skipped_file_csv, mode='w', newline='', encoding='utf-8') as file:
                            writer = csv.writer(file)
                            writer.writerow(["Skipped File Name", "Error"])

                    # Append the skipped file name to the CSV
                    with open(skipped_file_csv, mode='a', newline='', encoding='utf-8') as file:
                        writer = csv.writer(file)
                        writer.writerow([f_name, "'File Not Found in Webbuilder"])

                    new_file_name = f"processed_{file_name}"
                    new_file_path = os.path.join(files_folder, new_file_name)
                    os.rename(file_path, new_file_path)

    print(f"Completed Batch : {batch_index + 1} of {len(batches)}")
    print("======================================================")


def import_file(request, site_id):
    """
    Handle file import for a site. Accepts file upload via POST and processes it.
    """
    if request.method == 'POST' and request.FILES.get('import_file'):
        uploaded_file = request.FILES['import_file']
        # Example: Save the uploaded file to a temporary location
        import os
        from django.conf import settings
        temp_dir = getattr(settings, 'MEDIA_ROOT', '/tmp')
        file_path = os.path.join(temp_dir, uploaded_file.name)
        with open(file_path, 'wb+') as destination:
            for chunk in uploaded_file.chunks():
                destination.write(chunk)
        # Optionally, trigger background processing here
        return JsonResponse({'status': 'success', 'message': f'File {uploaded_file.name} uploaded.'})
    return render(request, 'site_manager/import_file.html', {'site_id': site_id})

@login_required
@require_GET
def export_status(request, site_id):
    """
    Return the export status for a given site_id as JSON.
    """
    return JsonResponse({"status": "ok", "site_id": site_id})

@login_required
def pages_import_view(request, site_id):
    """
    View for importing pages for a given site. Handles POST to trigger import_pages_func.py.
    """
    site = get_object_or_404(SiteListDetails, pk=site_id)
    if request.method == 'POST':
        try:
            # Run the import_pages_func.py script
            result = subprocess.run([
                'python3', 'import_pages_func.py', str(site_id)
            ], capture_output=True, text=True, check=True)
            messages.success(request, f"Pages import completed successfully. Output: {result.stdout}")
        except subprocess.CalledProcessError as e:
            messages.error(request, f"Pages import failed: {e.stderr or e.output or str(e)}")
        except Exception as e:
            messages.error(request, f"Unexpected error: {str(e)}")
        return redirect('pages_import', site_id=site.id)
    return render(request, 'site_manager/pages_import.html', {'site': site})
    """
    View for importing pages for a given site. Handles POST to trigger import_pages_func.py.
    """
    site = get_object_or_404(SiteListDetails, pk=site_id)
    if request.method == 'POST':
        try:
            # Run the import_pages_func.py script
            result = subprocess.run([
                'python3', 'import_pages_func.py', str(site_id)
            ], capture_output=True, text=True, check=True)
            messages.success(request, f"Pages import completed successfully. Output: {result.stdout}")
        except subprocess.CalledProcessError as e:
            messages.error(request, f"Pages import failed: {e.stderr or e.output or str(e)}")
        except Exception as e:
            messages.error(request, f"Unexpected error: {str(e)}")
        return redirect('pages_import', site_id=site.id)
    return render(request, 'site_manager/pages_import.html', {'site': site})

@login_required
def file_upload_meta(request, site_id):
    """
    Handle file upload using the file_upload.py script for WebBuilder.
    This function integrates with the PfizerWebBuilderUploader class.
    """
    import tempfile
    from django.contrib import messages
    from django.http import JsonResponse
    import threading
    
    site = get_object_or_404(SiteListDetails, pk=site_id)
    status_file = os.path.join(settings.BASE_DIR, f"site_{site_id}_file_upload.status")
    
    if request.method == 'POST':
        # Get WebBuilder configuration from environment variables
        instance_id = os.getenv('INSTANCE_ID', '')
        username = os.getenv('USERNAME', '')
        password = os.getenv('PASSWORD', '')
        file_folder = os.getenv('FILEFOLDER', '')
        
        if not instance_id:
            return JsonResponse({'success': False, 'message': 'Instance ID not configured in environment variables.'})
        
        if not file_folder:
            return JsonResponse({'success': False, 'message': 'FILEFOLDER not configured in environment variables.'})
        
        if not os.path.exists(file_folder):
            return JsonResponse({'success': False, 'message': f'File directory does not exist: {file_folder}'})
        
        # Get all files from the configured directory
        try:
            all_files = [f for f in os.listdir(file_folder) if os.path.isfile(os.path.join(file_folder, f))]
            if not all_files:
                return JsonResponse({'success': False, 'message': f'No files found in directory: {file_folder}'})
            
            # Start background upload process
            thread = threading.Thread(
                target=run_file_upload_in_background,
                args=(site_id, file_folder, instance_id, username, password, status_file)
            )
            thread.daemon = True
            thread.start()
            
            response_data = {
                'success': True, 
                'message': f'File upload started for {len(all_files)} files from {file_folder}. You can check the status below.'
            }
            
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse(response_data)
            
            messages.info(request, response_data['message'])
            return redirect('site_meta_list', site_id=site_id)
            
        except Exception as e:
            return JsonResponse({'success': False, 'message': f'Error reading directory: {str(e)}'})
    
    # Get environment configuration for display
    instance_id = os.getenv('INSTANCE_ID', 'Not configured')
    username = os.getenv('USERNAME', 'Not configured')
    file_folder = os.getenv('FILEFOLDER', 'Not configured')
    
    # Get list of files in the directory
    available_files = []
    directory_exists = False
    if file_folder and file_folder != 'Not configured':
        directory_exists = os.path.exists(file_folder)
        if directory_exists:
            try:
                available_files = [f for f in os.listdir(file_folder) if os.path.isfile(os.path.join(file_folder, f))]
            except Exception:
                available_files = []
    
    return render(request, 'site_manager/file_upload_meta.html', {
        'site': site,
        'site_id': site_id,
        'instance_id': instance_id,
        'username': username,
        'file_folder': file_folder,
        'available_files': available_files,
        'directory_exists': directory_exists,
        'credentials_configured': bool(os.getenv('USERNAME')) and bool(os.getenv('PASSWORD'))
    })

def run_file_upload_in_background(site_id, file_folder, instance_id, username, password, status_file):
    """
    Run the file upload process in the background using the file_upload.py script.
    """
    import sys
    
    try:
        # Write initial status with process information
        process_info = {
            'status': 'running', 
            'message': 'File upload in progress... Checking authentication status...',
            'pid': os.getpid(),
            'start_time': time.time()
        }
        with open(status_file, 'w') as f:
            f.write(json.dumps(process_info))
        
        # Set up environment variables for the upload script
        env = os.environ.copy()
        env['FILEFOLDER'] = file_folder
        env['INSTANCE_ID'] = instance_id
        env['USERNAME'] = username
        env['PASSWORD'] = password
        
        # Get the path to file_upload.py
        upload_script_path = os.path.join(settings.BASE_DIR, 'file_upload.py')
        
        # Run the file upload script with periodic status updates
        import threading
        import subprocess
        
        # Start a thread to periodically update status to show process is alive
        def update_status_periodically():
            start_time = time.time()
            while True:
                time.sleep(60)  # Update every minute
                elapsed = int((time.time() - start_time) / 60)
                try:
                    with open(status_file, 'w') as f:
                        f.write(json.dumps({
                            'status': 'running', 
                            'message': f'File upload in progress... ({elapsed} minutes elapsed)',
                            'pid': os.getpid(),
                            'last_update': time.time()
                        }))
                except:
                    break  # Exit if we can't write status (probably finished)
        
        status_thread = threading.Thread(target=update_status_periodically)
        status_thread.daemon = True
        status_thread.start()
        
        result = subprocess.run([
            sys.executable, upload_script_path
        ], capture_output=True, text=True, env=env, timeout=600)  # 10 minute timeout
        
        if result.returncode == 0:
            # Check if SSO was detected in the output
            sso_detected = "SSO authentication successful!" in result.stdout or "already authenticated via SSO" in result.stdout
            auth_method = "SSO" if sso_detected else "Credentials"
            
            # Parse the output for upload statistics
            output_lines = result.stdout.split('\n')
            total_files = 0
            skipped_files = 0
            successful_uploads = 0
            failed_uploads = 0
            
            for line in output_lines:
                if "Total files processed:" in line:
                    total_files = int(line.split(':')[1].strip())
                elif "Skipped files (already exist):" in line:
                    skipped_files = int(line.split(':')[1].strip())
                elif "Successful uploads:" in line:
                    successful_uploads = int(line.split(':')[1].strip())
                elif "Failed uploads:" in line:
                    failed_uploads = int(line.split(':')[1].strip())
            
            # Create detailed success message
            if skipped_files > 0:
                message = f'File upload completed using {auth_method} authentication. '
                message += f'Processed {total_files} files: {successful_uploads} uploaded, {skipped_files} already existed'
                if failed_uploads > 0:
                    message += f', {failed_uploads} failed'
                message += f'. Time saved by skipping existing files: ~{skipped_files * 2} minutes.'
            else:
                message = f'File upload completed successfully using {auth_method} authentication. {successful_uploads} files uploaded.'
            
            status = {
                'status': 'completed', 
                'message': message,
                'output': result.stdout,
                'stats': {
                    'total_files': total_files,
                    'skipped_files': skipped_files,
                    'successful_uploads': successful_uploads,
                    'failed_uploads': failed_uploads
                }
            }
        else:
            # Parse error message for authentication-related issues
            error_msg = result.stderr or "Unknown error"
            if "login" in error_msg.lower() or "authentication" in error_msg.lower():
                status = {
                    'status': 'failed', 
                    'message': f'Authentication failed: {error_msg}. Please check SSO status or credentials.',
                    'output': result.stdout
                }
            else:
                status = {
                    'status': 'failed', 
                    'message': f'File upload failed: {error_msg}',
                    'output': result.stdout
                }
            
    except subprocess.TimeoutExpired:
        status = {
            'status': 'failed', 
            'message': 'File upload timed out after 10 minutes.'
        }
    except Exception as e:
        status = {
            'status': 'failed', 
            'message': f'Unexpected error during file upload: {str(e)}'
        }
    finally:
        # Write final status
        with open(status_file, 'w') as f:
            f.write(json.dumps(status))
        
        # If the upload completed successfully, schedule cleanup of the status file
        if status.get('status') == 'completed':
            # Clean up the status file after 30 seconds to give user time to see success message
            import threading
            def cleanup_status_file():
                time.sleep(30)
                try:
                    if os.path.exists(status_file):
                        os.remove(status_file)
                        print(f"Cleaned up status file: {status_file}")
                except Exception as e:
                    print(f"Error cleaning up status file: {e}")
            
            cleanup_thread = threading.Thread(target=cleanup_status_file)
            cleanup_thread.daemon = True
            cleanup_thread.start()

@login_required
def check_file_upload_status(request, site_id):
    """
    Check the status of the file upload process for a given site_id.
    Returns JSON: {"status": str, "message": str, "output": str}
    """
    status_file = os.path.join(settings.BASE_DIR, f"site_{site_id}_file_upload.status")
    status = {'status': 'not_started', 'message': 'No file upload in progress.'}
    
    if os.path.exists(status_file):
        try:
            # Check if the status file is stale (older than 15 minutes)
            file_age = time.time() - os.path.getmtime(status_file)
            if file_age > 900:  # 15 minutes
                print(f"Status file is stale ({file_age/60:.1f} minutes old), removing it")
                os.remove(status_file)
                return JsonResponse(status)
            
            with open(status_file, 'r') as f:
                status = json.load(f)
                
            # Check if upload is truly stale by checking process and last update time
            if status.get('status') == 'running':
                is_stale = False
                last_update = status.get('last_update', status.get('start_time', 0))
                time_since_update = time.time() - last_update if last_update else file_age
                
                # Consider stale if no update for 10 minutes
                if time_since_update > 600:  # 10 minutes
                    is_stale = True
                    reason = f"no status update for {time_since_update/60:.1f} minutes"
                
                # Additional check: if we have a PID, check if process is still running
                if not is_stale and status.get('pid'):
                    try:
                        import psutil
                        if not psutil.pid_exists(status['pid']):
                            is_stale = True
                            reason = "process no longer exists"
                    except ImportError:
                        # psutil not available, fall back to time-based check
                        if file_age > 600:  # 10 minutes
                            is_stale = True
                            reason = f"file age {file_age/60:.1f} minutes (psutil not available)"
                
                if is_stale:
                    print(f"Running upload appears stale: {reason}")
                    status = {
                        'status': 'failed',
                        'message': 'Upload process appears to have stopped unexpectedly. You can try starting a new upload.',
                        'output': status.get('output', '')
                    }
                    # Update the status file
                    with open(status_file, 'w') as f:
                        f.write(json.dumps(status))
                    
        except Exception as e:
            print(f"Error reading status file: {e}")
            # If we can't read the status file, remove it
            try:
                os.remove(status_file)
            except:
                pass
    
    return JsonResponse(status)

@login_required
def clear_file_upload_status(request, site_id):
    """
    Clear the file upload status for a given site_id.
    This is useful for clearing stale status files.
    """
    status_file = os.path.join(settings.BASE_DIR, f"site_{site_id}_file_upload.status")
    
    try:
        if os.path.exists(status_file):
            os.remove(status_file)
            return JsonResponse({
                'success': True, 
                'message': 'Upload status cleared successfully.'
            })
        else:
            return JsonResponse({
                'success': True, 
                'message': 'No upload status to clear.'
            })
    except Exception as e:
        return JsonResponse({
            'success': False, 
            'message': f'Error clearing status: {str(e)}'
        })
