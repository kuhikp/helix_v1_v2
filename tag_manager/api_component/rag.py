"""
RAG (Retrieval-Augmented Generation) system for v1_v2 component migration data.

This module provides functionality to:
1. Load and process v1_v2.csv data
2. Create embeddings and store them in ChromaDB
3. Provide similarity search for component migration
4. Integrate with Ollama for enhanced migration suggestions
"""

import os
import csv
import hashlib
import json
import re
from typing import List, Dict, Tuple, Optional
import chromadb
from chromadb.config import Settings
import requests
from bs4 import BeautifulSoup
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Django imports
try:
    import django
    from django.conf import settings
    if not settings.configured:
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tag_manager.settings')
        django.setup()
    
    from data_migration_utility.models import KnowledgeBase
    DJANGO_AVAILABLE = True
except ImportError:
    DJANGO_AVAILABLE = False
    logger.warning("Django not available, falling back to CSV mode")

class ComponentRAG:
    """
    RAG system for Helix component migration from v1 to v2.
    """
    
    def __init__(self, csv_path: str = None, persist_directory: str = None):
        """
        Initialize the RAG system.
        
        Args:
            csv_path: Path to the v1_v2.csv file
            persist_directory: Directory to persist ChromaDB data
        """
        # Set default paths
        if csv_path is None:
            csv_path = os.path.join(os.path.dirname(__file__), 'v1_v2.csv')
        
        if persist_directory is None:
            persist_directory = os.path.join(os.path.dirname(__file__), 'chroma_db')
        
        self.csv_path = csv_path
        self.persist_directory = persist_directory
        
        # Initialize ChromaDB
        self.client = chromadb.PersistentClient(
            path=persist_directory,
            settings=Settings(allow_reset=True)
        )
        
        # Get or create collection
        self.collection_name = "helix_v1_v2_migrations"
        try:
            self.collection = self.client.get_collection(self.collection_name)
            logger.info(f"Loaded existing collection: {self.collection_name}")
        except:
            self.collection = self.client.create_collection(
                name=self.collection_name,
                metadata={"description": "Helix v1 to v2 component migrations"}
            )
            logger.info(f"Created new collection: {self.collection_name}")
        
        self.migration_data = []
        self.is_initialized = False
    
    def load_csv_data(self) -> List[Dict[str, str]]:
        """
        Load migration data from CSV file.
        
        Returns:
            List of dictionaries containing v1 and v2 component data
        """
        migration_data = []
        
        try:
            with open(self.csv_path, 'r', encoding='utf-8') as file:
                csv_reader = csv.DictReader(file)
                for i, row in enumerate(csv_reader):
                    if 'v1' in row and 'v2' in row and row['v1'].strip() and row['v2'].strip():
                        migration_data.append({
                            'id': str(i),
                            'v1': row['v1'].strip(),
                            'v2': row['v2'].strip(),
                            'v1_component': self.extract_component_name(row['v1']),
                            'v2_component': self.extract_component_name(row['v2']),
                            'attributes': self.extract_attributes(row['v1'])
                        })
            
            logger.info(f"Loaded {len(migration_data)} migration records from CSV")
            return migration_data
            
        except FileNotFoundError:
            logger.error(f"CSV file not found: {self.csv_path}")
            return []
        except Exception as e:
            logger.error(f"Error loading CSV data: {e}")
            return []
    
    def load_database_data(self) -> List[Dict[str, str]]:
        """
        Load migration data from Django Knowledge Base database table.
        
        Returns:
            List of dictionaries containing v1 and v2 component data
        """
        migration_data = []

        print("load_database_data called")  # DEBUG LINE
        
        if not DJANGO_AVAILABLE:
            logger.warning("Django not available, cannot load database data")
            return self.load_csv_data()
        
        try:
            # Query active Knowledge Base entries
            knowledge_entries = KnowledgeBase.objects.filter(is_active=True).order_by('created_at')
            
            for i, entry in enumerate(knowledge_entries):
                if entry.v1_code and entry.v2_code:
                    migration_data.append({
                        'id': str(entry.pk),
                        'v1': entry.v1_code.strip(),
                        'v2': entry.v2_code.strip(),
                        'v1_component': self.extract_component_name(entry.v1_code),
                        'v2_component': self.extract_component_name(entry.v2_code),
                        'attributes': self.extract_attributes(entry.v1_code),
                        'title': entry.title,
                        'component_name': entry.component_name,
                        'description': entry.description or '',
                        'tags': entry.tags or '',
                        'created_by': entry.created_by.username if entry.created_by else '',
                        'created_at': entry.created_at.isoformat()
                    })
            
            logger.info(f"Loaded {len(migration_data)} migration records from database")
            return migration_data
            
        except Exception as e:
            logger.error(f"Error loading database data: {e}")
            # Fallback to CSV if database fails
            logger.info("Falling back to CSV data")
            return self.load_csv_data()
    
    def load_data(self, use_database: bool = True) -> List[Dict[str, str]]:
        """
        Load migration data from database or CSV based on preference.
        
        Args:
            use_database: If True, try database first, then fallback to CSV
            
        Returns:
            List of dictionaries containing v1 and v2 component data
        """
        if use_database and DJANGO_AVAILABLE:
            return self.load_database_data()
        else:
            return self.load_csv_data()
    
    def extract_component_name(self, html_content: str) -> str:
        """
        Extract component name from HTML content.
        
        Args:
            html_content: HTML string containing component
            
        Returns:
            Component name (e.g., 'helix-image', 'helix-core-image')
        """
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            if soup.find():
                return soup.find().name
            return ""
        except:
            # Fallback to regex if BeautifulSoup fails
            match = re.search(r'<(\S+)', html_content.strip())
            return match.group(1) if match else ""
    
    def extract_attributes(self, html_content: str) -> Dict[str, str]:
        """
        Extract attributes from HTML component.
        
        Args:
            html_content: HTML string containing component
            
        Returns:
            Dictionary of attributes and their values
        """
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            element = soup.find()
            if element:
                return dict(element.attrs)
            return {}
        except:
            return {}
    
    def create_searchable_text(self, migration_record: Dict[str, str]) -> str:
        """
        Create searchable text representation of migration record.
        
        Args:
            migration_record: Dictionary containing migration data
            
        Returns:
            Searchable text string
        """
        components = [
            migration_record.get('v1_component', ''),
            migration_record.get('v2_component', ''),
            migration_record.get('component_name', ''),
        ]
        
        attributes = migration_record.get('attributes', {})
        attr_text = ' '.join([f"{k}={v}" for k, v in attributes.items()])
        
        # Include additional database fields for better searchability
        additional_fields = [
            migration_record.get('title', ''),
            migration_record.get('description', ''),
            migration_record.get('tags', ''),
        ]
        
        searchable_text = ' '.join([
            ' '.join(components),
            ' '.join(additional_fields),
            attr_text,
            migration_record.get('v1', ''),
            migration_record.get('v2', '')
        ])
        
        return searchable_text.lower()
    
    def initialize_rag(self, force_reload: bool = False, use_database: bool = True) -> bool:
        """
        Initialize the RAG system by loading data and creating embeddings.
        
        Args:
            force_reload: If True, reload data even if already initialized
            use_database: If True, load data from database; if False, use CSV
            
        Returns:
            True if successful, False otherwise
        """
        if self.is_initialized and not force_reload:
            logger.info("RAG system already initialized")
            return True
        
        try:
            # Load data (database or CSV)
            self.migration_data = self.load_data(use_database=use_database)
            if not self.migration_data:
                logger.error("No migration data loaded")
                return False
            
            # Check if collection is empty or needs refresh
            collection_count = self.collection.count()
            if collection_count == 0 or force_reload:
                if force_reload and collection_count > 0:
                    # Clear existing data
                    self.client.delete_collection(self.collection_name)
                    self.collection = self.client.create_collection(
                        name=self.collection_name,
                        metadata={"description": "Helix v1 to v2 component migrations"}
                    )
                
                # Prepare data for ChromaDB
                documents = []
                metadatas = []
                ids = []
                
                for record in self.migration_data:
                    # Create searchable document
                    document = self.create_searchable_text(record)
                    documents.append(document)
                    
                    # Create metadata with additional database fields if available
                    metadata = {
                        'v1_component': record['v1_component'],
                        'v2_component': record['v2_component'],
                        'v1': record['v1'],
                        'v2': record['v2'],
                        'attributes_count': len(record['attributes']),
                        'component_name': record.get('component_name', record['v1_component']),
                        'title': record.get('title', ''),
                        'description': record.get('description', ''),
                        'tags': record.get('tags', ''),
                        'created_by': record.get('created_by', ''),
                        'source': 'database' if use_database and DJANGO_AVAILABLE else 'csv'
                    }
                    metadatas.append(metadata)
                    
                    # Create unique ID
                    content_hash = hashlib.md5(record['v1'].encode()).hexdigest()
                    ids.append(f"migration_{record['id']}_{content_hash[:8]}")
                
                # Add to ChromaDB
                self.collection.add(
                    documents=documents,
                    metadatas=metadatas,
                    ids=ids
                )
                
                data_source = "database" if use_database and DJANGO_AVAILABLE else "CSV"
                logger.info(f"Added {len(documents)} documents from {data_source} to ChromaDB")
            else:
                logger.info(f"Using existing ChromaDB collection with {collection_count} documents")
            
            self.is_initialized = True
            return True
            
        except Exception as e:
            logger.error(f"Error initializing RAG system: {e}")
            return False
    
    def search_similar_migrations(self, query: str, n_results: int = 5) -> List[Dict]:
        """
        Search for similar migration examples.
        
        Args:
            query: Search query (component HTML or component name)
            n_results: Number of results to return
            
        Returns:
            List of similar migration examples
        """
        if not self.is_initialized:
            if not self.initialize_rag():
                return []
        
        try:
            # Prepare query
            query_text = query.lower()
            if '<' in query:
                # If it's HTML, extract component info
                component_name = self.extract_component_name(query)
                attributes = self.extract_attributes(query)
                attr_text = ' '.join([f"{k}={v}" for k, v in attributes.items()])
                query_text = f"{component_name} {attr_text} {query}".lower()
            
            # Search ChromaDB
            results = self.collection.query(
                query_texts=[query_text],
                n_results=n_results,
                include=['documents', 'metadatas', 'distances']
            )
            
            # Format results
            similar_migrations = []
            for i in range(len(results['ids'][0])):
                similarity_score = 1.0 - results['distances'][0][i]  # Convert distance to similarity
                
                migration = {
                    'id': results['ids'][0][i],
                    'v1': results['metadatas'][0][i]['v1'],
                    'v2': results['metadatas'][0][i]['v2'],
                    'v1_component': results['metadatas'][0][i]['v1_component'],
                    'v2_component': results['metadatas'][0][i]['v2_component'],
                    'similarity_score': similarity_score,
                    'attributes_count': results['metadatas'][0][i]['attributes_count']
                }
                similar_migrations.append(migration)
            
            # Sort by similarity score (highest first)
            similar_migrations.sort(key=lambda x: x['similarity_score'], reverse=True)
            
            logger.info(f"Found {len(similar_migrations)} similar migrations for query: {query[:50]}...")
            return similar_migrations
            
        except Exception as e:
            logger.error(f"Error searching similar migrations: {e}")
            return []
    
    def get_migration_suggestion(self, v1_html: str, use_ollama: bool = True) -> Dict:
        """
        Get migration suggestion for a v1 component.
        
        Args:
            v1_html: HTML content of v1 component
            use_ollama: Whether to use Ollama for enhanced suggestions
            
        Returns:
            Dictionary containing migration suggestion and similar examples
        """
        if not self.is_initialized:
            if not self.initialize_rag():
                return {'error': 'RAG system not initialized'}
        
        try:
            # Find similar migrations
            similar_migrations = self.search_similar_migrations(v1_html, n_results=3)
            
            result = {
                'input_v1': v1_html,
                'similar_examples': similar_migrations,
                'suggested_v2': None,
                'confidence_score': 0.0,
                'method': 'rag_only'
            }
            
            if similar_migrations:
                # Use the most similar example as base suggestion
                best_match = similar_migrations[0]
                result['suggested_v2'] = best_match['v2']
                result['confidence_score'] = best_match['similarity_score']
                
                if use_ollama and best_match['similarity_score'] < 0.9:
                    # Use Ollama to enhance the suggestion
                    enhanced_suggestion = self.enhance_with_ollama(v1_html, similar_migrations)
                    if enhanced_suggestion:
                        result['suggested_v2'] = enhanced_suggestion
                        result['method'] = 'rag_plus_ollama'
                        result['confidence_score'] = min(result['confidence_score'] + 0.1, 1.0)
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting migration suggestion: {e}")
            return {'error': str(e)}
    
    def enhance_with_ollama(self, v1_html: str, similar_examples: List[Dict]) -> Optional[str]:
        """
        Use Ollama to enhance migration suggestion based on similar examples.
        
        Args:
            v1_html: Original v1 HTML
            similar_examples: List of similar migration examples
            
        Returns:
            Enhanced v2 HTML or None if failed
        """
        try:
            # Create context from similar examples
            context = "Here are similar migration examples:\n\n"
            for i, example in enumerate(similar_examples[:2], 1):
                context += f"Example {i}:\n"
                context += f"V1: {example['v1']}\n"
                context += f"V2: {example['v2']}\n\n"
            
            # Create prompt
            prompt = f"""Based on the migration patterns shown in the examples above, migrate this v1 component to v2:

{v1_html}

Follow these migration patterns:
1. Change helix- components to helix-core- components
2. Update attribute names and structure as shown in examples
3. Maintain all functionality and data
4. Return ONLY the migrated v2 HTML, no explanations

V2 Migration:"""
            
            # Call Ollama API
            url = "http://localhost:11434/api/generate"
            payload = {
                "model": os.getenv('LLM_MODEL'),
                "prompt": prompt,
                "stream": False,
                "system": "You are a precise HTML migration tool. Return ONLY the migrated HTML content.",
                "options": {"temperature": 0}
            }
            
            response = requests.post(url, json=payload, timeout=60)
            response.raise_for_status()
            
            data = response.json()
            if "response" in data:
                migrated_html = data["response"].strip()
                # Clean up common prefixes
                prefixes_to_remove = [
                    "Here is the migrated v2 HTML:",
                    "V2 Migration:",
                    "The migrated HTML is:",
                    "Here's the v2 version:"
                ]
                
                for prefix in prefixes_to_remove:
                    if migrated_html.lower().startswith(prefix.lower()):
                        migrated_html = migrated_html[len(prefix):].strip()
                
                return migrated_html
            
        except Exception as e:
            logger.error(f"Error enhancing with Ollama: {e}")
            return None
    
    def get_statistics(self) -> Dict:
        """
        Get RAG system statistics.
        
        Returns:
            Dictionary containing system statistics
        """
        if not self.is_initialized:
            if not self.initialize_rag():
                return {'error': 'RAG system not initialized'}
        
        try:
            collection_count = self.collection.count()
            
            # Count component types
            component_counts = {}
            database_entries = 0
            csv_entries = 0
            
            for record in self.migration_data:
                v1_comp = record['v1_component']
                if v1_comp in component_counts:
                    component_counts[v1_comp] += 1
                else:
                    component_counts[v1_comp] = 1
                
                # Count data source types
                if 'created_at' in record:  # Database entries have created_at
                    database_entries += 1
                else:
                    csv_entries += 1
            
            # Get database statistics if available
            db_stats = {}
            if DJANGO_AVAILABLE:
                try:
                    total_kb_entries = KnowledgeBase.objects.count()
                    active_kb_entries = KnowledgeBase.objects.filter(is_active=True).count()
                    inactive_kb_entries = total_kb_entries - active_kb_entries
                    db_stats = {
                        'total_knowledge_base_entries': total_kb_entries,
                        'active_knowledge_base_entries': active_kb_entries,
                        'inactive_knowledge_base_entries': inactive_kb_entries
                    }
                except Exception as e:
                    db_stats = {'database_error': str(e)}
            
            return {
                'total_migrations': len(self.migration_data),
                'chromadb_documents': collection_count,
                'component_types': len(component_counts),
                'component_counts': component_counts,
                'data_sources': {
                    'database_entries': database_entries,
                    'csv_entries': csv_entries
                },
                'database_stats': db_stats,
                'csv_path': self.csv_path,
                'persist_directory': self.persist_directory,
                'is_initialized': self.is_initialized,
                'django_available': DJANGO_AVAILABLE
            }
            
        except Exception as e:
            logger.error(f"Error getting statistics: {e}")
            return {'error': str(e)}
    
    def update_rag_system(self, use_database: bool = True) -> bool:
        """
        Update the RAG system with the latest data from database or CSV.
        This forces a reload of all data and rebuilds the ChromaDB collection.
        
        Args:
            use_database: If True, load data from database; if False, use CSV
            
        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info("Updating RAG system with latest data...")
            
            # Force reload with latest data
            success = self.initialize_rag(force_reload=True, use_database=use_database)
            
            if success:
                data_source = "database" if use_database and DJANGO_AVAILABLE else "CSV"
                logger.info(f"Successfully updated RAG system with data from {data_source}")
                return True
            else:
                logger.error("Failed to update RAG system")
                return False
                
        except Exception as e:
            logger.error(f"Error updating RAG system: {e}")
            return False
    
    def reset_rag_system(self, use_database: bool = True) -> bool:
        """
        Reset and reinitialize the RAG system.
        
        Args:
            use_database: If True, load data from database; if False, use CSV
        
        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info("Resetting RAG system...")
            
            # Delete existing collection
            try:
                self.client.delete_collection(self.collection_name)
                logger.info(f"Deleted existing collection: {self.collection_name}")
            except:
                logger.info("No existing collection to delete")
            
            # Recreate collection
            self.collection = self.client.create_collection(
                name=self.collection_name,
                metadata={"description": "Helix v1 to v2 component migrations"}
            )
            
            # Reset state
            self.is_initialized = False
            self.migration_data = []
            
            # Reinitialize with fresh data
            return self.initialize_rag(force_reload=True, use_database=use_database)
            
        except Exception as e:
            logger.error(f"Error resetting RAG system: {e}")
            return False


# Global RAG instance
_rag_instance = None

def get_rag_instance() -> ComponentRAG:
    """Get or create global RAG instance."""
    global _rag_instance
    if _rag_instance is None:
        _rag_instance = ComponentRAG()
        _rag_instance.initialize_rag(use_database=True)  # Default to database
    return _rag_instance

# Convenience functions for easy usage
def search_migrations(query: str, n_results: int = 5) -> List[Dict]:
    """Search for similar migrations."""
    rag = get_rag_instance()
    return rag.search_similar_migrations(query, n_results)

def get_migration_suggestion(v1_html: str, use_ollama: bool = True) -> Dict:
    """Get migration suggestion for v1 component."""
    rag = get_rag_instance()
    return rag.get_migration_suggestion(v1_html, use_ollama)

def get_rag_statistics() -> Dict:
    """Get RAG system statistics."""
    rag = get_rag_instance()
    return rag.get_statistics()

def update_rag(use_database: bool = True) -> bool:
    """Update RAG system with latest data."""
    rag = get_rag_instance()
    return rag.update_rag_system(use_database=use_database)

def reset_rag(use_database: bool = True) -> bool:
    """Reset RAG system."""
    global _rag_instance
    if _rag_instance:
        result = _rag_instance.reset_rag_system(use_database=use_database)
        if result:
            _rag_instance = None
        return result
    return True

def force_reload_rag(use_database: bool = True) -> bool:
    """Force reload the RAG instance with fresh data."""
    global _rag_instance
    _rag_instance = None  # Clear the global instance
    rag = get_rag_instance()
    return rag.initialize_rag(force_reload=True, use_database=use_database)
