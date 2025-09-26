# API Component Views Documentation

## Overview
The `api_component/views.py` file contains the core functionality for migrating V1 components to V2 components using machine learning embeddings, vector similarity search, and rule-based transformations.

## Table of Contents
1. [Authentication Classes](#authentication-classes)
2. [API Views](#api-views)
3. [Helper Functions](#helper-functions)
4. [Migration Process](#migration-process)
5. [Environment Variables](#environment-variables)
6. [Error Handling](#error-handling)

---

## Authentication Classes

### `BearerTokenAuthentication`
```python
class BearerTokenAuthentication(TokenAuthentication):
    keyword = 'Bearer'
```

**Purpose**: Custom authentication class that extends Django REST Framework's TokenAuthentication to use "Bearer" prefix instead of "Token".

**Usage**: Used in API endpoints to authenticate requests with Bearer tokens.

---

## API Views

### `MigrateV1ToV2View`
**Type**: APIView  
**Authentication**: Bearer Token Required  
**Method**: POST

**Purpose**: Main endpoint for migrating V1 component code to V2 format.

#### Request Payload:
```json
{
    "v1_body": "V1 HTML content",
    "v1_css": "V1 CSS content", 
    "v1_js": "V1 JavaScript content"
}
```

#### Response:
```json
{
    "v2_body": "Migrated V2 HTML content",
    "v2_css": "Migrated V2 CSS content",
    "v2_js": "Migrated V2 JavaScript content"
}
```

#### Process Flow:
1. Extract V1 content from request
2. If V1 body exists, call `migrate()` function for advanced migration
3. Apply database tag mappings for basic replacements
4. Return migrated V2 content

---

## Helper Functions

### `get_token_form(request)`
**Purpose**: Renders a form for generating authentication tokens.

**Functionality**:
- GET: Display token generation form
- POST: Authenticate user and generate token

**Returns**: Rendered template with token or error message

---

### `initialize_qdrant_client()`
**Purpose**: Initialize vector database client and load migration data.

**Process**:
1. Create in-memory Qdrant client
2. Load V1→V2 mappings from CSV file (`v1_v2.csv`)
3. Generate embeddings for all V1 components
4. Create vector collection with cosine similarity
5. Upload vectors and metadata to collection

**Returns**: `(qdrant_client, dataframe)`

**Dependencies**:
- `v1_v2.csv` file in same directory
- `COLLECTION_NAME` environment variable
- Working `generate_embedding()` function

---

### `generate_embedding(text)`
**Purpose**: Generate vector embeddings for text using external LLM service.

**Process**:
1. Send text to embedding API endpoint
2. Stream response and extract embedding vector
3. Handle JSON parsing errors gracefully

**Environment Variables Required**:
- `MIGRATION_CLIENT_ENDPOINT`: API endpoint for embeddings
- `LLM_MODEL`: Model name to use for embeddings

**Returns**: List of floats representing the text embedding

**Error Handling**: Raises exception on API errors, prints detailed error messages

---

### `migrate(query)`
**Purpose**: Advanced migration function using AI and rule-based transformations.

#### Migration Steps:

##### 1. ID Attribute Handling
- Extracts ID attributes (`id`, `account-id`, `media-id`) from HTML
- Replaces with dummy values during processing
- Restores original values after transformation

##### 2. Embedding-Based Matching
- Generates embedding for input query
- Searches vector database for similar V1 patterns
- Applies top 3 matches as replacements

##### 3. Tag Transformations
- Maps V1 tag names to V2 tag names
- Updates opening and closing tags
- Example: `<helix-video>` → `<helix-media-player>`

##### 4. Data Attribute Transformations
- Updates `data-gjs-type` attributes
- Maps V1 component types to V2 types

##### 5. Attribute Management
- **Additions**: Adds new attributes required by V2 components
- **Deletions**: Removes deprecated V1-only attributes

##### 6. ID Restoration
- Restores original ID values using dummy-to-original mapping
- Applies to transformed V2 tag names

**Returns**: Dictionary with migration results:
```json
{
    "input_v1": "original V1 content",
    "migrated_v2": "transformed V2 content", 
    "migration_notes": "transformation summary"
}
```

---

## Migration Process Flow

```
1. Input V1 Content
   ↓
2. Extract & Replace IDs with Dummies
   ↓
3. Generate Embedding Vector
   ↓
4. Search Vector Database for Similar Patterns
   ↓
5. Apply Best Matches (Pattern Replacement)
   ↓
6. Transform Tag Names (helix-* components)
   ↓
7. Update Data Attributes (data-gjs-type)
   ↓
8. Add New V2 Attributes
   ↓
9. Remove Deprecated V1 Attributes
   ↓
10. Restore Original IDs
    ↓
11. Return Migrated V2 Content
```

---

## Environment Variables

### Required Variables:
- `MIGRATION_CLIENT_ENDPOINT`: URL for embedding generation service
- `LLM_MODEL`: Model name for embeddings (e.g., "mistral")
- `COLLECTION_NAME`: Name for Qdrant vector collection

### Optional Variables:
- `OLLAMA_BASE_URL`: Base URL for Ollama API (used in other functions)
- `OLLAMA_API_KEY`: API key for Ollama service

---

## Error Handling

### Common Errors and Solutions:

#### 1. Missing CSV File
**Error**: `FileNotFoundError` when loading `v1_v2.csv`
**Solution**: Ensure CSV file exists in `api_component/` directory

#### 2. Embedding API Failures
**Error**: `RequestException` during embedding generation
**Solutions**:
- Check `MIGRATION_CLIENT_ENDPOINT` is accessible
- Verify `LLM_MODEL` is valid
- Ensure embedding service is running

#### 3. Vector Database Issues
**Error**: Qdrant client initialization fails
**Solutions**:
- Check memory availability for in-memory database
- Verify embedding dimensions are consistent

#### 4. Authentication Errors
**Error**: 401/403 responses
**Solutions**:
- Verify Bearer token is valid and not expired
- Check user permissions

---

## Data Flow Diagram

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Client App    │────│  Django API     │────│  Embedding API  │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                              │
                              ▼
                       ┌─────────────────┐
                       │  Qdrant Vector  │
                       │    Database     │
                       └─────────────────┘
                              │
                              ▼
                       ┌─────────────────┐
                       │   v1_v2.csv     │
                       │  Training Data  │
                       └─────────────────┘
```

---

## File Dependencies

```
api_component/
├── views.py              # Main logic
├── v1_v2.csv            # Training data for migrations
├── urls.py              # URL routing
└── templates/
    └── api_component/
        └── get_token.html  # Token generation form
```

---

## Usage Examples

### 1. Generate Authentication Token
```bash
curl -X POST http://localhost:8010/api/token/ \
  -d "username=admin&password=password"
```

### 2. Migrate V1 to V2
```bash
curl -X POST http://localhost:8010/api/migrate/ \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "v1_body": "<helix-video account-id=\"123\">Content</helix-video>",
    "v1_css": ".helix-video { color: blue; }",
    "v1_js": "console.log(\"v1 script\");"
  }'
```

### Response:
```json
{
    "v2_body": "<helix-media-player account-id=\"123\">Content</helix-media-player>",
    "v2_css": ".helix-media-player { color: blue; }",
    "v2_js": "console.log(\"v2 script\");"
}
```

---

## Performance Considerations

1. **Vector Search**: Limited to top 3 matches for performance
2. **Memory Usage**: In-memory Qdrant database - suitable for small datasets
3. **API Timeouts**: Embedding generation may be slow for large content
4. **Caching**: Consider caching embeddings for frequently migrated patterns

---

## Future Improvements

1. **Persistent Vector Database**: Move from in-memory to persistent storage
2. **Batch Processing**: Support multiple migrations in single request  
3. **Migration Validation**: Add post-migration validation checks
4. **Performance Metrics**: Track migration success rates and timing
5. **Custom Rules Engine**: Allow user-defined transformation rules

---

## Troubleshooting Guide

### Debug Mode
Enable detailed logging by setting environment variable:
```bash
export DJANGO_LOG_LEVEL=DEBUG
```

### Common Issues:

1. **Empty Migration Results**
   - Check if `v1_v2.csv` has relevant training data
   - Verify embedding API is generating valid vectors

2. **Slow Performance** 
   - Reduce vector search limit from 3 to 1
   - Optimize embedding generation endpoint

3. **Memory Errors**
   - Reduce dataset size in `v1_v2.csv`
   - Consider switching to persistent Qdrant instance

---

This documentation provides a comprehensive guide to understanding and working with the API component migration system. For specific implementation details, refer to the inline comments in the source code.
