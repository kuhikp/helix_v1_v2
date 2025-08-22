from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from .models import SiteListDetails, SiteMetaDetails
from .forms import SiteListDetailsForm, SiteMetaDetailsForm
import requests
from bs4 import BeautifulSoup
import logging
import xml.etree.ElementTree as ET
from django.db import models
import json
import re
from tag_manager_component.models import Tag, TagMapper
from tag_manager_component.views import get_website_complexity
import csv
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
import threading
import time
from django.contrib.sessions.models import Session
from django.contrib.sessions.backends.db import SessionStore
from tag_manager_component.views import get_website_complexity
from django.utils import timezone
from urllib.parse import urlparse
import urllib3
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
import time
import csv
# Disable SSL warnings for sites with certificate issues
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# Configure logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

@login_required
def site_list(request):
    query = request.GET.get('search', '').strip()
    if query:
        filtered_sites = SiteListDetails.objects.filter(website_url__icontains=query)
    else:
        filtered_sites = SiteListDetails.objects.all()
    sites = SiteListDetails.objects.all()
    return render(request, 'site_manager/site_list.html', {
        'sites': sites,
        'filtered_sites': filtered_sites,
        'search': query,
    })
@login_required
def site_meta_export_config(request, site_id):
    # site = get_object_or_404(SiteListDetails, pk=site_id)
    print(f"Attempting to export config for site_id: {site_id}")
    site = get_object_or_404(SiteListDetails, pk=site_id)
    print(f"Found site: {site.helix_site_id}")

    Weburl = site.website_url.replace('http://', '').replace('https://', '').replace('www.', '')
    print(f"Found url: {Weburl}")
    # Set up Chrome options
    chrome_options = Options()
    # Uncomment the next line if you want to run in headless mode
    # chrome_options.add_argument("--headless")

    # Set up the WebDriver
    driver = webdriver.Chrome(options=chrome_options)
    wait = WebDriverWait(driver, 10)

    
    # Update helix_site_id if this is the requested site
    # if site.id == 1193:
    #     site.helix_site_id = 5791
    #     site.website_url
    #     site.save()
    # meta_details = site.meta_details.all()
   # Set up Chrome options
    chrome_options = Options()
   
    # return HttpResponse("Exited after printing meta_details.")
    # Uncomment the next line if you want to run in headless mode
    # chrome_options.add_argument("--headless")

    # Set up the WebDriver
    driver = webdriver.Chrome(options=chrome_options)
    wait = WebDriverWait(driver, 10)

    try:
        print("Starting Pfizer WebBuilder login process...")
        
        # Navigate to the login page
        driver.get('https://webbuilder.pfizer/webbuilder/dashboard')
        print("Navigated to login page")
        
        # Wait for the page to load
        time.sleep(2)
        
        # Wait for login form to be present
        try:
            driver.execute_script("document.querySelector('div.tw-text-center a.tw-bg-gray-900').click();", 1)
            time.sleep(5)
            # Check if 'authorization' is present in the current URL
            if 'authorization' in driver.current_url:
                driver.find_element(By.ID, "username").send_keys('')
                driver.find_element(By.ID, "password").send_keys('')
                driver.find_element(By.ID, "submit_button").click()
                time.sleep(5)

            print("Login credentials submitted")
            
            
            print(f"Login completed. Current URL: {driver.current_url}")
            
        except Exception as e:
            print(f"Could not find login elements automatically. Error: {e}")
            print("Please manually complete the login process...")
            input("Press Enter after you have logged in manually...")
        
        # Navigate to the dashboard
        driver.get('https://webbuilder.pfizer/webbuilder/dashboard')
        print("Navigating to dashboard...")

        # Read values from input.csv
        with open('/Users/tcs/pfizer/tag_manager/site_manager/static/site_manager/samples/input.csv', 'r', encoding='utf-8') as csvfile:
            reader = csv.reader(csvfile)
            # next(reader) # Uncomment this line if your CSV has a header row
            for row in reader:
                if not row:  # Skip empty rows
                    continue
                
                website_id = site.helix_site_id
                panel_type = row[0]  # Assuming panel_type is in the first column

                
                # Construct the dynamic URL
                dynamic_url = f"https://webbuilder.pfizer/builder/website/{website_id}?panel={panel_type}"
                print(f"Navigating to URL for website_id: {website_id}, panel_type: {panel_type}")
                driver.get(dynamic_url)
                
                # Wait for the page to load. You might need to adjust the condition.
                # For example, wait for a specific element that appears on the target page.
                # Here, we'll just add a small delay.
                time.sleep(3) 
                
                print(f"Successfully navigated to: {driver.current_url}")
                # Wait for dashboard to load
                wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
                print("Successfully navigated to dashboard")
                print(f"Current URL: {driver.current_url}")
                print(f"Page title: {driver.title}")
                
                # Keep the browser open for a few seconds to see the result
                time.sleep(3)
                # Get all elements on the page
                inputs = driver.find_elements(By.XPATH, "//input | //textarea | //select | //checkbox")
                # Prepare data: get name, type, and value for each input
                rows = []
                for inp in inputs:
                    if inp.get_attribute('type') == 'checkbox':
                        name = inp.get_attribute('name') or inp.get_attribute('id') or ''
                        input_type = 'checkbox'
                        # For checkboxes, the 'value' is its checked state
                        value = 'checked' if inp.is_selected() else 'unchecked'
                    else:
                        name = inp.get_attribute('name') or ''
                        if inp.tag_name == 'select' and not name:
                            name = inp.get_attribute('id') or ''
                        input_type = inp.get_attribute('type') or ''
                        value = inp.get_attribute('value') or ''
                    rows.append([website_id, panel_type, name, input_type, value])  # Added website_id as a new column

                # Write to CSV (append mode)
                with open(f'/Users/tcs/pfizer/tag_manager/site_manager/static/site_manager/samples/{website_id}.csv', 'a', newline='', encoding='utf-8') as csvfile:
                    writer = csv.writer(csvfile)
                    # Write header only if file is empty
                    if csvfile.tell() == 0:
                        writer.writerow(['Website ID', 'Panel Type', 'Name', 'Type', 'Value'])
                    writer.writerows(rows)
                # You can add more actions here for each page

    except Exception as e:
        print(f"An error occurred: {e}")
        print(f"Current URL: {driver.current_url}")

    finally:
        # Close the browser
        driver.quit()
        print("Browser closed")
        print("Script execution completed.")

    #return HttpResponse(f"Export complete for site_id {site_id}. helix_site_id is now {site.helix_site_id}")
    return render(request, f'sites/{site_id}/meta')

@login_required
def batch_analyze_sitemaps(request):
    """
    Initiate batch analysis with progress tracking
    """
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
    progress_data = request.session.get('batch_analysis_progress', {
        'status': 'not_started',
        'current': 0,
        'total': 0,
        'current_site': '',
        'completed_sites': [],
        'failed_sites': []
    })
    
    # Calculate percentage
    if progress_data['total'] > 0:
        percentage = round((progress_data['current'] / progress_data['total']) * 100, 1)
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
     
        # Get session
        session = SessionStore(session_key=session_key)
        
        # Get all sites
        sites = SiteListDetails.objects.filter(is_imported=False)
        total_sites = sites.count()
        
        # Update progress
        progress = session.get('batch_analysis_progress', {})
        progress.update({
            'status': 'processing',
            'total': total_sites,
            'current': 0
        })
        session['batch_analysis_progress'] = progress
        session.save()
        
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
                sitemap_urls = fetch_sitemap_urls(site.website_url)
                if not sitemap_urls:
                    failed_sites.append({'url': site.website_url, 'error': 'No sitemap found'})
                    continue
                
                for sitemap_url in sitemap_urls:
                    soup, page_source, error = fetch_page(sitemap_url)
                    if error:
                        continue
                    print("URL >>>")
                    print(sitemap_url)
                    custom_elements = find_enhanced_custom_class_elements(soup, "custom-block-element")
                    helix_elements = find_enhanced_helix_elements(soup, page_source)
                    
                    # Get tag mappings
                    v1_tags = Tag.objects.filter(version='V1').order_by('name')
                    v2_tags = Tag.objects.filter(version='V2').order_by('name')
                    v1_to_v2_map = {}
                    for v1 in v1_tags:
                        mappings = TagMapper.objects.filter(v1_component_name=v1.name)
                        v1_to_v2_map[v1.name] = [{'v2_name': m.v2_component_name, 'weight': m.weight} for m in mappings]
                    
                    # Process compatible components
                    helix_v2_compatible_component_data = []
                    for v1_component_name in helix_elements:
                        if v1_component_name in v1_to_v2_map:
                            sorted_mappings = sorted(v1_to_v2_map[v1_component_name], key=lambda x: x['weight'], reverse=True)
                            if sorted_mappings:
                                helix_v2_compatible_component_data.append(sorted_mappings[0]['v2_name'])
                    
                    # Process non-compatible components
                    helix_v2_non_compatible_component_data = []
                    for v1_component_name in helix_elements:
                        if v1_component_name not in v1_to_v2_map or not v1_to_v2_map[v1_component_name]:
                            helix_v2_non_compatible_component_data.append(v1_component_name)
                    
                    # Create meta details
                    # Remove empty elements and store as comma separated string
                    helix_v1_component_str = ",".join([e for e in set(helix_elements) if e])
                    helix_v2_compatible_component_str = ",".join([e for e in set(helix_v2_compatible_component_data) if e])
                    helix_v2_non_compatible_component_str = ",".join([e for e in set(helix_v2_non_compatible_component_data) if e])
                    custom_component_str = ",".join([e for e in set(custom_elements) if e])

                    SiteMetaDetails.objects.create(
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
                
                # Update site details after analysis
                # Remove duplicates and blank values, store as comma-separated string
                # Collect all helix_v1_component values (JSON strings), flatten, deduplicate, and store as JSON array
                helix_v1_components_raw = SiteMetaDetails.objects.filter(
                    site_list_details=site, helix_v1_component__isnull=False
                ).values_list('helix_v1_component', flat=True)
                unique_v1_components = set()
                for value in helix_v1_components_raw:
                    try:
                        items = json.loads(value)
                        if isinstance(items, list):
                            unique_v1_components.update([v for v in items if v])
                    except Exception:
                        pass
                site.helix_v1_component = json.dumps(sorted(unique_v1_components))
                # Store as comma-separated string, remove duplicates and blanks
                site.helix_v1_component = ",".join(sorted(set([str(v) for v in unique_v1_components if v])))
                
                print(site.helix_v1_component)
                print("PARAG HERE")
                site.helix_v2_compatible_component = json.dumps(
                    list(
                        set(
                            str(value) for value in SiteMetaDetails.objects.filter(
                                site_list_details=site, helix_v2_compatible_component__isnull=False
                            ).values_list('helix_v2_compatible_component', flat=True)
                        )
                    )
                )
                site.helix_v2_non_compatible_component = json.dumps(
                    list(
                        set(
                            str(value) for value in SiteMetaDetails.objects.filter(
                                site_list_details=site, helix_v2_non_compatible_component__isnull=False
                            ).values_list('helix_v2_non_compatible_component', flat=True)
                        )
                    )
                )
                site.custom_component = SiteMetaDetails.objects.filter(
                    site_list_details=site, custom_component_count__isnull=False
                ).aggregate(total=models.Sum('custom_component_count'))['total'] or 0
                site.v2_compatible_count = SiteMetaDetails.objects.filter(
                    site_list_details=site, helix_v2_compatible_component__isnull=False
                ).aggregate(total=models.Sum('v2_compatible_count'))['total'] or 0
                site.v2_non_compatible_count = SiteMetaDetails.objects.filter(
                    site_list_details=site, helix_v2_non_compatible_component__isnull=False
                ).aggregate(total=models.Sum('v2_non_compatible_count'))['total'] or 0
                site.total_pages = site.meta_details.count()
                
                # Calculate and update complexity based on site data
                try:
                    # Calculate component complexity counts by analyzing the components found
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
                            print(f"Component: {component_name}, Complexity: {tag.complexity}")
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
                            site.complexity = calculated_complexity
                            
                            # Store the configuration data used for this complexity determination
                            if config_data:
                                # Add site data to config for complete audit trail
                                full_config_data = {
                                    'configuration_used': config_data,
                                    'site_data_at_calculation': site_data,
                                    'calculation_timestamp': timezone.now().isoformat(),
                                    'complexity_determined': calculated_complexity
                                }
                                site.complexity_configuration = json.dumps(full_config_data)
                            
                            print(f"Updated complexity for {site.website_url}: {calculated_complexity} (simple: {simple_count}, medium: {medium_count}, complex: {complex_count})")
                        else:
                            print(f"Could not determine complexity for {site.website_url}, keeping default")
                    else:
                        print(f"Could not determine complexity for {site.website_url}, keeping default")
                except Exception as complexity_error:
                    logger.warning(f"Error calculating complexity for {site.website_url}: {complexity_error}")
                
                site.is_imported = True
                site.last_analyzed = timezone.now()
                site.save()
                
                completed_sites.append(site.website_url)
                
            except Exception as e:
                logger.warning(f"Error analyzing site {site.website_url}: {e}")
                failed_sites.append({'url': site.website_url, 'error': str(e)})
            
            # Update progress after each site
            progress = session.get('batch_analysis_progress', {})
            progress.update({
                'current': index + 1,
                'completed_sites': completed_sites,
                'failed_sites': failed_sites
            })
            session['batch_analysis_progress'] = progress
            session.save()
        
        # Mark as completed
        progress = session.get('batch_analysis_progress', {})
        progress.update({
            'status': 'completed',
            'current': total_sites,
            'current_site': '',
            'end_time': time.time()
        })
        session['batch_analysis_progress'] = progress
        session.save()
        
    except Exception as e:
        logger.error(f"Error in batch analysis process: {e}")
        # Mark as failed
        try:
            progress = session.get('batch_analysis_progress', {})
            progress.update({
                'status': 'failed',
                'error': str(e)
            })
            session['batch_analysis_progress'] = progress
            session.save()
        except:
            pass


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
    site = get_object_or_404(SiteListDetails, pk=site_id)
    sitemap_urls = fetch_sitemap_urls(site.website_url)

    if not sitemap_urls:
        return render(request, 'site_manager/error.html', {'error': 'No sitemap URLs found.'})

    for sitemap_url in sitemap_urls:
        try:

            soup, page_source, error = fetch_page(sitemap_url)
            if error:
                logger.warning(f"Error fetching {sitemap_url}: {error}")
                continue
             
            custom_elements = find_enhanced_custom_class_elements(soup, "custom-block-element")
            helix_elements = find_enhanced_helix_elements(soup, page_source)

            
        
            v1_tags = Tag.objects.filter(version='V1').order_by('name')
            v2_tags = Tag.objects.filter(version='V2').order_by('name')
            # Build current mapping: {v1_name: [v2_name, ...]}
            v1_to_v2_map = {}
            for v1 in v1_tags:
                mappings = TagMapper.objects.filter(v1_component_name=v1.name)
                v1_to_v2_map[v1.name] = [{'v2_name': m.v2_component_name, 'weight': m.weight} for m in mappings]

            # Fetch v2_component_name based on v1_component_name using the updated mapping logic
            helix_v2_compatible_component_data = []
            for v1_component_name in helix_elements:
                if v1_component_name in v1_to_v2_map:
                    # Sort mappings by weight (descending) and pick the highest-weighted v2_name
                    sorted_mappings = sorted(v1_to_v2_map[v1_component_name], key=lambda x: x['weight'], reverse=True)
                    if sorted_mappings:
                        helix_v2_compatible_component_data.append(sorted_mappings[0]['v2_name'])
                else:
                    logger.warning(f"No mapping found for v1 component '{v1_component_name}'")

            # Determine non-compatible v2 tags
            helix_v2_non_compatible_component_data = []
            for v1_component_name in helix_elements:
                if v1_component_name not in v1_to_v2_map or not v1_to_v2_map[v1_component_name]:
                    helix_v2_non_compatible_component_data.append(v1_component_name)
         
            
            # print("START DEBUGGING")
            # print(sitemap_url)
            # print(type(helix_elements))
            # print(helix_elements)
            # print(len(helix_elements))
            # print(type(helix_v2_compatible_component_data))
            # print(helix_v2_compatible_component_data)
            # print(len(helix_v2_compatible_component_data))
            # print(type(helix_v2_non_compatible_component_data))
            # print(helix_v2_non_compatible_component_data)
            # print(len(helix_v2_non_compatible_component_data))
            # print("END DEBUGGING")
            SiteMetaDetails.objects.create(
                site_list_details=site,
                site_url=sitemap_url,
                helix_v1_component=json.dumps(list(set(helix_elements))),
                helix_v2_compatible_component=json.dumps(list(set(helix_v2_compatible_component_data))),
                helix_v2_non_compatible_component=json.dumps(list(set(helix_v2_non_compatible_component_data))),
                custom_component=json.dumps(list(set(custom_elements))),
                v2_compatible_count=len(helix_v2_compatible_component_data),
                v2_non_compatible_count=len(helix_v2_non_compatible_component_data),
                custom_component_count=len(custom_elements),
            )
        except requests.exceptions.RequestException as e:
            return render(request, 'site_manager/error.html', {'error': str(e)})


    site.helix_v1_component = json.dumps(
        list(
            set(
                str(value) for value in SiteMetaDetails.objects.filter(
                    site_list_details=site, helix_v1_component__isnull=False
                ).values_list('helix_v1_component', flat=True)
            )
        )
    )
    site.helix_v2_compatible_component = json.dumps(
        list(
            set(
                str(value) for value in SiteMetaDetails.objects.filter(
                    site_list_details=site, helix_v2_compatible_component__isnull=False
                ).values_list('helix_v2_compatible_component', flat=True)
            )
        )
    )
    site.helix_v2_non_compatible_component = json.dumps(
        list(
            set(
                str(value) for value in SiteMetaDetails.objects.filter(
                    site_list_details=site, helix_v2_non_compatible_component__isnull=False
                ).values_list('helix_v2_non_compatible_component', flat=True)
            )
        )
    )

    site.custom_component = SiteMetaDetails.objects.filter(
        site_list_details=site, custom_component_count__isnull=False
    ).aggregate(total=models.Sum('custom_component_count'))['total'] or 0

    # Update total_pages count
    site.v2_compatible_count = SiteMetaDetails.objects.filter(
        site_list_details=site, helix_v2_compatible_component__isnull=False
    ).aggregate(total=models.Sum('v2_compatible_count'))['total'] or 0
    
    site.v2_non_compatible_count = SiteMetaDetails.objects.filter(
        site_list_details=site, helix_v2_non_compatible_component__isnull=False
    ).aggregate(total=models.Sum('v2_non_compatible_count'))['total'] or 0

    
    
    site.total_pages = site.meta_details.count()
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


def fetch_sitemap_urls(base_url):
    """
    Fetch all URLs from sitemap(s) for the given website
    Returns a list of URLs found in sitemaps
    """
    urls_found = []

    try:
        
        # Common sitemap locations
        sitemap_urls = [
            f"{base_url}/sitemap.xml",
            # f"{base_url}/sitemap_index.xml", 
            # f"{base_url}/sitemaps.xml",
            # f"{base_url}/sitemap/sitemap.xml",
            # f"{base_url}/sitemap1.xml"
        ]

        # Check robots.txt for sitemap references
        try:
            robots_url = f"{base_url}/robots.txt"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'text/plain, */*',
                'Accept-Language': 'en-US,en;q=0.9,*;q=0.8'
            }
            robots_response = requests.get(robots_url, headers=headers, timeout=10, verify=False)
            if robots_response.status_code == 200:
                robots_content = robots_response.text
                # Look for sitemap directives
                for line in robots_content.split('\n'):
                    if line.lower().startswith('sitemap:'):
                        sitemap_url = line.split(':', 1)[1].strip()
                        if sitemap_url not in sitemap_urls:
                            sitemap_urls.append(sitemap_url)
        except Exception as e:
            logger.warning(f"Could not fetch robots.txt: {e}")

        # Try each sitemap URL
        for sitemap_url in sitemap_urls:
            try:
                print(f"Trying sitemap: {sitemap_url}")
                # Enhanced headers and SSL handling
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                    'Accept': 'application/xml, text/xml, */*',
                    'Accept-Language': 'en-US,en;q=0.9,*;q=0.8',
                    'Cache-Control': 'no-cache',
                    'Connection': 'keep-alive'
                }
                
                # Disable SSL verification to handle self-signed certificates
                response = requests.get(sitemap_url, headers=headers, timeout=15, verify=False)
                print(f"Response for {sitemap_url}: {response.status_code}")
                if response.status_code == 200:
                    #print(f"Sitemap content: {response.text[:500]}...")  # Log first 500 characters
                    urls_from_sitemap = parse_sitemap(response.content, base_url)
                    urls_found.extend(urls_from_sitemap)
                    #print(f"Found {len(urls_from_sitemap)} URLs in {sitemap_url}")
                else:
                    print(f"Sitemap {sitemap_url} returned status code {response.status_code}")
                    logger.warning(f"Sitemap {sitemap_url} returned status code {response.status_code}")

            except Exception as e:
                print(f"Error fetching sitemap {sitemap_url}: {e}")
                logger.warning(f"Error fetching sitemap {sitemap_url}: {e}")
                continue

       
        unique_urls = list(set(urls_found))
        valid_urls = []

        #print(unique_urls)
        for url in unique_urls:
            #print(f"Validating URL: {url}")
            if url.startswith(('http://', 'https://')):
                valid_urls.append(url)

        logger.info(f"Total unique valid URLs found: {len(valid_urls)}")
        return valid_urls

    except Exception as e:
        logger.error(f"Error fetching sitemap URLs: {e}")
        return []


def parse_sitemap(sitemap_content, base_url):
    """
    Parse sitemap XML content and extract URLs
    Handles both regular sitemaps and sitemap index files
    Enhanced to handle multi-language URLs and various sitemap formats
    """
    urls = []
    
    try:
        # Try to decode if it's bytes
        if isinstance(sitemap_content, bytes):
            try:
                sitemap_content = sitemap_content.decode('utf-8')
            except UnicodeDecodeError:
                sitemap_content = sitemap_content.decode('utf-8', errors='ignore')
        
        root = ET.fromstring(sitemap_content)
        
        # Store original namespace mapping for proper handling
        namespaces = {}
        for prefix, uri in ET._namespace_map.items():
            if uri in str(root.tag):
                namespaces[prefix] = uri
        
        # Also extract namespace from root element
        if root.tag.startswith('{'):
            namespace_uri = root.tag[1:root.tag.find('}')]
            namespaces[''] = namespace_uri
        
        # Remove namespace prefixes to simplify parsing but preserve structure
        for elem in root.iter():
            if '}' in str(elem.tag):
                elem.tag = elem.tag.split('}', 1)[1]
        
        # Check if this is a sitemap index (contains other sitemaps)
        sitemap_elements = root.findall('.//sitemap')
        if sitemap_elements:
            print(f"Found sitemap index with {len(sitemap_elements)} sub-sitemaps...")
            for sitemap_elem in sitemap_elements:
                loc_elem = sitemap_elem.find('loc')
                if loc_elem is not None and loc_elem.text:
                    sub_sitemap_url = loc_elem.text.strip()
                    print(f"Processing sub-sitemap: {sub_sitemap_url}")
                    try:
                        # Fetch the sub-sitemap
                        headers = {
                            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                            'Accept': 'application/xml, text/xml, */*',
                            'Accept-Language': 'en-US,en;q=0.9,*;q=0.8'
                        }
                        sub_response = requests.get(sub_sitemap_url, headers=headers, timeout=15, verify=False)
                        if sub_response.status_code == 200:
                            sub_urls = parse_sitemap(sub_response.content, base_url)
                            urls.extend(sub_urls)
                            print(f"Found {len(sub_urls)} URLs in sub-sitemap: {sub_sitemap_url}")
                        else:
                            print(f"Sub-sitemap {sub_sitemap_url} returned status {sub_response.status_code}")
                    except Exception as e:
                        logger.warning(f"Error fetching sub-sitemap {sub_sitemap_url}: {e}")
        
        # Parse URL elements - try multiple patterns to catch all variations
        url_patterns = ['.//url', './/URL', './/*[local-name()="url"]']
        url_elements = []
        
        for pattern in url_patterns:
            try:
                elements = root.findall(pattern)
                if elements:
                    url_elements.extend(elements)
                    break  # Use the first pattern that works
            except:
                continue
        
        print(f"Found {len(url_elements)} URL elements to process")
        
        for url_elem in url_elements:
            # Try multiple ways to find the location element
            loc_elem = None
            for loc_pattern in ['loc', 'LOC', './/*[local-name()="loc"]']:
                try:
                    loc_elem = url_elem.find(loc_pattern)
                    if loc_elem is not None:
                        break
                except:
                    continue
            
            if loc_elem is not None and loc_elem.text:
                url = loc_elem.text.strip()
                
                # Validate and clean the URL
                if url and is_valid_url(url, base_url):
                    urls.append(url)
                    print(f"Added URL: {url}")
        
        print(f"Total URLs extracted from sitemap: {len(urls)}")
        return list(set(urls))  # Remove duplicates
        
    except ET.ParseError as e:
        logger.warning(f"Error parsing sitemap XML: {e}")
        # Try to extract URLs using regex as fallback
        return extract_urls_with_regex(sitemap_content, base_url)
    except Exception as e:
        logger.error(f"Unexpected error parsing sitemap: {e}")
        return []


def is_valid_url(url, base_url):
    """
    Validate if URL is properly formatted and relevant
    Enhanced to handle multi-language URLs
    """
    if not url:
        return False
    
    # Basic URL validation
    if not url.startswith(('http://', 'https://')):
        return False
    
    # Parse base URL to get domain
    try:
        base_parsed = urlparse(base_url)
        url_parsed = urlparse(url)
        
        # Allow URLs from same domain or subdomains
        base_domain = base_parsed.netloc.lower()
        url_domain = url_parsed.netloc.lower()
        
        # Handle cases like www.example.com vs example.com
        if base_domain.startswith('www.'):
            base_domain = base_domain[4:]
        if url_domain.startswith('www.'):
            url_domain = url_domain[4:]
        
        # Allow exact match or subdomain
        if url_domain == base_domain or url_domain.endswith('.' + base_domain):
            return True
            
    except Exception as e:
        logger.warning(f"Error validating URL {url}: {e}")
    
    return False


def extract_urls_with_regex(content, base_url):
    """
    Fallback method to extract URLs using regex when XML parsing fails
    """
    urls = []
    
    try:
        if isinstance(content, bytes):
            content = content.decode('utf-8', errors='ignore')
        
        # Look for URLs in <loc> tags
        import re
        url_pattern = r'<loc[^>]*>(.*?)</loc>'
        matches = re.findall(url_pattern, content, re.IGNORECASE | re.DOTALL)
        
        for match in matches:
            url = match.strip()
            if is_valid_url(url, base_url):
                urls.append(url)
        
        print(f"Regex fallback found {len(urls)} URLs")
        
    except Exception as e:
        logger.error(f"Error in regex URL extraction: {e}")
    
    return urls


def find_enhanced_custom_class_elements(soup, class_filter="custom-block-element"):
    """
    Enhanced Custom Class Elements finder with detailed analysis
    Focus on PRIMARY elements only, excluding child helix elements
    """
    custom_elements = []
    
    # Find all elements with the target class
    all_elements = soup.find_all(attrs={"class": True})
    
    for element in all_elements:
        classes = element.get('class', [])
        class_string = ' '.join(classes)
        
        if class_filter.lower() in class_string.lower():
            custom_elements.append(element.name)
    
    return custom_elements


def find_enhanced_helix_elements(soup, page_source):
    """Enhanced Helix Elements finder with detailed analysis"""
    helix_elements = []
    
    # Method 1: Parse HTML for helix tags
    helix_tags = soup.find_all(lambda tag: tag.name and tag.name.startswith('helix'))
    
    for tag in helix_tags:
        helix_elements.append(tag.name)
    
    return helix_elements



def fetch_page(url):
    """Fetch webpage content using requests"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9,*;q=0.8',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }
        
        # Disable SSL verification to handle self-signed certificates
        response = requests.get(url, headers=headers, timeout=30, verify=False)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        return soup, response.text, None
        
    except Exception as e:
        logger.error(f"Error fetching page: {e}")
        return None, None, str(e)


def determine_block_category(element, classes):
    """Determine the category of the custom block"""
    class_string = ' '.join(classes).lower()
    
    if 'header' in class_string or 'navigation' in class_string or 'menu' in class_string:
        return 'Navigation/Header'
    elif 'hero' in class_string or 'banner' in class_string:
        return 'Hero/Banner'
    elif 'footer' in class_string:
        return 'Footer'
    elif 'content' in class_string or 'article' in class_string:
        return 'Content Block'
    elif 'sidebar' in class_string or 'aside' in class_string:
        return 'Sidebar'
    elif 'form' in class_string or 'input' in class_string:
        return 'Form Element'
    elif 'media' in class_string or 'image' in class_string or 'video' in class_string:
        return 'Media Block'
    elif 'card' in class_string or 'tile' in class_string:
        return 'Card/Tile'
    elif 'list' in class_string or 'grid' in class_string:
        return 'Layout/Grid'
    else:
        return 'Generic Block'
    


def generate_enhanced_label(element, classes, helix_children):
    """Generate an enhanced, descriptive label for the block"""
    tag = element.name.upper()
    element_id = element.get('id', 'no-id')
    
    # Get meaningful text content (first 50 chars)
    text_content = element.get_text(strip=True)[:50]
    text_preview = f" - '{text_content}...'" if len(text_content) > 47 else f" - '{text_content}'" if text_content else " - (no text)"
    
    # Include helix information if present
    helix_info = ""
    if helix_children:
        helix_types = list(set([child.name for child in helix_children]))
        helix_info = f" [Contains: {', '.join(helix_types)}]"
    
    return f"{tag}#{element_id}{text_preview}{helix_info}"


def calculate_content_metrics(element):
    """Calculate detailed content metrics"""
    text_content = element.get_text(strip=True)
    
    return {
        'total_text_length': len(text_content),
        'word_count': len(text_content.split()) if text_content else 0,
        'has_images': len(element.find_all('img')) > 0,
        'image_count': len(element.find_all('img')),
        'has_links': len(element.find_all('a')) > 0,
        'link_count': len(element.find_all('a')),
        'has_forms': len(element.find_all(['form', 'input', 'textarea', 'select'])) > 0,
        'form_element_count': len(element.find_all(['form', 'input', 'textarea', 'select'])),
        'nesting_depth': calculate_nesting_depth(element)
    }


def calculate_nesting_depth(element):
    """Calculate the maximum nesting depth"""
    def get_depth(elem, current_depth=0):
        if not elem.children:
            return current_depth
        max_child_depth = current_depth
        for child in elem.children:
            if hasattr(child, 'children'):
                child_depth = get_depth(child, current_depth + 1)
                max_child_depth = max(max_child_depth, child_depth)
        return max_child_depth
    
    return get_depth(element)


def extract_tag_name_from_match(html_match):
    """Extract tag name from regex match"""
    match = re.match(r'<(helix-[^>\s]+)', html_match, re.IGNORECASE)
    return match.group(1) if match else 'helix-unknown'


def extract_text_from_helix_match(html_match):
    """Extract text content from helix HTML match"""
    try:
        soup = BeautifulSoup(html_match, 'html.parser')
        return soup.get_text(strip=True)
    except:
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