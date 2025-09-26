from django.shortcuts import render
from rest_framework.authtoken.models import Token
from django.contrib.auth import authenticate
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.authentication import TokenAuthentication
from rest_framework.permissions import IsAuthenticated
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from tag_manager_component.models import TagMapper
import requests
import json
import re
import pandas as pd
import os
from .rag import get_rag_instance, search_migrations, get_migration_suggestion, get_rag_statistics, reset_rag
from .ollama_api import call_ollama as ollama_call_ollama, create_migration_prompt

# Custom authentication class to use Bearer tokens
class BearerTokenAuthentication(TokenAuthentication):
    keyword = 'Bearer'

# API view to handle migration from V1 to V2 components
class MigrateV1ToV2View(APIView):
    authentication_classes = [BearerTokenAuthentication]
    permission_classes = [IsAuthenticated]

    @method_decorator(csrf_exempt)
    def post(self, request):
        """
        Handle POST requests to migrate V1 components to V2 components.
        Extracts V1 body, CSS, and JS from the request, applies transformations,
        and returns the migrated V2 content.
        """
        v1_body = request.data.get('v1_body', '')
        v1_css = request.data.get('v1_css', '')
        v1_js = request.data.get('v1_js', '')

        # If V1 body is provided, perform migration
        if v1_body.strip():
            output_v2 = migrate(v1_body)
            # print("Migration Output:", output_v2)
            migrated_body = output_v2.get("migrated_v2", "")

            # print("FUIII")
            # print(migrated_body)

        try:
            # Fetch tag mappings from the database
            tag_mappings = TagMapper.objects.all()

            # Initialize V2 content with V1 content
            v2_body = migrated_body if output_v2 else v1_body
            v2_css = v1_css
            v2_js = v1_js

            # Replace V1 components with V2 components using tag mappings
            for mapping in tag_mappings:
                v2_body = v2_body.replace(mapping.v1_component_name, mapping.v2_component_name)
                v2_css = v2_css.replace(mapping.v1_component_name, mapping.v2_component_name)
                v2_js = v2_js.replace(mapping.v1_component_name, mapping.v2_component_name)

        except Exception as e:
            # Return error response if an exception occurs
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        # Return the migrated V2 content
        return Response({
            'v2_body': v2_body,
            'v2_css': v2_css,
            'v2_js': v2_js
        }, status=status.HTTP_200_OK)


# RAG-based migration views
class RAGMigrateV1ToV2View(APIView):
    """
    RAG-enhanced migration endpoint that uses semantic search and AI assistance.
    """
    authentication_classes = [BearerTokenAuthentication]
    permission_classes = [IsAuthenticated]

    @method_decorator(csrf_exempt)
    def post(self, request):
        """
        Handle POST requests to migrate V1 components to V2 using RAG system.
        Uses semantic search to find similar migrations and optionally Ollama for enhancement.
        """
        try:
            v1_html = request.data.get('v1_html', '')
            use_ollama = request.data.get('use_ollama', True)
            
            if not v1_html.strip():
                return Response({
                    'error': 'v1_html is required'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Get RAG-based migration suggestion
            suggestion = get_migration_suggestion(v1_html, use_ollama=use_ollama)
            
            if 'error' in suggestion:
                return Response({
                    'error': f"RAG migration failed: {suggestion['error']}"
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
            return Response({
                'input_v1': suggestion['input_v1'],
                'suggested_v2': suggestion['suggested_v2'],
                'confidence_score': suggestion['confidence_score'],
                'method': suggestion['method'],
                'similar_examples': suggestion['similar_examples'],
                'timestamp': json.dumps(pd.Timestamp.now(), default=str)
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response({
                'error': f'RAG migration error: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class RAGSearchView(APIView):
    """
    Search for similar migration examples using RAG.
    """
    authentication_classes = [BearerTokenAuthentication]
    permission_classes = [IsAuthenticated]

    @method_decorator(csrf_exempt)
    def post(self, request):
        """
        Search for similar migration examples based on query.
        """
        try:
            query = request.data.get('query', '')
            n_results = request.data.get('n_results', 5)
            
            if not query.strip():
                return Response({
                    'error': 'query is required'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Search for similar migrations
            similar_migrations = search_migrations(query, n_results=n_results)
            
            return Response({
                'query': query,
                'n_results': len(similar_migrations),
                'migrations': similar_migrations
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response({
                'error': f'RAG search error: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class RAGStatsView(APIView):
    """
    Get RAG system statistics and information.
    """
    authentication_classes = [BearerTokenAuthentication]
    permission_classes = [IsAuthenticated]

    @method_decorator(csrf_exempt)
    def get(self, request):
        """
        Get RAG system statistics.
        """
        try:
            stats = get_rag_statistics()
            
            if 'error' in stats:
                return Response({
                    'error': f"Could not get RAG stats: {stats['error']}"
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
            return Response(stats, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response({
                'error': f'RAG stats error: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class RAGResetView(APIView):
    """
    Reset and reinitialize the RAG system.
    """
    authentication_classes = [BearerTokenAuthentication]
    permission_classes = [IsAuthenticated]

    @method_decorator(csrf_exempt)
    def post(self, request):
        """
        Reset the RAG system and reload data.
        """
        try:
            success = reset_rag()
            
            if success:
                return Response({
                    'message': 'RAG system reset successfully',
                    'success': True
                }, status=status.HTTP_200_OK)
            else:
                return Response({
                    'error': 'Failed to reset RAG system',
                    'success': False
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
        except Exception as e:
            return Response({
                'error': f'RAG reset error: {str(e)}',
                'success': False
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# View to handle token generation for authentication
def get_token_form(request):
    """
    Render a form to generate authentication tokens.
    Accepts username and password, and returns a token if authentication is successful.
    """
    token = None
    error = None
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(username=username, password=password)
        if user:
            token, created = Token.objects.get_or_create(user=user)
        else:
            error = 'Invalid username or password.'
    return render(request, 'api_component/get_token.html', {'token': token.key if token else None, 'error': error})


def extract_helix_parent_elements(content):
    """
    Extract helix parent elements from content using regex pattern matching.
    
    Args:
        content (str): HTML content to parse
        
    Returns:
        list: List of extracted helix parent elements
    """
    tag_pattern = re.compile(r'<(helix-[a-zA-Z0-9\-]+)([^>]*)>', re.DOTALL)
    end_tag_template = r'</{tag}>'

    tags = []
    for m in tag_pattern.finditer(content):
        tag = m.group(1)
        start = m.start()
        end_tag = f'</{tag}>'
        stack = 1
        pos = m.end()
        while stack > 0:
            next_open = content.find(f'<{tag}', pos)
            next_close = content.find(end_tag, pos)
            if next_close == -1:
                break
            if next_open != -1 and next_open < next_close:
                stack += 1
                pos = next_open + 1
            else:
                stack -= 1
                pos = next_close + len(end_tag)
        end = pos
        tags.append((start, end, tag))

    parent_ranges = []
    for i, (start_i, end_i, tag_i) in enumerate(tags):
        is_parent = True
        for j, (start_j, end_j, tag_j) in enumerate(tags):
            if i != j and start_i > start_j and end_i < end_j:
                is_parent = False
                break
        if is_parent:
            parent_ranges.append((start_i, end_i))

    elements = []
    for start, end in parent_ranges:
        elements.append(content[start:end])

    return elements


def get_mapping_by_tag(tag_name):
    """
    Load CSS mapping data based on tag name search.
    Searches for the tag in V1 data and returns the corresponding V1 and V2 tag values.
    
    Args:
        tag_name (str): The V1 tag name to search for (e.g., 'helix-video')
    
    Returns:
        dict or None: Dictionary containing 'v1' and 'v2' tag names if found, None otherwise
    """
    try:
        # First try to use RAG to search for migration examples
        try:
            rag_results = search_migrations(tag_name, n_results=1)
            print("FOUND >>>>>>>>") 
            print(tag_name)
            print("RAG RESULTS>>>>>>")
            print(rag_results)

            if rag_results and len(rag_results) > 0:
                # Return the first matching result from RAG
                best_match = rag_results[0]
                return {
                    'v1': best_match.get('v1', ''),
                    'v2': best_match.get('v2', '')
                }
        except Exception as e:
            print(f"RAG search failed for tag {tag_name}: {str(e)}")
            # Continue to fallback CSV search below

        # Load the CSV file containing V1 to V2 mappings
        csv_file_path = os.path.join(os.path.dirname(__file__), 'v1_v2.csv')
        df = pd.read_csv(csv_file_path)
        
        # Search for the tag in V1 column content
        for _, row in df.iterrows():
            v1_content = row['v1']
            v2_content = row['v2']
            
            # Check if the tag name appears in the V1 content
            if tag_name in v1_content:
                # Return the full V1 and V2 content from the CSV
                return {'v1': v1_content, 'v2': v2_content}
        
        # If no direct match found, try partial matching
        for _, row in df.iterrows():
            v1_content = row['v1']
            v2_content = row['v2']
            
            # Extract V1 tags from the content
            v1_tags = re.findall(r'<(helix-[^>\s]+)', v1_content)
            if tag_name in v1_tags:
                return {'v1': v1_content, 'v2': v2_content}
        
        return None
        
    except FileNotFoundError:
        print(f"CSV file not found: {csv_file_path}")
        return None
    except Exception as e:
        print(f"Error loading CSS mapping: {str(e)}")
        return None
    
def extract_and_map_helix_elements(migrated_content):
        """
        Extract helix elements from migrated content and get their mappings.
        
        Args:
            migrated_content (str): The HTML content to extract helix elements from
        
        Returns:
            dict: Mapping dictionary with V1 to V2 transformations
        """
        
        # Extract all helix elements from the content
        helix_elements = set(re.findall(r'<(helix-[^>\s]+)', migrated_content))

        # print("Helix elements in migrated content:", helix_elements)

        # Get mapping values for each helix element with optimized lookup
        mapping_values = {
            element: get_mapping_by_tag(element) 
            for element in helix_elements
        }

        # Filter out None values and log results
        mapping_values = {k: v for k, v in mapping_values.items() if v}
        for element in helix_elements:
            if element in mapping_values:
                print(f"Found mapping for {element}: {mapping_values[element]}")
            else:
                print(f"No mapping found for {element}")

        # print("All mapping values:", mapping_values)

        # Convert mapping_values to the required format using V1 and V2 content
        mapping = {
            mapping_data['v1']: mapping_data['v2']
            for mapping_data in mapping_values.values()
            if 'v1' in mapping_data and 'v2' in mapping_data
        }
        
        return mapping

# Function to migrate V1 content to V2 content
def migrate(query):
    """
    Perform migration of V1 content to V2 content.
    Applies transformations using Ollama AI with CSV mappings.
    """
    csv_file_path = os.path.join(os.path.dirname(__file__), 'v1_v2.csv')
    df = pd.read_csv(csv_file_path)
    migrated_content = query

    # Load the CSV mapping file
    try:
        mapping = dict(zip(df['v1'], df['v2']))
    except FileNotFoundError:
        print("v1_v2.csv not found. Please create the file.")
        return {"input_v1": query, "migrated_v2": query, "migration_notes": "CSV file not found."}

    # Extract helix parent elements
    helix_parents = extract_helix_parent_elements(migrated_content)
    
    # Extract all helix elements from the content
    helix_elements = set(re.findall(r'<(helix-[^>\s]+)', migrated_content))
    
    updated_content = migrated_content
    for idx, el in enumerate(helix_parents, 1):
        mapping = extract_and_map_helix_elements(el)
        migration_prompt = create_migration_prompt(el, mapping)

        # print("PROMPT IS >>>>>>>>>>")
        # print(migration_prompt)

        migrated_text = ollama_call_ollama(migration_prompt)

        # print("MIGRATED TEXT IS >>>>>>>>>>")
        # print(migrated_text)
        
        if migrated_text:
            updated_content = updated_content.replace(el, migrated_text)
            
    migrated_content = updated_content

    # Fetch V1 and V2 component details from the database for validation
    v1_component_details = {}
    try:
        tag_mappings = TagMapper.objects.filter(v1_component_name__in=helix_elements).values(
            'v1_component_name', 'v2_component_name', 'v1_component_attributes', 'v2_component_attributes'
        )
        for mapping in tag_mappings:
            v1_key = mapping['v1_component_name']
            v2_key = mapping['v2_component_name']
            v1_component_attribute = mapping['v1_component_attributes']
            v2_component_attributes = mapping['v2_component_attributes']
            v1_component_details[v1_key] = [v2_key, v1_component_attribute, v2_component_attributes]
             
    except Exception as e:
        print(f"Error fetching component details: {str(e)}")

    # Extract all helix elements from the migrated content
    helix_elements = re.findall(r'<(helix-[^>\s]+)', migrated_content)
    print("Helix elements in migrated content:", helix_elements)
    
    return {
        "input_v1": query,
        "migrated_v2": migrated_content,
        "migration_notes": "Performed AI-powered migration using Ollama with CSV mappings."
    }


