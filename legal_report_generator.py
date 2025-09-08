"""
Enhanced Report Generation Tool for Legal Amendment Analysis
Creates professional PDF reports and uploads to S3 with public URLs
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
import boto3
from botocore.exceptions import ClientError
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
import uuid
import os

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class LegalAmendmentReportGenerator:
    """Generates professional PDF reports for legal amendment analysis"""
    
    def __init__(self, s3_bucket: str = None, aws_access_key: str = None, aws_secret_key: str = None):
        self.s3_bucket = s3_bucket or os.getenv('S3_BUCKET', 'legal-amendment-reports')
        self.aws_access_key = aws_access_key or os.getenv('AWS_ACCESS_KEY_ID')
        self.aws_secret_key = aws_secret_key or os.getenv('AWS_SECRET_ACCESS_KEY')
        
        # Initialize S3 client
        if self.aws_access_key and self.aws_secret_key:
            self.s3_client = boto3.client(
                's3',
                aws_access_key_id=self.aws_access_key,
                aws_secret_access_key=self.aws_secret_key,
                region_name='us-east-1'
            )
        else:
            self.s3_client = boto3.client('s3')  # Uses default AWS credentials
        
        # Initialize styles
        self.styles = getSampleStyleSheet()
        self.setup_custom_styles()
    
    def setup_custom_styles(self):
        """Setup custom paragraph styles for the report"""
        # Title style
        self.styles.add(ParagraphStyle(
            name='CustomTitle',
            parent=self.styles['Heading1'],
            fontSize=18,
            spaceAfter=30,
            alignment=TA_CENTER,
            textColor=colors.darkblue
        ))
        
        # Section header style
        self.styles.add(ParagraphStyle(
            name='SectionHeader',
            parent=self.styles['Heading2'],
            fontSize=14,
            spaceAfter=12,
            spaceBefore=20,
            textColor=colors.darkblue
        ))
        
        # Subsection style
        self.styles.add(ParagraphStyle(
            name='Subsection',
            parent=self.styles['Heading3'],
            fontSize=12,
            spaceAfter=8,
            spaceBefore=12,
            textColor=colors.darkgreen
        ))
        
        # Body text style
        self.styles.add(ParagraphStyle(
            name='BodyTextStyle',
            parent=self.styles['Normal'],
            fontSize=10,
            spaceAfter=6,
            alignment=TA_JUSTIFY
        ))
        
        # Table header style
        self.styles.add(ParagraphStyle(
            name='TableHeader',
            parent=self.styles['Normal'],
            fontSize=10,
            alignment=TA_CENTER,
            textColor=colors.white
        ))
    
    def generate_pdf_report(self, analyzer, report_type: str = "comprehensive") -> str:
        """Generate PDF report and upload to S3"""
        try:
            # Generate unique filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"legal_amendment_report_{timestamp}_{uuid.uuid4().hex[:8]}.pdf"
            
            # Create temporary local file
            temp_path = Path(f"/tmp/{filename}")
            
            # Generate PDF content
            doc = SimpleDocTemplate(str(temp_path), pagesize=A4)
            story = []
            
            # Add content based on report type
            if report_type == "executive":
                story.extend(self._create_executive_report(analyzer))
            elif report_type == "detailed":
                story.extend(self._create_detailed_report(analyzer))
            else:  # comprehensive
                story.extend(self._create_comprehensive_report(analyzer))
            
            # Build PDF
            doc.build(story)
            
            # Upload to S3
            s3_url = self._upload_to_s3(temp_path, filename)
            
            # Clean up local file
            temp_path.unlink()
            
            return s3_url
            
        except Exception as e:
            logger.error(f"Error generating PDF report: {e}")
            raise e
    
    def _create_executive_report(self, analyzer) -> List:
        """Create executive summary report content"""
        story = []
        
        # Title
        story.append(Paragraph("Legal Amendment Analysis Report", self.styles['CustomTitle']))
        story.append(Paragraph("Executive Summary", self.styles['SectionHeader']))
        story.append(Spacer(1, 12))
        
        # Document metadata
        metadata = self._get_document_metadata(analyzer)
        story.extend(self._add_metadata_section(metadata))
        
        # Key findings
        summary = analyzer.summarize_all_changes()
        story.extend(self._add_key_findings_section(summary))
        
        # Impact assessment
        story.extend(self._add_impact_assessment_section(summary))
        
        return story
    
    def _create_detailed_report(self, analyzer) -> List:
        """Create detailed analysis report content"""
        story = []
        
        # Title and metadata
        story.append(Paragraph("Legal Amendment Analysis Report", self.styles['CustomTitle']))
        story.append(Paragraph("Detailed Analysis", self.styles['SectionHeader']))
        story.append(Spacer(1, 12))
        
        # Include executive summary sections
        metadata = self._get_document_metadata(analyzer)
        story.extend(self._add_metadata_section(metadata))
        
        summary = analyzer.summarize_all_changes()
        story.extend(self._add_key_findings_section(summary))
        
        # Detailed amendments
        story.extend(self._add_detailed_amendments_section(analyzer, summary))
        
        # Article-by-article analysis
        story.extend(self._add_article_analysis_section(analyzer, summary))
        
        return story
    
    def _create_comprehensive_report(self, analyzer) -> List:
        """Create comprehensive report content"""
        story = []
        
        # Title page
        story.append(Paragraph("Legal Amendment Analysis Report", self.styles['CustomTitle']))
        story.append(Paragraph("Comprehensive Analysis", self.styles['SectionHeader']))
        story.append(Spacer(1, 20))
        
        # Table of contents
        story.extend(self._add_table_of_contents())
        story.append(PageBreak())
        
        # Executive summary
        story.extend(self._create_executive_report(analyzer))
        story.append(PageBreak())
        
        # Detailed analysis
        story.extend(self._create_detailed_report(analyzer))
        story.append(PageBreak())
        
        # Recommendations
        summary = analyzer.summarize_all_changes()
        story.extend(self._add_recommendations_section(summary))
        
        # Appendix
        story.extend(self._add_appendix_section(analyzer))
        
        return story
    
    def _add_metadata_section(self, metadata: Dict) -> List:
        """Add document metadata section"""
        story = []
        story.append(Paragraph("Document Information", self.styles['Subsection']))
        
        # Create metadata table
        data = [
            ['Field', 'Decree', 'Amendment'],
            ['Title', metadata.get('decree', {}).get('title', 'N/A'), metadata.get('amendment', {}).get('title', 'N/A')],
            ['Document Number', metadata.get('decree', {}).get('decree_number', 'N/A'), metadata.get('amendment', {}).get('decree_number', 'N/A')],
            ['Date', metadata.get('decree', {}).get('date', 'N/A'), metadata.get('amendment', {}).get('date', 'N/A')],
            ['Page Count', str(metadata.get('decree', {}).get('page_count', 'N/A')), str(metadata.get('amendment', {}).get('page_count', 'N/A'))]
        ]
        
        table = Table(data, colWidths=[1.5*inch, 2*inch, 2*inch])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        
        story.append(table)
        story.append(Spacer(1, 12))
        
        return story
    
    def _add_key_findings_section(self, summary: Dict) -> List:
        """Add key findings section"""
        story = []
        story.append(Paragraph("Key Findings", self.styles['Subsection']))
        
        summary_data = summary.get('summary', {})
        
        findings_data = [
            ['Metric', 'Value'],
            ['Total Amendments', str(summary_data.get('total_amendments', 0))],
            ['Articles Affected', str(summary_data.get('articles_affected', 0))],
            ['New Articles Added', str(summary_data.get('new_articles_added', 0))],
            ['Amendment Types', ', '.join([f"{k}: {v}" for k, v in summary_data.get('amendment_types', {}).items()])]
        ]
        
        table = Table(findings_data, colWidths=[2*inch, 3*inch])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.darkgreen),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.lightgrey),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        
        story.append(table)
        story.append(Spacer(1, 12))
        
        return story
    
    def _add_impact_assessment_section(self, summary: Dict) -> List:
        """Add impact assessment section"""
        story = []
        story.append(Paragraph("Impact Assessment", self.styles['Subsection']))
        
        summary_data = summary.get('summary', {})
        affected_articles = summary_data.get('affected_articles', [])
        new_articles = summary_data.get('new_articles', [])
        
        # Most affected articles
        story.append(Paragraph("Most Affected Articles:", self.styles['BodyText']))
        for article in affected_articles[:5]:
            story.append(Paragraph(f"• Article {article}", self.styles['BodyText']))
        
        story.append(Spacer(1, 6))
        
        # New articles
        if new_articles:
            story.append(Paragraph("New Articles Added:", self.styles['BodyText']))
            for article in new_articles:
                story.append(Paragraph(f"• Article {article}", self.styles['BodyText']))
        
        story.append(Spacer(1, 12))
        
        return story
    
    def _add_detailed_amendments_section(self, analyzer, summary: Dict) -> List:
        """Add detailed amendments section"""
        story = []
        story.append(Paragraph("Detailed Amendment Analysis", self.styles['Subsection']))
        
        detailed_changes = summary.get('detailed_changes', [])
        
        for i, change in enumerate(detailed_changes[:10]):  # Limit to first 10 for readability
            story.append(Paragraph(f"Amendment {i+1}: {change.get('amendment_type', 'Unknown')}", self.styles['BodyText']))
            story.append(Paragraph(f"Target Article: {change.get('target_article', 'N/A')}", self.styles['BodyText']))
            if change.get('target_clause'):
                story.append(Paragraph(f"Target Clause: {change.get('target_clause')}", self.styles['BodyText']))
            story.append(Spacer(1, 6))
        
        story.append(Spacer(1, 12))
        
        return story
    
    def _add_article_analysis_section(self, analyzer, summary: Dict) -> List:
        """Add article-by-article analysis section"""
        story = []
        story.append(Paragraph("Article-by-Article Analysis", self.styles['Subsection']))
        
        affected_articles = summary.get('summary', {}).get('affected_articles', [])
        
        for article_num in affected_articles[:5]:  # Limit to first 5 articles
            story.append(Paragraph(f"Article {article_num}", self.styles['BodyText']))
            
            # Get article content
            content = analyzer.get_article_content(article_num)
            if 'error' not in content:
                story.append(Paragraph(f"Title: {content.get('title', 'N/A')}", self.styles['BodyText']))
                story.append(Paragraph(f"Chapter: {content.get('chapter_number', 'N/A')} - {content.get('chapter_title', 'N/A')}", self.styles['BodyText']))
            
            # Get changes
            changes = analyzer.get_changes_in_article(article_num)
            story.append(Paragraph(f"Changes: {changes.get('total_changes', 0)}", self.styles['BodyText']))
            
            story.append(Spacer(1, 6))
        
        story.append(Spacer(1, 12))
        
        return story
    
    def _add_recommendations_section(self, summary: Dict) -> List:
        """Add recommendations section"""
        story = []
        story.append(Paragraph("Recommendations", self.styles['Subsection']))
        
        recommendations = self._generate_recommendations(summary)
        
        for i, rec in enumerate(recommendations, 1):
            story.append(Paragraph(f"{i}. {rec}", self.styles['BodyText']))
        
        story.append(Spacer(1, 12))
        
        return story
    
    def _add_appendix_section(self, analyzer) -> List:
        """Add appendix section"""
        story = []
        story.append(Paragraph("Appendix", self.styles['Subsection']))
        story.append(Paragraph("Detailed Amendment Data", self.styles['BodyText']))
        
        # Add raw data tables if needed
        story.append(Paragraph("This section contains detailed technical data for reference.", self.styles['BodyText']))
        
        story.append(Spacer(1, 12))
        
        return story
    
    def _add_table_of_contents(self) -> List:
        """Add table of contents"""
        story = []
        story.append(Paragraph("Table of Contents", self.styles['SectionHeader']))
        
        toc_items = [
            "1. Document Information",
            "2. Key Findings",
            "3. Impact Assessment",
            "4. Detailed Amendment Analysis",
            "5. Article-by-Article Analysis",
            "6. Recommendations",
            "7. Appendix"
        ]
        
        for item in toc_items:
            story.append(Paragraph(item, self.styles['BodyText']))
        
        story.append(Spacer(1, 12))
        
        return story
    
    def _get_document_metadata(self, analyzer) -> Dict:
        """Get document metadata"""
        metadata = {}
        if analyzer.decree_data:
            metadata["decree"] = analyzer.decree_data.get("metadata", {})
        if analyzer.amendment_data:
            metadata["amendment"] = analyzer.amendment_data.get("metadata", {})
        return metadata
    
    def _generate_recommendations(self, summary: Dict) -> List[str]:
        """Generate recommendations based on analysis"""
        recommendations = []
        
        amendment_types = summary.get('summary', {}).get('amendment_types', {})
        new_articles = summary.get('summary', {}).get('new_articles', [])
        
        if amendment_types.get("Addition", 0) > 0:
            recommendations.append("Review new additions for compliance requirements and implementation timeline")
        
        if amendment_types.get("Modification", 0) > 0:
            recommendations.append("Update existing procedures and policies based on modifications")
        
        if amendment_types.get("Deletion", 0) > 0:
            recommendations.append("Remove obsolete procedures and update related documentation")
        
        if new_articles:
            recommendations.append(f"Implement new articles: {', '.join(new_articles)} with proper training and documentation")
        
        recommendations.append("Conduct impact assessment on affected business processes")
        recommendations.append("Update legal compliance documentation and procedures")
        
        return recommendations
    
    def _upload_to_s3(self, file_path: Path, filename: str) -> str:
        """Upload file to S3 and return public URL"""
        try:
            # Upload file
            # self.s3_client.upload_file(str(file_path), self.s3_bucket, filename)

            s3_key = f"{'reports'}/{filename}"
        
            # Upload file to S3
            self.s3_client.upload_file(str(file_path), self.s3_bucket, s3_key)
            
            # Generate presigned URL valid for 7 days
            url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': self.s3_bucket, 'Key': filename},
                ExpiresIn=604800  # 7 days in seconds
            )
            
            logger.info(f"PDF report uploaded to S3: {url}")
            return url
            
        except ClientError as e:
            logger.error(f"Error uploading to S3: {e}")
            raise e
