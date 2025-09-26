"""
Django management command to initialize and manage the RAG system.
"""

from django.core.management.base import BaseCommand
from api_component.rag import ComponentRAG, get_rag_instance
import os


class Command(BaseCommand):
    help = 'Initialize and manage the RAG system for component migrations'

    def add_arguments(self, parser):
        parser.add_argument(
            '--init',
            action='store_true',
            help='Initialize the RAG system',
        )
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Reset and reinitialize the RAG system',
        )
        parser.add_argument(
            '--stats',
            action='store_true',
            help='Show RAG system statistics',
        )
        parser.add_argument(
            '--test-search',
            type=str,
            help='Test search functionality with a query',
        )
        parser.add_argument(
            '--test-migration',
            type=str,
            help='Test migration functionality with V1 HTML',
        )
        parser.add_argument(
            '--csv-path',
            type=str,
            help='Custom path to v1_v2.csv file',
        )

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS('RAG System Management Command')
        )

        if options['init']:
            self.init_rag(options.get('csv_path'))
        elif options['reset']:
            self.reset_rag()
        elif options['stats']:
            self.show_stats()
        elif options['test_search']:
            self.test_search(options['test_search'])
        elif options['test_migration']:
            self.test_migration(options['test_migration'])
        else:
            self.stdout.write(
                self.style.WARNING('Please specify an action: --init, --reset, --stats, --test-search, or --test-migration')
            )

    def init_rag(self, csv_path=None):
        """Initialize the RAG system."""
        self.stdout.write('Initializing RAG system...')
        
        try:
            if csv_path:
                rag = ComponentRAG(csv_path=csv_path)
            else:
                rag = get_rag_instance()
            
            success = rag.initialize_rag(force_reload=True)
            
            if success:
                stats = rag.get_statistics()
                self.stdout.write(
                    self.style.SUCCESS(
                        f'RAG system initialized successfully!\n'
                        f'Total migrations: {stats.get("total_migrations", 0)}\n'
                        f'ChromaDB documents: {stats.get("chromadb_documents", 0)}\n'
                        f'Component types: {stats.get("component_types", 0)}'
                    )
                )
            else:
                self.stdout.write(
                    self.style.ERROR('Failed to initialize RAG system')
                )
                
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error initializing RAG system: {e}')
            )

    def reset_rag(self):
        """Reset the RAG system."""
        self.stdout.write('Resetting RAG system...')
        
        try:
            rag = get_rag_instance()
            success = rag.reset_rag_system()
            
            if success:
                self.stdout.write(
                    self.style.SUCCESS('RAG system reset successfully!')
                )
            else:
                self.stdout.write(
                    self.style.ERROR('Failed to reset RAG system')
                )
                
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error resetting RAG system: {e}')
            )

    def show_stats(self):
        """Show RAG system statistics."""
        self.stdout.write('Fetching RAG system statistics...')
        
        try:
            rag = get_rag_instance()
            stats = rag.get_statistics()
            
            if 'error' in stats:
                self.stdout.write(
                    self.style.ERROR(f'Error getting stats: {stats["error"]}')
                )
                return
            
            self.stdout.write(
                self.style.SUCCESS('RAG System Statistics:')
            )
            
            self.stdout.write(f"Total migrations: {stats.get('total_migrations', 0)}")
            self.stdout.write(f"ChromaDB documents: {stats.get('chromadb_documents', 0)}")
            self.stdout.write(f"Component types: {stats.get('component_types', 0)}")
            self.stdout.write(f"CSV path: {stats.get('csv_path', 'N/A')}")
            self.stdout.write(f"Persist directory: {stats.get('persist_directory', 'N/A')}")
            self.stdout.write(f"Is initialized: {stats.get('is_initialized', False)}")
            
            component_counts = stats.get('component_counts', {})
            if component_counts:
                self.stdout.write('\nComponent breakdown:')
                for component, count in sorted(component_counts.items()):
                    self.stdout.write(f"  {component}: {count}")
                    
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error getting statistics: {e}')
            )

    def test_search(self, query):
        """Test search functionality."""
        self.stdout.write(f'Testing search with query: "{query}"')
        
        try:
            from api_component.rag import search_migrations
            
            results = search_migrations(query, n_results=3)
            
            self.stdout.write(
                self.style.SUCCESS(f'Found {len(results)} similar migrations:')
            )
            
            for i, result in enumerate(results, 1):
                self.stdout.write(f'\n--- Result {i} ---')
                self.stdout.write(f'Component: {result["v1_component"]} -> {result["v2_component"]}')
                self.stdout.write(f'Similarity: {result["similarity_score"]:.3f}')
                self.stdout.write(f'V1: {result["v1"][:100]}...')
                self.stdout.write(f'V2: {result["v2"][:100]}...')
                
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error testing search: {e}')
            )

    def test_migration(self, v1_html):
        """Test migration functionality."""
        self.stdout.write(f'Testing migration with V1 HTML: "{v1_html[:50]}..."')
        
        try:
            from api_component.rag import get_migration_suggestion
            
            suggestion = get_migration_suggestion(v1_html, use_ollama=False)
            
            if 'error' in suggestion:
                self.stdout.write(
                    self.style.ERROR(f'Migration error: {suggestion["error"]}')
                )
                return
            
            self.stdout.write(
                self.style.SUCCESS('Migration suggestion generated:')
            )
            
            self.stdout.write(f'Method: {suggestion["method"]}')
            self.stdout.write(f'Confidence: {suggestion["confidence_score"]:.3f}')
            self.stdout.write(f'Similar examples: {len(suggestion["similar_examples"])}')
            
            if suggestion['suggested_v2']:
                self.stdout.write(f'Suggested V2: {suggestion["suggested_v2"][:200]}...')
            else:
                self.stdout.write('No V2 suggestion generated')
                
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error testing migration: {e}')
            )
