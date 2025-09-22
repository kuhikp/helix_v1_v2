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

# Django imports
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.sessions.models import Session
from django.db import models
from django.db.models import Sum, Count, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.db import connection

# Third-party imports
import requests
import urllib3
from bs4 import BeautifulSoup

# Project-specific imports
from .models import SiteListDetails, SiteMetaDetails
from .forms import SiteListDetailsForm, SiteMetaDetailsForm
from tag_manager_component.models import Tag, TagMapper
from tag_manager_component.views import get_website_complexity

# Disable SSL warnings for sites with certificate issues
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Configure logging
logger = logging.getLogger(__name__)

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
                site.save()
                return JsonResponse({"success": True, "site_id": webbuilder_site_id})
            else:
                return JsonResponse({"success": False, "error": "Site ID not found in URL output: " + url})
        except subprocess.CalledProcessError as e:
            error_message = e.stderr or str(e)
            return JsonResponse({"success": False, "error": error_message})
        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)})
    return JsonResponse({"success": False, "error": "Invalid request"})
