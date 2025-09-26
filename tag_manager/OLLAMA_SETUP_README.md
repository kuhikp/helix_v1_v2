# Ollama & ChromaDB Setup Guide

This guide will help you set up Ollama with llama3 and ChromaDB for local development of the HelixBridge Tag Manager application.

## 📋 Prerequisites

- macOS, Linux, or Windows
- Python 3.8+
- At least 8GB RAM (16GB+ recommended for better performance)
- 10GB+ free disk space

## 🚀 Installation Steps

### 1. Install Ollama

#### macOS
```bash
# Download and install Ollama
curl -fsSL https://ollama.ai/install.sh | sh

# Or using Homebrew
brew install ollama
```

#### Linux
```bash
curl -fsSL https://ollama.ai/install.sh | sh
```

#### Windows
Download the installer from [https://ollama.ai/download](https://ollama.ai/download)

### 2. Start Ollama Service

```bash
# Start Ollama service (runs in background)
ollama serve
```

**Note:** Keep this terminal open or run as a background service.

### 3. Install llama3 Model

```bash
# Pull the llama3 model (this will take several minutes)
ollama pull llama3:latest

# Verify installation
ollama list
```

Expected output:
```
NAME            ID              SIZE      MODIFIED
llama3:latest   365c0bd3c000    4.7GB     2 minutes ago
```

### 4. Test Ollama Installation

```bash
# Test the model
ollama run llama3:latest "Hello, how are you?"

# Test API endpoint
curl http://localhost:11434/api/version
```

### 5. Install Python Dependencies

```bash
# Navigate to project directory
cd /path/to/commit_v1_v2/tag_manager

# Activate virtual environment
source venv/bin/activate  # or source .venv/bin/activate

# Install required packages
pip install chromadb requests python-dotenv django
```

### 6. Configure Environment Variables

Copy the environment template and update the configuration:

```bash
# Copy environment template
cp .env.example .env

# Edit the .env file
nano .env  # or use your preferred editor
```

Ensure these values are set in your `.env` file:

```bash
# Ollama Configuration
OLLAMA_BASE_URL="http://localhost:11434"
LLM_MODEL="llama3:latest"
MIGRATION_CLIENT_ENDPOINT="http://localhost:11434/api/embeddings"

# ChromaDB Configuration
COLLECTION_NAME="migration"

# Django Configuration
DEBUG=True
SECRET_KEY=your-development-secret-key
```

### 7. Initialize ChromaDB

The ChromaDB database will be automatically created when you first run the application. The default location is:

```bash
# ChromaDB data directory (auto-created)
./chroma_db/
```

### 8. Start the Django Application

```bash
# Run database migrations
python manage.py migrate

# Start the development server
python manage.py runserver 9002
```

## 🔧 Available Endpoints

Once the application is running, you can access these key endpoints:

### Migration Tools
- **Migration List**: [http://localhost:9002/migrations/list/](http://localhost:9002/migrations/list/)
  - View and manage HTML migration tasks
  - Use AI-powered Ollama for content migration between Helix versions

### Knowledge Base Management
- **Knowledge Base**: [http://localhost:9002/migrations/knowledge-base/](http://localhost:9002/migrations/knowledge-base/)
  - Manage V1 and V2 compatible code examples
  - Add, edit, and delete knowledge base entries
  - Automatic RAG (Retrieval-Augmented Generation) system updates
  - Search and query existing migration patterns

### API Endpoints
- **API Component**: [http://localhost:9002/api/api_component/](http://localhost:9002/api/api_component/)
- **Get Bearer Token**: [http://localhost:9002/api/get_token/](http://localhost:9002/api/get_token/)

## 🧪 Testing the Setup

### Test Ollama Integration

```bash
# Test the call_ollama function
cd /path/to/commit_v1_v2/tag_manager
python test_call_ollama.py
```

Expected output:
```
🧪 Testing call_ollama function
========================================
Function signature: call_ollama(prompt, model='llama3:latest')
Input prompt: Convert <helix-image> to <helix-core-image>
Calling call_ollama...
✅ call_ollama succeeded!
Result preview: <helix-core-image>...
```

### Test ChromaDB Integration

```bash
# Test RAG system
python test_rag_integration.py
```

### Test Complete Migration Workflow

1. Visit [http://localhost:9002/migrations/knowledge-base/](http://localhost:9002/migrations/knowledge-base/)
2. Add a new knowledge base entry with V1 and V2 code examples
3. Visit [http://localhost:9002/migrations/list/](http://localhost:9002/migrations/list/)
4. Test HTML migration using the AI-powered system

## 🔍 Troubleshooting

### Common Issues

#### 1. Ollama 404 Error
- **Problem**: `Error calling Ollama API: 404 Client Error`
- **Solution**: Ensure model name includes the tag (e.g., `llama3:latest` not `llama3`)

#### 2. Model Not Found
- **Problem**: Model `llama3` not found
- **Solution**: 
  ```bash
  ollama pull llama3:latest
  ollama list  # verify installation
  ```

#### 3. Memory Issues with Large Models
- **Problem**: `llama runner process has terminated: signal: killed`
- **Solution**: Use smaller models or increase system RAM
  ```bash
  # Use a smaller model if needed
  ollama pull llama3.2:1b
  # Update .env: LLM_MODEL="llama3.2:1b"
  ```

#### 4. ChromaDB Permission Issues
- **Problem**: Cannot write to ChromaDB directory
- **Solution**: 
  ```bash
  # Ensure proper permissions
  mkdir -p chroma_db
  chmod 755 chroma_db
  ```

#### 5. Django Database Issues
- **Problem**: Database connection errors
- **Solution**:
  ```bash
  # Reset database
  python manage.py migrate --run-syncdb
  ```

### Verify Installation

Run this comprehensive test:

```bash
# Check all services
echo "Testing Ollama..."
curl -s http://localhost:11434/api/version && echo "✅ Ollama OK" || echo "❌ Ollama Failed"

echo "Testing Django..."
curl -s http://localhost:9002/api/get_token/ && echo "✅ Django OK" || echo "❌ Django Failed"

echo "Testing Models..."
ollama list | grep llama3 && echo "✅ llama3 OK" || echo "❌ llama3 Missing"
```

## 📚 Usage Examples

### Knowledge Base Management

The Knowledge Base system allows you to:

1. **Add V1/V2 Code Examples**:
   - Original V1 Helix components
   - Migrated V2 Helix Core components
   - Migration patterns and best practices

2. **Automatic RAG Updates**:
   - When you add/edit/delete knowledge base entries
   - The system automatically updates the RAG (ChromaDB) database
   - Provides better AI-powered migration suggestions

3. **Search and Query**:
   - Search existing migration patterns
   - Get AI-powered suggestions for complex migrations
   - Access historical migration examples

### Migration Workflow

1. **Prepare Content**: Add your V1 HTML content
2. **Use Knowledge Base**: Reference existing V1→V2 migration patterns
3. **AI Migration**: Let Ollama suggest V2 conversions based on knowledge base
4. **Review & Refine**: Validate and adjust the migrated content
5. **Update Knowledge Base**: Add successful patterns for future use

## 🤝 Contributing

When adding new migration patterns to the knowledge base:

1. Include clear V1 and V2 examples
2. Add descriptive comments explaining the changes
3. Test the migration pattern thoroughly
4. Document any special considerations or edge cases

## 📞 Support

If you encounter issues:

1. Check the troubleshooting section above
2. Verify all services are running (`ollama serve` and `python manage.py runserver 9002`)
3. Check the console logs for detailed error messages
4. Ensure your `.env` file matches the example configuration

---

**Happy Migrating!** 🚀