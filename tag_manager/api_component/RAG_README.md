# RAG System for Helix Component Migration

This RAG (Retrieval-Augmented Generation) system provides intelligent migration suggestions for converting Helix v1 components to v2 components using semantic search and AI assistance.

## Overview

The RAG system:
1. **Loads** migration data from `v1_v2.csv`
2. **Creates embeddings** and stores them in ChromaDB for semantic search
3. **Provides similarity search** to find similar component migrations
4. **Integrates with Ollama** for enhanced AI-powered migration suggestions
5. **Offers API endpoints** for seamless integration with your applications

## Features

- **Semantic Search**: Find similar component migrations based on HTML structure and attributes
- **AI Enhancement**: Optional Ollama integration for improved migration suggestions
- **High Performance**: ChromaDB for fast vector similarity search
- **Django Integration**: Ready-to-use API endpoints with authentication
- **Management Commands**: Easy initialization and maintenance
- **Comprehensive Logging**: Detailed logging for debugging and monitoring

## Installation

### Prerequisites

Ensure you have the following dependencies installed:

```bash
pip install chromadb beautifulsoup4 requests
```

These are already included in the `requirements.txt` file.

### Setup

1. **Initialize the RAG system**:
   ```bash
   python manage.py manage_rag --init
   ```

2. **Verify installation**:
   ```bash
   python manage.py manage_rag --stats
   ```

3. **Test the system**:
   ```bash
   cd api_component
   python test_rag.py
   ```

## Usage

### API Endpoints

All endpoints require Bearer token authentication.

#### 1. RAG-based Migration (`POST /api_component/rag/migrate/`)

Migrate v1 components to v2 using RAG and optional AI enhancement.

**Request:**
```json
{
    "v1_html": "<helix-image alt=\"Test\" src=\"image.jpg\"></helix-image>",
    "use_ollama": true
}
```

**Response:**
```json
{
    "input_v1": "<helix-image alt=\"Test\" src=\"image.jpg\"></helix-image>",
    "suggested_v2": "<helix-core-image alt=\"Test\" img-src=\"image.jpg\"></helix-core-image>",
    "confidence_score": 0.95,
    "method": "rag_plus_ollama",
    "similar_examples": [...],
    "timestamp": "2024-12-09T10:30:00Z"
}
```

#### 2. Search Similar Migrations (`POST /api_component/rag/search/`)

Search for similar migration examples.

**Request:**
```json
{
    "query": "helix-image",
    "n_results": 5
}
```

**Response:**
```json
{
    "query": "helix-image",
    "n_results": 3,
    "migrations": [
        {
            "id": "migration_0_a1b2c3d4",
            "v1": "<helix-image...>",
            "v2": "<helix-core-image...>",
            "v1_component": "helix-image",
            "v2_component": "helix-core-image",
            "similarity_score": 0.98,
            "attributes_count": 5
        }
    ]
}
```

#### 3. System Statistics (`GET /api_component/rag/stats/`)

Get RAG system statistics and information.

**Response:**
```json
{
    "total_migrations": 150,
    "chromadb_documents": 150,
    "component_types": 12,
    "component_counts": {
        "helix-image": 25,
        "helix-video": 18,
        "helix-accordion": 12
    },
    "csv_path": "/path/to/v1_v2.csv",
    "persist_directory": "/path/to/chroma_db",
    "is_initialized": true
}
```

#### 4. Reset RAG System (`POST /api_component/rag/reset/`)

Reset and reinitialize the RAG system.

**Response:**
```json
{
    "message": "RAG system reset successfully",
    "success": true
}
```

### Python API

You can also use the RAG system directly in Python:

```python
from api_component.rag import get_rag_instance, search_migrations, get_migration_suggestion

# Get migration suggestion
suggestion = get_migration_suggestion(
    '<helix-image alt="Test" src="image.jpg"></helix-image>',
    use_ollama=True
)

# Search for similar migrations
similar = search_migrations('helix-video', n_results=5)

# Get system statistics
from api_component.rag import get_rag_statistics
stats = get_rag_statistics()
```

### Management Commands

Use Django management commands for system maintenance:

```bash
# Initialize RAG system
python manage.py manage_rag --init

# Reset RAG system
python manage.py manage_rag --reset

# Show statistics
python manage.py manage_rag --stats

# Test search functionality
python manage.py manage_rag --test-search "helix-image"

# Test migration functionality
python manage.py manage_rag --test-migration '<helix-image alt="Test"></helix-image>'

# Use custom CSV file
python manage.py manage_rag --init --csv-path /path/to/custom.csv
```

## Configuration

### Data Sources

- **CSV File**: `v1_v2.csv` contains the migration examples
- **ChromaDB**: Vector database stored in `chroma_db/` directory
- **Ollama**: Optional AI service running on `http://localhost:11434`

### CSV Format

The `v1_v2.csv` file should have the following format:

```csv
v1,v2
"<helix-image ...>","<helix-core-image ...>"
"<helix-video ...>","<helix-core-video ...>"
```

### ChromaDB Storage

The system automatically creates and manages a ChromaDB collection named `helix_v1_v2_migrations` with:
- **Documents**: Searchable text representations of components
- **Metadata**: Component names, attributes, and migration data
- **IDs**: Unique identifiers for each migration example

## How It Works

### 1. Data Processing
- Loads migration data from CSV
- Extracts component names and attributes using BeautifulSoup
- Creates searchable text representations

### 2. Embedding & Storage
- ChromaDB automatically generates embeddings for semantic search
- Stores documents with rich metadata for filtering and retrieval

### 3. Similarity Search
- Uses vector similarity to find the most relevant migration examples
- Considers component structure, attributes, and context

### 4. AI Enhancement (Optional)
- Integrates with Ollama for improved suggestions
- Uses similar examples as context for AI-generated migrations
- Applies intelligent response cleaning

## Performance

- **ChromaDB**: Fast vector similarity search with automatic embedding generation
- **Caching**: Global RAG instance for efficient reuse
- **Batch Processing**: Efficient bulk operations for initialization
- **Memory Management**: Optimized for production use

## Troubleshooting

### Common Issues

1. **"ChromaDB not found"**:
   ```bash
   pip install chromadb
   ```

2. **"No migration data loaded"**:
   - Check if `v1_v2.csv` exists in the correct location
   - Verify CSV format and encoding (UTF-8)

3. **"Ollama connection failed"**:
   - Start Ollama service: `ollama serve`
   - Pull required model: `ollama pull llama3`

4. **"RAG system not initialized"**:
   ```bash
   python manage.py manage_rag --init
   ```

### Debug Mode

Enable detailed logging by setting the log level in your Django settings:

```python
LOGGING = {
    'version': 1,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'loggers': {
        'api_component.rag': {
            'handlers': ['console'],
            'level': 'DEBUG',
        },
    },
}
```

### Testing

Run the test suite to verify functionality:

```bash
cd api_component
python test_rag.py
```

This will test:
- CSV loading
- ChromaDB initialization
- Search functionality
- Migration suggestions
- Error handling

## Advanced Usage

### Custom Similarity Thresholds

Adjust similarity thresholds for different use cases:

```python
from api_component.rag import get_rag_instance

rag = get_rag_instance()

# High confidence migrations only
high_confidence = rag.search_similar_migrations(query, n_results=5)
high_confidence = [m for m in high_confidence if m['similarity_score'] > 0.9]

# Broader search for edge cases
broader_search = rag.search_similar_migrations(query, n_results=10)
```

### Batch Processing

For processing multiple components:

```python
components = [
    '<helix-image alt="img1" src="1.jpg">',
    '<helix-video media-id="123">',
    # ... more components
]

suggestions = []
for component in components:
    suggestion = get_migration_suggestion(component)
    suggestions.append(suggestion)
```

### Custom Enhancement

Extend the system with custom enhancement logic:

```python
class CustomRAG(ComponentRAG):
    def custom_enhance(self, v1_html, context):
        # Your custom enhancement logic
        enhanced_v2 = self.apply_custom_rules(v1_html)
        return enhanced_v2
```

## API Reference

See the complete API documentation in the code docstrings and the Django endpoint implementations in `views.py`.

## Contributing

When adding new features:

1. Update the CSV data with new migration examples
2. Test with `python test_rag.py`
3. Reinitialize the system: `python manage.py manage_rag --reset`
4. Update this documentation

## License

This RAG system is part of the Helix component migration toolkit and follows the same licensing terms as the parent project.
