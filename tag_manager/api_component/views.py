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
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams
import os

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
            migrated_body = output_v2.get("migrated_v2", "")

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

# Function to initialize the Qdrant client and load data from CSV
def initialize_qdrant_client():
    """
    Initialize the Qdrant client, load data from the CSV file, and upload it to the Qdrant collection.
    Returns the Qdrant client instance and the loaded DataFrame.
    """
    qdrant = QdrantClient(":memory:")
    csv_file_path = os.path.join(os.path.dirname(__file__), 'v1_v2.csv')
    df = pd.read_csv(csv_file_path)

    # Prepare payloads and vectors for Qdrant
    payloads = [{'v2': v2} for v2 in df['v2']]
    vectors = [generate_embedding(v1) for v1 in df['v1'].tolist()]

    # Check if the collection exists and delete it if necessary
    collection_name = os.getenv('COLLECTION_NAME')
    if qdrant.collection_exists(collection_name=collection_name):
        qdrant.delete_collection(collection_name=collection_name)

    # Create a new collection in Qdrant
    qdrant.create_collection(
        collection_name=collection_name,
        vectors_config=VectorParams(
            size=len(vectors[0]),
            distance="Cosine",
            on_disk=True
        )
    )

    collection_info = qdrant.get_collection(collection_name=collection_name)
    vector_count = collection_info.vectors_count

    # Upload data to the Qdrant collection
    qdrant.upload_collection(
        collection_name=collection_name,
        vectors=vectors,
        payload=payloads
    )

    return qdrant, df

# Function to generate embeddings using a language model
def generate_embedding(text):
    """
    Generate an embedding for the given text using a language model.
    Sends a request to the migration client endpoint and returns the embedding vector.
    """
    url = os.getenv('MIGRATION_CLIENT_ENDPOINT')
    payload = {
        "model": os.getenv('LLM_MODEL'),
        "prompt": text
    }
    try:
        response = requests.post(url, json=payload, stream=True)
        response.raise_for_status()
        embedding = []
        for line in response.iter_lines(decode_unicode=True):
            if line:
                try:
                    data = json.loads(line)
                    if "embedding" in data:
                        embedding = data["embedding"]
                        break
                except json.JSONDecodeError:
                    pass
        return embedding
    except requests.exceptions.RequestException:
        raise

# Function to migrate V1 content to V2 content
def migrate(query):
    """
    Perform migration of V1 content to V2 content.
    Applies transformations such as tag replacements, attribute updates, and embedding-based matching.
    """
    # Extract and replace ID attributes with dummy values
    id_attributes = re.findall(r'(<helix-[^>\s]+[^>]*\s([^=\s]*(?:id|account-id|media-id)[^=\s]*)="([^"]*)")', query)
    id_replacements = {}
    for match in id_attributes:
        if len(match) == 3:
            full_match, attr_name, attr_value = match
            dummy_value = f"dummy-{attr_name}"
            tag_name = re.search(r'<(helix-[^>\s]+)', full_match).group(1)
            if tag_name not in id_replacements:
                id_replacements[tag_name] = {}
            id_replacements[tag_name][attr_value] = dummy_value
            query = query.replace(full_match, full_match.replace(f'{attr_name}="{attr_value}"', f'{attr_name}="{dummy_value}"'))

    # Generate embedding for the query
    # q_vec = generate_embedding(query)
    csv_file_path = os.path.join(os.path.dirname(__file__), 'v1_v2.csv')
    # qdrant, df = initialize_qdrant_client()
    df = pd.read_csv(csv_file_path)
    # result = qdrant.query_points(collection_name=os.getenv('COLLECTION_NAME'), query=q_vec, limit=1)
    migrated_content = query

    # # Replace V1 patterns with V2 replacements based on Qdrant results
    # for match in result.points:
    #     v1_pattern = df[df['v2'] == match.payload['v2']]['v1'].iloc[0]
    #     v2_replacement = match.payload['v2']
    #     if v1_pattern in migrated_content:
    #         migrated_content = migrated_content.replace(v1_pattern, v2_replacement)

    # Perform additional transformations (e.g., tag and attribute updates)
    helix_transformations = {}
    for _, row in df.iterrows():
        v1_tags = re.findall(r'<(helix-[^>\s]+)', row['v1'])
        v2_tags = re.findall(r'<(helix-[^>\s]+)', row['v2'])
        for v1_tag in v1_tags:
            for v2_tag in v2_tags:
                if v1_tag != v2_tag:
                    helix_transformations[v1_tag] = v2_tag

    for v1_tag, v2_tag in helix_transformations.items():
        migrated_content = re.sub(f'<{v1_tag}([^>]*?)>', f'<{v2_tag}\\1>', migrated_content)
        migrated_content = re.sub(f'</{v1_tag}>', f'</{v2_tag}>', migrated_content)

    gjs_type_transformations = {}
    for _, row in df.iterrows():
        v1_types = re.findall(r'data-gjs-type="([^"]*)"', row['v1'])
        v2_types = re.findall(r'data-gjs-type="([^"]*)"', row['v2'])
        for v1_type in v1_types:
            for v2_type in v2_types:
                if v1_type != v2_type:
                    gjs_type_transformations[v1_type] = v2_type

    for v1_type, v2_type in gjs_type_transformations.items():
        migrated_content = migrated_content.replace(f'data-gjs-type="{v1_type}"', f'data-gjs-type="{v2_type}"')

    attribute_additions = {}
    attributes_deletion = {}
    for _, row in df.iterrows():
        v1_matches = re.findall(r'<(helix-[^>\s]+)([^>]*)>', row['v1'])
        v2_matches = re.findall(r'<(helix-[^>\s]+)([^>]*)>', row['v2'])
        for v1_tag, v1_attrs in v1_matches:
            for v2_tag, v2_attrs in v2_matches:
                old_attrs = set(re.findall(r'(\w+(?:-\w+)*)="[^"]*"', v1_attrs)) - set(re.findall(r'(\w+(?:-\w+)*)="[^"]*"', v2_attrs))
                for attr in old_attrs:
                    attr_match = re.search(f'{attr}="([^"]*)"', v1_attrs)
                    if attr_match:
                        if v1_tag not in attributes_deletion:
                            attributes_deletion[v1_tag] = []
                        attributes_deletion[v1_tag].append(f'{attr}="{attr_match.group(1)}"')
                new_attrs = set(re.findall(r'(\w+(?:-\w+)*)="[^"]*"', v2_attrs)) - set(re.findall(r'(\w+(?:-\w+)*)="[^"]*"', v1_attrs))
                for attr in new_attrs:
                    attr_match = re.search(f'{attr}="([^"]*)"', v2_attrs)
                    if attr_match:
                        if v2_tag not in attribute_additions:
                            attribute_additions[v2_tag] = []
                        attribute_additions[v2_tag].append(f'{attr}="{attr_match.group(1)}"')

    for tag, attrs in attribute_additions.items():
        for attr in attrs:
            if tag in migrated_content and attr.split('=')[0] not in migrated_content:
                migrated_content = re.sub(rf'(<{tag}[^>]*?)>', rf'\1 {attr}>', migrated_content)

    for v1_tag, attrs in attributes_deletion.items():
        for attr in attrs:
            v2_tag = helix_transformations[v1_tag]
            attr_name = attr.split('=')[0]
            migrated_content = re.sub(rf'(<{v2_tag}[^>]*?)\s+{attr_name}="[^"]*"', r'\1', migrated_content)

    for tag_name, replacements in id_replacements.items():
        v2_tag = helix_transformations.get(tag_name, tag_name)
        for original_id, dummy_id in replacements.items():
            for attr_name in replacements:
                attr_name = dummy_id.replace("dummy-", "")
                migrated_content = re.sub(
                    rf'(<{v2_tag}[^>]*?)\s+{attr_name}="{dummy_id}"',
                    rf'\1 {attr_name}="{original_id}"',
                    migrated_content
                )

    return {
        "input_v1": query,
        "migrated_v2": migrated_content,
        "migration_notes": "Performed direct tag transformation based on V1 to V2 mappings."
    }
