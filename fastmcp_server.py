"""
Legal Amendment Change Detection FastMCP Server
Server-side MCP server for legal document analysis using FastMCP
"""

import json
import logging
from typing import Any, Dict, List, Optional
from pathlib import Path
from datetime import datetime
import boto3
import os
from io import StringIO
import argparse

# Configure logging first
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from fastmcp import FastMCP

# S3 Configuration
S3_BUCKET = os.getenv('S3_BUCKET', 'legal-amendment-mcp')
DEFAULT_DECREE_S3_PATH = 'decrees/Decree-118_2021.json'
DEFAULT_AMENDMENT_S3_PATH = 'ammendments/190_2025_ND-CP.json'

# Initialize S3 client
try:
    s3_client = boto3.client('s3', region_name='us-east-1', aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'), aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY')  )
    S3_AVAILABLE = True
    logger.info("S3 client initialized successfully")
except Exception as e:
    logger.warning(f"S3 client not available: {e}")
    S3_AVAILABLE = False

# Import report generator with error handling
try:
    from legal_report_generator import LegalAmendmentReportGenerator
    REPORT_GENERATOR_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Report generator not available: {e}")
    REPORT_GENERATOR_AVAILABLE = False

# Legal document analysis classes
class LegalDocumentAnalyzer:
    """Analyzes legal documents from JSON structures"""
    
    def __init__(self):
        self.decree_data = None
        self.amendment_data = None
    
    def load_decree_data(self, file_path: str):
        """Load decree JSON data from local file or S3"""
        if file_path.startswith('s3://'):
            self._load_from_s3(file_path, 'decree')
        else:
            with open(file_path, 'r', encoding='utf-8') as f:
                self.decree_data = json.load(f)
    
    def load_amendment_data(self, file_path: str):
        """Load amendment JSON data from local file or S3"""
        if file_path.startswith('s3://'):
            self._load_from_s3(file_path, 'amendment')
        else:
            with open(file_path, 'r', encoding='utf-8') as f:
                self.amendment_data = json.load(f)
    
    def _load_from_s3(self, s3_path: str, data_type: str):
        """Load JSON data from S3"""
        if not S3_AVAILABLE:
            raise Exception("S3 client not available")
        
        try:
            # Parse S3 path: s3://bucket/key
            if not s3_path.startswith('s3://'):
                raise ValueError("S3 path must start with 's3://'")
            
            path_parts = s3_path[5:].split('/', 1)  # Remove 's3://' and split
            if len(path_parts) != 2:
                raise ValueError("Invalid S3 path format")
            
            bucket = path_parts[0]
            key = path_parts[1]
            
            logger.info(f"Loading {data_type} data from S3: s3://{bucket}/{key}")
            
            # Get object from S3
            response = s3_client.get_object(Bucket=bucket, Key=key)
            content = response['Body'].read().decode('utf-8')
            
            # Parse JSON
            data = json.loads(content)
            
            if data_type == 'decree':
                self.decree_data = data
            elif data_type == 'amendment':
                self.amendment_data = data
            
            logger.info(f"Successfully loaded {data_type} data from S3")
            
        except Exception as e:
            logger.error(f"Error loading {data_type} data from S3: {e}")
            raise Exception(f"Failed to load {data_type} data from S3: {str(e)}")
    
    def load_default_documents(self):
        """Load default documents from S3"""
        try:
            decree_s3_path = f"s3://{S3_BUCKET}/{DEFAULT_DECREE_S3_PATH}"
            amendment_s3_path = f"s3://{S3_BUCKET}/{DEFAULT_AMENDMENT_S3_PATH}"
            
            self.load_decree_data(decree_s3_path)
            self.load_amendment_data(amendment_s3_path)
            
            logger.info(f"Successfully loaded default documents from S3")
            return True
            
        except Exception as e:
            logger.warning(f"Could not load default documents from S3: {e}")
            return False
    
    def get_changes_in_article(self, article_number: str) -> Dict[str, Any]:
        """Get changes for a specific article"""
        if not self.amendment_data:
            return {"error": "Amendment data not loaded"}
        
        changes = []
        for amendment in self.amendment_data.get("amendments", []):
            target = amendment.get("target", {})
            if target.get("article_number") == article_number:
                change_info = {
                    "amendment_type": amendment.get("amendment_type"),
                    "target": target,
                    "text": amendment.get("text", ""),
                    "clauses": amendment.get("clauses", [])
                }
                
                # Add metadata if available
                if "insert_after_article" in target:
                    change_info["insert_after_article"] = target["insert_after_article"]
                
                changes.append(change_info)
        
        return {
            "article_number": article_number,
            "changes": changes,
            "total_changes": len(changes)
        }
    
    def summarize_all_changes(self) -> Dict[str, Any]:
        """Summarize all changes between decree and amendment"""
        if not self.amendment_data:
            return {"error": "Amendment data not loaded"}
        
        amendments = self.amendment_data.get("amendments", [])
        
        # Count by amendment type
        amendment_counts = {}
        articles_affected = set()
        new_articles = set()
        
        for amendment in amendments:
            amendment_type = amendment.get("amendment_type")
            amendment_counts[amendment_type] = amendment_counts.get(amendment_type, 0) + 1
            
            target = amendment.get("target", {})
            if "article_number" in target:
                articles_affected.add(target["article_number"])
                
                # Check if it's a new article (has insert_after_article)
                if "insert_after_article" in target:
                    new_articles.add(target["article_number"])
        
        return {
            "summary": {
                "total_amendments": len(amendments),
                "amendment_types": amendment_counts,
                "articles_affected": len(articles_affected),
                "affected_articles": sorted(list(articles_affected)),
                "new_articles_added": len(new_articles),
                "new_articles": sorted(list(new_articles))
            },
            "detailed_changes": [
                {
                    "amendment_type": a.get("amendment_type"),
                    "target_article": a.get("target", {}).get("article_number"),
                    "target_clause": a.get("target", {}).get("clause_number"),
                    "is_new_article": "insert_after_article" in a.get("target", {}),
                    "insert_after": a.get("target", {}).get("insert_after_article"),
                    "has_text": bool(a.get("text")),
                    "has_clauses": bool(a.get("clauses")),
                    "clause_count": len(a.get("clauses", []))
                }
                for a in amendments
            ]
        }
    
    def get_article_content(self, article_number: str) -> Dict[str, Any]:
        """Get content of a specific article from decree"""
        if not self.decree_data:
            return {"error": "Decree data not loaded"}
        
        for chapter in self.decree_data.get("Decree", {}).get("chapters", []):
            for article in chapter.get("articles", []):
                if article.get("article_number") == article_number:
                    return {
                        "article_number": article_number,
                        "title": article.get("article_title"),
                        "clauses": article.get("clauses", []),
                        "chapter_number": chapter.get("chapter_number"),
                        "chapter_title": chapter.get("chapter_title")
                    }
        
        return {"error": f"Article {article_number} not found"}
    
    def compare_article_before_after(self, article_number: str) -> Dict[str, Any]:
        """Compare article content before and after amendments"""
        original_content = self.get_article_content(article_number)
        changes = self.get_changes_in_article(article_number)
        
        return {
            "article_number": article_number,
            "original_content": original_content,
            "changes": changes,
            "analysis": {
                "has_changes": changes.get("total_changes", 0) > 0,
                "change_types": [c["amendment_type"] for c in changes.get("changes", [])],
                "is_new_article": any("insert_after_article" in c.get("target", {}) for c in changes.get("changes", []))
            }
        }
    
    def get_amendment_details(self, amendment_index: int) -> Dict[str, Any]:
        """Get detailed information about a specific amendment by index"""
        if not self.amendment_data:
            return {"error": "Amendment data not loaded"}
        
        amendments = self.amendment_data.get("amendments", [])
        if amendment_index < 0 or amendment_index >= len(amendments):
            return {"error": f"Amendment index {amendment_index} out of range. Total amendments: {len(amendments)}"}
        
        amendment = amendments[amendment_index]
        return {
            "index": amendment_index,
            "amendment_type": amendment.get("amendment_type"),
            "target": amendment.get("target", {}),
            "text": amendment.get("text", ""),
            "clauses": amendment.get("clauses", []),
            "clause_count": len(amendment.get("clauses", [])),
            "has_text": bool(amendment.get("text")),
            "has_clauses": bool(amendment.get("clauses"))
        }
    
    def search_amendments_by_type(self, amendment_type: str) -> Dict[str, Any]:
        """Search amendments by type (Addition, Modification, etc.)"""
        if not self.amendment_data:
            return {"error": "Amendment data not loaded"}
        
        amendments = self.amendment_data.get("amendments", [])
        matching_amendments = []
        
        for i, amendment in enumerate(amendments):
            if amendment.get("amendment_type", "").lower() == amendment_type.lower():
                matching_amendments.append({
                    "index": i,
                    "amendment_type": amendment.get("amendment_type"),
                    "target_section": amendment.get("target", {}).get("article_number"),
                    "target_clause": amendment.get("target", {}).get("clause_number"),
                    "has_text": bool(amendment.get("text")),
                    "has_clauses": bool(amendment.get("clauses"))
                })
        
        return {
            "amendment_type": amendment_type,
            "matches": matching_amendments,
            "total_matches": len(matching_amendments)
        }
    
    def get_detailed_amendment_analysis(self, amendment_index: int) -> Dict[str, Any]:
        """Get detailed analysis of an amendment showing original vs new content"""
        if not self.amendment_data:
            return {"error": "Amendment data not loaded"}
        
        amendments = self.amendment_data.get("amendments", [])
        if amendment_index < 0 or amendment_index >= len(amendments):
            return {"error": f"Amendment index {amendment_index} out of range. Total amendments: {len(amendments)}"}
        
        amendment = amendments[amendment_index]
        amendment_type = amendment.get("amendment_type")
        target = amendment.get("target", {})
        article_number = target.get("article_number")
        
        analysis = {
            "amendment_index": amendment_index,
            "amendment_type": amendment_type,
            "target_article": article_number,
            "target_clause": target.get("clause_number"),
            "is_new_article": "insert_after_article" in target,
            "insert_after": target.get("insert_after_article")
        }
        
        # Get original content if it's a modification or deletion
        if amendment_type in ["Modification", "Deletion"] and article_number:
            original_content = self.get_article_content(article_number)
            analysis["original_content"] = original_content
        
        # Analyze the amendment content
        if amendment_type == "Addition":
            analysis["added_content"] = {
                "text": amendment.get("text", ""),
                "clauses": amendment.get("clauses", [])
            }
            analysis["summary"] = f"New content added to Article {article_number}"
            
        elif amendment_type == "Modification":
            analysis["modified_content"] = {
                "text": amendment.get("text", ""),
                "clauses": amendment.get("clauses", [])
            }
            analysis["summary"] = f"Article {article_number} content modified"
            
        elif amendment_type == "Deletion":
            analysis["deleted_content"] = {
                "text": amendment.get("text", ""),
                "clauses": amendment.get("clauses", [])
            }
            analysis["summary"] = f"Content deleted from Article {article_number}"
        
        return analysis
    
    def get_combined_article_view(self, article_number: str) -> Dict[str, Any]:
        """Get combined view of article with amendments applied"""
        if not self.amendment_data:
            return {"error": "Amendment data not loaded"}
        
        # Get original article content
        original_content = self.get_article_content(article_number)
        if "error" in original_content:
            # Check if it's a new article
            changes = self.get_changes_in_article(article_number)
            if changes.get("total_changes", 0) > 0:
                # It's a new article
                new_article_changes = [c for c in changes.get("changes", []) if c.get("amendment_type") == "Addition"]
                if new_article_changes:
                    return {
                        "article_number": article_number,
                        "is_new_article": True,
                        "content": new_article_changes[0].get("clauses", []),
                        "text": new_article_changes[0].get("text", ""),
                        "insert_after": new_article_changes[0].get("insert_after_article"),
                        "source": "amendment_only"
                    }
            return original_content
        
        # Get changes for this article
        changes = self.get_changes_in_article(article_number)
        
        # Start with original content
        combined_content = {
            "article_number": article_number,
            "title": original_content.get("title"),
            "chapter_number": original_content.get("chapter_number"),
            "chapter_title": original_content.get("chapter_title"),
            "clauses": original_content.get("clauses", []).copy(),
            "modifications": [],
            "additions": [],
            "deletions": []
        }
        
        # Apply amendments
        for change in changes.get("changes", []):
            amendment_type = change.get("amendment_type")
            
            if amendment_type == "Addition":
                combined_content["additions"].append({
                    "clauses": change.get("clauses", []),
                    "text": change.get("text", "")
                })
                
            elif amendment_type == "Modification":
                combined_content["modifications"].append({
                    "target_clause": change.get("target", {}).get("clause_number"),
                    "clauses": change.get("clauses", []),
                    "text": change.get("text", "")
                })
                
            elif amendment_type == "Deletion":
                combined_content["deletions"].append({
                    "target_clause": change.get("target", {}).get("clause_number"),
                    "clauses": change.get("clauses", []),
                    "text": change.get("text", "")
                })
        
        combined_content["has_changes"] = len(combined_content["modifications"]) > 0 or len(combined_content["additions"]) > 0 or len(combined_content["deletions"]) > 0
        
        return combined_content

# Initialize FastMCP server
mcp = FastMCP("legal-amendment-detector", port=3000)

# Initialize document analyzer
analyzer = LegalDocumentAnalyzer()

# Auto-load default documents from S3
try:
    success = analyzer.load_default_documents()
    if success:
        logger.info("Successfully auto-loaded default documents from S3")
    else:
        logger.warning("Could not auto-load default documents from S3")
except Exception as e:
    logger.warning(f"Error during auto-loading: {e}")

@mcp.tool
def load_legal_documents(decree_file: str, amendment_file: str) -> str:
    """Load decree and amendment JSON files for analysis"""
    try:
        analyzer.load_decree_data(decree_file)
        analyzer.load_amendment_data(amendment_file)
        return f"Successfully loaded decree from {decree_file} and amendment from {amendment_file}"
    except Exception as e:
        logger.error(f"Error loading documents: {e}")
        return f"Error loading documents: {str(e)}"

@mcp.tool
def get_changes_in_article(article_number: str, decree_file: str = "", amendment_file: str = "") -> str:
    """Get all changes for a specific article number. Optionally provide decree_file and amendment_file to load different documents."""
    try:
        # Load documents if provided (check for non-empty strings)
        if decree_file and amendment_file:
            analyzer.load_decree_data(decree_file)
            analyzer.load_amendment_data(amendment_file)
        else:
            # If no specific files provided, try to load default documents if not already loaded
            if not analyzer.amendment_data or not analyzer.decree_data:
                logger.info("Attempting to load default documents...")
                success = analyzer.load_default_documents()
                if not success:
                    logger.warning("Failed to load default documents")
        
        # Check if documents are loaded
        if not analyzer.amendment_data:
            return json.dumps({
                "error": "Amendment data not loaded. Please provide decree_file and amendment_file parameters or ensure default documents are available.",
                "suggestion": "Try calling load_legal_documents with specific file paths first."
            }, indent=2, ensure_ascii=False)
        
        result = analyzer.get_changes_in_article(article_number)
        return json.dumps(result, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error getting changes for article {article_number}: {e}")
        return f"Error getting changes for article {article_number}: {str(e)}"

@mcp.tool
def summarize_all_changes(decree_file: str = "", amendment_file: str =  "") -> str:
    """Generate a comprehensive summary of all changes between decree and amendment. Optionally provide decree_file and amendment_file to load different documents."""
    try:
        # Load documents if provided
        if decree_file and amendment_file:
            analyzer.load_decree_data(decree_file)
            analyzer.load_amendment_data(amendment_file)
        
        # Check if documents are loaded
        if not analyzer.amendment_data:
            return json.dumps({
                "error": "Amendment data not loaded. Please provide decree_file and amendment_file parameters or ensure default documents are available."
            }, indent=2, ensure_ascii=False)
        
        result = analyzer.summarize_all_changes()
        return json.dumps(result, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error summarizing changes: {e}")
        return f"Error summarizing changes: {str(e)}"

@mcp.tool
def get_article_content(article_number: str, decree_file: str =  "") -> str:
    """Get the original content of a specific article from the decree. Optionally provide decree_file to load different document."""
    try:
        # Load decree if provided
        if decree_file:
            analyzer.load_decree_data(decree_file)
        
        # Check if decree is loaded
        if not analyzer.decree_data:
            return json.dumps({
                "error": "Decree data not loaded. Please provide decree_file parameter or ensure default documents are available."
            }, indent=2, ensure_ascii=False)
        
        result = analyzer.get_article_content(article_number)
        return json.dumps(result, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error getting content for article {article_number}: {e}")
        return f"Error getting content for article {article_number}: {str(e)}"

@mcp.tool
def compare_article_before_after(article_number: str, decree_file: str =  "", amendment_file: str =  "") -> str:
    """Compare an article's content before and after amendments. Optionally provide decree_file and amendment_file to load different documents."""
    try:
        # Load documents if provided
        if decree_file and amendment_file:
            analyzer.load_decree_data(decree_file)
            analyzer.load_amendment_data(amendment_file)
        
        # Check if documents are loaded
        if not analyzer.decree_data or not analyzer.amendment_data:
            return json.dumps({
                "error": "Documents not loaded. Please provide decree_file and amendment_file parameters or ensure default documents are available."
            }, indent=2, ensure_ascii=False)
        
        result = analyzer.compare_article_before_after(article_number)
        return json.dumps(result, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error comparing article {article_number}: {e}")
        return f"Error comparing article {article_number}: {str(e)}"

@mcp.tool
def get_amendment_statistics(decree_file: str = "", amendment_file: str =  "") -> str:
    """Get statistics about amendment types and affected articles. Optionally provide decree_file and amendment_file to load different documents."""
    try:
        # Load documents if provided
        if decree_file and amendment_file:
            analyzer.load_decree_data(decree_file)
            analyzer.load_amendment_data(amendment_file)
        
        # Check if documents are loaded
        if not analyzer.amendment_data:
            return json.dumps({
                "error": "Amendment data not loaded. Please provide decree_file and amendment_file parameters or ensure default documents are available."
            }, indent=2, ensure_ascii=False)
        
        result = analyzer.summarize_all_changes()
        # Extract just the statistics part
        stats = {
            "statistics": result.get("summary", {}),
            "amendment_breakdown": result.get("detailed_changes", [])
        }
        return json.dumps(stats, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error getting amendment statistics: {e}")
        return f"Error getting amendment statistics: {str(e)}"

@mcp.tool
def get_amendment_details(amendment_index: int, decree_file: str =  "", amendment_file: str =  "") -> str:
    """Get detailed information about a specific amendment by index (0-based). Optionally provide decree_file and amendment_file to load different documents."""
    try:
        # Load documents if provided
        if decree_file and amendment_file:
            analyzer.load_decree_data(decree_file)
            analyzer.load_amendment_data(amendment_file)
        
        # Check if documents are loaded
        if not analyzer.amendment_data:
            return json.dumps({
                "error": "Amendment data not loaded. Please provide decree_file and amendment_file parameters or ensure default documents are available."
            }, indent=2, ensure_ascii=False)
        
        result = analyzer.get_amendment_details(amendment_index)
        return json.dumps(result, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error getting amendment details for index {amendment_index}: {e}")
        return f"Error getting amendment details for index {amendment_index}: {str(e)}"

@mcp.tool
def search_amendments_by_type(amendment_type: str, decree_file: str =  "", amendment_file: str =  "") -> str:
    """Search amendments by type (Addition, Modification, etc.). Optionally provide decree_file and amendment_file to load different documents."""
    try:
        # Load documents if provided
        if decree_file and amendment_file:
            analyzer.load_decree_data(decree_file)
            analyzer.load_amendment_data(amendment_file)
        
        # Check if documents are loaded
        if not analyzer.amendment_data:
            return json.dumps({
                "error": "Amendment data not loaded. Please provide decree_file and amendment_file parameters or ensure default documents are available."
            }, indent=2, ensure_ascii=False)
        
        result = analyzer.search_amendments_by_type(amendment_type)
        return json.dumps(result, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error searching amendments by type {amendment_type}: {e}")
        return f"Error searching amendments by type {amendment_type}: {str(e)}"

@mcp.tool
def get_detailed_amendment_analysis(amendment_index: int, decree_file: str =  "", amendment_file: str =  "") -> str:
    """Get detailed analysis of an amendment showing original vs new content. Optionally provide decree_file and amendment_file to load different documents."""
    try:
        # Load documents if provided
        if decree_file and amendment_file:
            analyzer.load_decree_data(decree_file)
            analyzer.load_amendment_data(amendment_file)
        
        # Check if documents are loaded
        if not analyzer.amendment_data:
            return json.dumps({
                "error": "Amendment data not loaded. Please provide decree_file and amendment_file parameters or ensure default documents are available."
            }, indent=2, ensure_ascii=False)
        
        result = analyzer.get_detailed_amendment_analysis(amendment_index)
        return json.dumps(result, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error getting detailed amendment analysis for index {amendment_index}: {e}")
        return f"Error getting detailed amendment analysis for index {amendment_index}: {str(e)}"

@mcp.tool
def get_combined_article_view(article_number: str, decree_file: str =  "", amendment_file: str =  "") -> str:
    """Get combined view of article with amendments applied (decree + amendments). Optionally provide decree_file and amendment_file to load different documents."""
    try:
        # Load documents if provided
        if decree_file and amendment_file:
            analyzer.load_decree_data(decree_file)
            analyzer.load_amendment_data(amendment_file)
        
        # Check if documents are loaded
        if not analyzer.decree_data or not analyzer.amendment_data:
            return json.dumps({
                "error": "Documents not loaded. Please provide decree_file and amendment_file parameters or ensure default documents are available."
            }, indent=2, ensure_ascii=False)
        
        result = analyzer.get_combined_article_view(article_number)
        return json.dumps(result, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error getting combined article view for {article_number}: {e}")
        return f"Error getting combined article view for {article_number}: {str(e)}"

# @mcp.tool
# def debug_s3_connection() -> str:
#     """Debug S3 connection and attempt to load default documents"""
#     try:
#         debug_info = {
#             "s3_available": S3_AVAILABLE,
#             "s3_bucket": S3_BUCKET,
#             "default_decree_path": DEFAULT_DECREE_S3_PATH,
#             "default_amendment_path": DEFAULT_AMENDMENT_S3_PATH,
#             "current_documents_loaded": {
#                 "decree_loaded": analyzer.decree_data is not None,
#                 "amendment_loaded": analyzer.amendment_data is not None
#             }
#         }
        
#         if S3_AVAILABLE:
#             # Test S3 connection by trying to load default documents
#             debug_info["s3_test"] = "Attempting to load default documents..."
#             try:
#                 success = analyzer.load_default_documents()
#                 debug_info["s3_test_result"] = "Success" if success else "Failed"
#                 debug_info["documents_after_load"] = {
#                     "decree_loaded": analyzer.decree_data is not None,
#                     "amendment_loaded": analyzer.amendment_data is not None
#                 }
#             except Exception as e:
#                 debug_info["s3_test_result"] = f"Error: {str(e)}"
#         else:
#             debug_info["s3_test"] = "S3 not available"
        
#         return json.dumps(debug_info, indent=2, ensure_ascii=False)
#     except Exception as e:
#         return f"Debug error: {str(e)}"

@mcp.tool
def check_document_status() -> str:
    """Check the status of loaded documents and S3 connectivity"""
    try:
        status = {
            "s3_available": S3_AVAILABLE,
            "s3_bucket": S3_BUCKET,
            "default_decree_path": DEFAULT_DECREE_S3_PATH,
            "default_amendment_path": DEFAULT_AMENDMENT_S3_PATH,
            "documents_loaded": {
                "decree_loaded": analyzer.decree_data is not None,
                "amendment_loaded": analyzer.amendment_data is not None
            }
        }
        
        if analyzer.decree_data:
            status["decree_info"] = {
                "title": analyzer.decree_data.get("metadata", {}).get("title", "N/A"),
                "decree_number": analyzer.decree_data.get("metadata", {}).get("decree_number", "N/A")
            }
        
        if analyzer.amendment_data:
            status["amendment_info"] = {
                "title": analyzer.amendment_data.get("metadata", {}).get("title", "N/A"),
                "decree_number": analyzer.amendment_data.get("metadata", {}).get("decree_number", "N/A"),
                "total_amendments": len(analyzer.amendment_data.get("amendments", []))
            }
        
        return json.dumps(status, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error checking document status: {e}")
        return f"Error checking document status: {str(e)}"

@mcp.tool
def generate_analysis_report(report_type: str = "comprehensive", s3_bucket: str =  "") -> str:
    """Generate a comprehensive analysis report with PDF and return summary with download link"""
    try:
        if not analyzer.amendment_data:
            return json.dumps({
                "status": "error",
                "message": "Amendment data not loaded. Please load documents first using load_legal_documents tool."
            }, indent=2, ensure_ascii=False)
        
        # Check if report generator is available
        if not REPORT_GENERATOR_AVAILABLE:
            return json.dumps({
                "status": "error",
                "message": "PDF report generation not available. Please install required dependencies: pip install reportlab boto3 botocore",
                "analysis_summary": analyzer.summarize_all_changes()
            }, indent=2, ensure_ascii=False)
        
        # Generate summary first
        summary = analyzer.summarize_all_changes()
        summary_data = summary.get("summary", {})
        
        # Get document metadata
        metadata = {}
        if analyzer.decree_data:
            metadata["decree"] = analyzer.decree_data.get("metadata", {})
        if analyzer.amendment_data:
            metadata["amendment"] = analyzer.amendment_data.get("metadata", {})
        
        # Initialize report generator
        report_generator = LegalAmendmentReportGenerator(s3_bucket=s3_bucket)
        
        # Generate PDF report
        pdf_url = report_generator.generate_pdf_report(analyzer, report_type)
        
        # Create short summary
        short_summary = {
            "analysis_summary": {
                "total_amendments": summary_data.get("total_amendments", 0),
                "articles_affected": summary_data.get("articles_affected", 0),
                "new_articles_added": summary_data.get("new_articles_added", 0),
                "amendment_types": summary_data.get("amendment_types", {}),
                "most_affected_articles": summary_data.get("affected_articles", [])[:5],
                "new_articles": summary_data.get("new_articles", [])
            },
            "document_info": {
                "decree_title": metadata.get("decree", {}).get("title", "N/A"),
                "amendment_title": metadata.get("amendment", {}).get("title", "N/A"),
                "decree_number": metadata.get("decree", {}).get("decree_number", "N/A"),
                "amendment_number": metadata.get("amendment", {}).get("decree_number", "N/A")
            },
            "report_details": {
                "report_type": report_type,
                "pdf_url": pdf_url,
                "expires_in": "7 days",
                "generated_at": datetime.now().isoformat(),
                "status": "success"
            }
        }
        
        return json.dumps(short_summary, indent=2, ensure_ascii=False)
        
    except Exception as e:
        logger.error(f"Error generating analysis report: {e}")
        return json.dumps({
            "status": "error",
            "error": str(e),
            "message": "Failed to generate analysis report"
        }, indent=2, ensure_ascii=False)

if __name__ == "__main__":
    print("🚀Starting server... ")

    # Debug Mode
    #  uv run mcp dev server.py

    # Production Mode
    # uv run server.py --server_type=sse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--server_type", type=str, default="sse", choices=["sse", "stdio"]
    )
    print("Server type: ", parser.parse_args().server_type)
    print("Launching on Port: ", 3000)
    print('Check "http://localhost:3000/sse" for the server status')

    args = parser.parse_args()
    mcp.run(args.server_type)