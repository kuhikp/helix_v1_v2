from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, F
import json

from .models import Tag, TagMapper
from site_manager.models import SiteListDetails, SiteMetaDetails

@login_required
def update_usage_counts(request):
    """
    Update the used_in_website count for Tag and TagMapper models by analyzing
    all SiteListDetails and SiteMetaDetails data.
    """
    if request.method == 'POST':
        try:
            # Initialize counters
            tag_counts = {}
            tag_mapper_counts = {}
            
            # Process SiteListDetails
            site_details = SiteListDetails.objects.all()
            total_sites = site_details.count()
            processed_sites = 0
            
            # First, reset all counts to zero
            Tag.objects.all().update(used_in_website=0)
            TagMapper.objects.all().update(used_in_website=0)
            
            # Process each site
            for site in site_details:
                processed_sites += 1
                print(f"Processing website: {site.website_url}")
                
                # Process V1 components
                if site.helix_v1_component:
                    try:
                        components = json.loads(site.helix_v1_component)
                        if isinstance(components, list):
                            for component in components:
                                if isinstance(component, str):
                                    # Update tag counts
                                    if component not in tag_counts:
                                        tag_counts[component] = 0
                                    tag_counts[component] += 1
                    except json.JSONDecodeError:
                        print("Invalid JSON in helix_v1_component")
                        # Handle non-JSON data
                        pass
                
                # Process V2 compatible components
                if site.helix_v2_compatible_component:
                    try:
                        components = json.loads(site.helix_v2_compatible_component)
                        if isinstance(components, list):
                            for component in components:
                                if isinstance(component, str):
                                    # Update tag counts
                                    if component not in tag_counts:
                                        tag_counts[component] = 0
                                    tag_counts[component] += 1
                    except json.JSONDecodeError:
                        # Handle non-JSON data
                        print("Invalid JSON in helix_v2_compatible_component")
                        pass
                
                # Process V2 non-compatible components
                if site.helix_v2_non_compatible_component:
                    try:
                        components = json.loads(site.helix_v2_non_compatible_component)
                        if isinstance(components, list):
                            for component in components:
                                if isinstance(component, str):
                                    # Update tag counts
                                    if component not in tag_counts:
                                        tag_counts[component] = 0
                                    tag_counts[component] += 1
                    except json.JSONDecodeError:
                        # Handle non-JSON data
                        print("Invalid JSON in helix_v2_non_compatible_component")
                        pass
            
            # Also process SiteMetaDetails for more detailed data
            # meta_details = SiteMetaDetails.objects.all()
            # total_meta = meta_details.count()
            processed_meta = 0
            
            # for meta in meta_details:
            #     processed_meta += 1
                
            #     # Process fields with component data
            #     for field_name in ['helix_v1_component', 'helix_v2_compatible_component', 'helix_v2_non_compatible_component', 'custom_component']:
            #         field_value = getattr(meta, field_name)
            #         if field_value:
            #             try:
            #                 components = json.loads(field_value)
            #                 if isinstance(components, list):
            #                     for component in components:
            #                         if isinstance(component, str):
            #                             # Update tag counts
            #                             if component not in tag_counts:
            #                                 tag_counts[component] = 0
            #                             tag_counts[component] += 1
            #             except json.JSONDecodeError:
            #                 # Handle non-JSON data
            #                 print(f"Invalid JSON in {field_name} for meta {meta.id}")
            #                 pass
            
            # Print out all the tags found and their counts
            print("Tag counts summary:")
            for tag_name, count in tag_counts.items():
                print(f"  {tag_name}: {count}")
            
            # Update Tag counts in database
            for tag_name, count in tag_counts.items():
                # Update by name (assuming tag names are unique - if not, you may need to add version filter)
                # Use direct update rather than F expression to ensure exact count
                tags_updated = Tag.objects.filter(name=tag_name).update(used_in_website=count)
                print(f"Updated {tags_updated} tags with name '{tag_name}' to count {count}")
            
            # Process TagMapper objects
            # For simplicity, we'll just count how many sites use a component that could be mapped
            tag_mappers = TagMapper.objects.all()
            
            for mapper in tag_mappers:
                v1_component = mapper.v1_component_name
                if v1_component in tag_counts:
                    print(f"Updating mapper for {v1_component} = {tag_counts[v1_component]}")
                    mapper.used_in_website = tag_counts[v1_component]
                    mapper.save()
                else:
                    print(f"No counts found for mapper component '{v1_component}'")
                    mapper.used_in_website = 0
                    mapper.save()
            
            messages.success(request, f"Successfully updated usage counts for {Tag.objects.count()} tags and {TagMapper.objects.count()} tag mappers.")
            # messages.info(request, f"Processed {processed_sites} sites and {processed_meta} page details.")
            
        except Exception as e:
            messages.error(request, f"Error updating usage counts: {str(e)}")
        
        return redirect('tag_list')
    
    # GET request - show confirmation page
    total_tags = Tag.objects.count()
    total_mappers = TagMapper.objects.count()
    total_sites = SiteListDetails.objects.count()
    
    return render(request, 'tag_manager_component/update_counts_confirmation.html', {
        'total_tags': total_tags,
        'total_mappers': total_mappers,
        'total_sites': total_sites,
    })
