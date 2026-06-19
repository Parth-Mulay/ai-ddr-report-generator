import os
from datetime import datetime
import logging
from PIL import Image as PILImage

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage, PageBreak, KeepTogether, HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfgen import canvas

logger = logging.getLogger(__name__)

# Premium Palette
COLOR_PRIMARY = colors.HexColor("#1E293B")    # Slate Dark
COLOR_SECONDARY = colors.HexColor("#3B82F6")  # Muted Blue
COLOR_TEXT = colors.HexColor("#334155")       # Charcoal Text
COLOR_LIGHT_BG = colors.HexColor("#F8FAF4")   # Ivory/Light Grey
COLOR_BORDER = colors.HexColor("#E2E8F0")     # Cool Grey border
COLOR_ALERT = colors.HexColor("#EF4444")      # Red conflict alert

# Severity Colors
SEVERITY_COLORS = {
    "low": colors.HexColor("#10B981"),        # Emerald Green
    "medium": colors.HexColor("#F59E0B"),     # Amber Orange
    "high": colors.HexColor("#EF4444"),       # Red
    "critical": colors.HexColor("#991B1B")    # Deep Crimson
}

class NumberedCanvas(canvas.Canvas):
    """
    Custom canvas to calculate total page count dynamically 
    and draw 'Page X of Y' on every page (except cover page).
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_number(num_pages)
            super().showPage()
        super().save()

    def draw_page_number(self, page_count):
        # We don't draw header/footer on page 1 (cover page)
        if self._pageNumber == 1:
            return
            
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(COLOR_TEXT)
        
        # Header (Top)
        self.drawString(54, 750, "Detailed Diagnostic Report (DDR) — Confidential")
        self.setStrokeColor(COLOR_BORDER)
        self.setLineWidth(0.5)
        self.line(54, 742, letter[0] - 54, 742)
        
        # Footer (Bottom)
        self.line(54, 54, letter[0] - 54, 54)
        page_text = f"Page {self._pageNumber} of {page_count}"
        self.drawRightString(letter[0] - 54, 40, page_text)
        self.drawString(54, 40, f"Generated Date: {datetime.now().strftime('%Y-%m-%d')}")
        self.restoreState()


def get_image_flowable(img_filename: str, temp_images_dir: str) -> object:
    """
    Loads an image from temp directory, resizes maintaining aspect ratio, 
    and returns a ReportLab Image flowable or a styled 'Not Available' table.
    """
    fallback_text = "<b>Image Not Available</b>"
    
    if not img_filename or img_filename.lower() == "image not available":
        return create_fallback_image_box(fallback_text)
        
    img_path = os.path.join(temp_images_dir, img_filename)
    if not os.path.exists(img_path):
        logger.warning(f"Extracted image {img_filename} not found at {img_path}")
        return create_fallback_image_box(fallback_text)
        
    try:
        # Get aspect ratio
        with PILImage.open(img_path) as pil_img:
            width, height = pil_img.size
            aspect = height / width
            
        # Target width of 260 points fits nicely in 2-column or full width lists
        target_width = 260
        target_height = target_width * aspect
        
        # Prevent overly tall images
        if target_height > 180:
            target_height = 180
            target_width = target_height / aspect
            
        return RLImage(img_path, width=target_width, height=target_height)
    except Exception as e:
        logger.error(f"Error preparing report image {img_filename}: {e}")
        return create_fallback_image_box(f"{fallback_text}<br/><font size=7 color=grey>{str(e)}</font>")


def create_fallback_image_box(text: str) -> Table:
    """
    Creates a styled grey placeholder table when an image is unavailable.
    """
    style = ParagraphStyle(
        'FallbackImgStyle',
        fontName='Helvetica-Oblique',
        fontSize=9,
        textColor=colors.HexColor("#64748B"),
        alignment=1 # Centered
    )
    p = Paragraph(text, style)
    t = Table([[p]], colWidths=[260], rowHeights=[80])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F1F5F9")),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#CBD5E1")),
    ]))
    return t


def generate_ddr_pdf(analysis_data: dict, temp_images_dir: str, output_pdf_path: str):
    """
    Compiles the AI analysis and images into a premium structured PDF document.
    """
    # Create target folder if missing
    dir_name = os.path.dirname(output_pdf_path)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)
    
    # Page setup - Margins: Top 1.0 in (72pt) to clear header, bottom 1.0 in, side 0.75 in
    doc = SimpleDocTemplate(
        output_pdf_path,
        pagesize=letter,
        leftMargin=54,
        rightMargin=54,
        topMargin=72,
        bottomMargin=72
    )
    
    styles = getSampleStyleSheet()
    
    # Create or update custom paragraph styles
    styles.add(ParagraphStyle(
        name='DDRTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=28,
        leading=34,
        textColor=COLOR_PRIMARY,
        alignment=1, # Centered
        spaceAfter=15
    ))
    
    styles.add(ParagraphStyle(
        name='DDRSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=13,
        leading=16,
        textColor=COLOR_SECONDARY,
        alignment=1, # Centered
        spaceAfter=30
    ))
    
    styles.add(ParagraphStyle(
        name='DDRHeading1',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=15,
        leading=18,
        textColor=COLOR_PRIMARY,
        spaceBefore=14,
        spaceAfter=8,
        keepWithNext=True
    ))

    styles.add(ParagraphStyle(
        name='DDRHeading2',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=11,
        leading=14,
        textColor=COLOR_SECONDARY,
        spaceBefore=10,
        spaceAfter=4,
        keepWithNext=True
    ))

    styles.add(ParagraphStyle(
        name='DDRBody',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9.5,
        leading=14,
        textColor=COLOR_TEXT,
        spaceAfter=6
    ))

    styles.add(ParagraphStyle(
        name='DDRBodyBold',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9.5,
        leading=14,
        textColor=COLOR_TEXT,
        spaceAfter=6
    ))

    styles.add(ParagraphStyle(
        name='ConflictText',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#7F1D1D")
    ))

    styles.add(ParagraphStyle(
        name='SeverityBadgeText',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=11,
        leading=14,
        textColor=colors.white,
        alignment=1 # Centered
    ))

    story = []
    
    # ==================== COVER PAGE ====================
    story.append(Spacer(1, 150))
    story.append(Paragraph("DETAILED DIAGNOSTIC REPORT (DDR)", styles['DDRTitle']))
    
    # Decorative line
    story.append(HRFlowable(
        width="60%",
        thickness=3,
        color=COLOR_SECONDARY,
        spaceBefore=10,
        spaceAfter=15,
        hAlign='CENTER'
    ))
    
    story.append(Paragraph("AI-Assisted Property Inspection & Thermal Anomaly Analysis", styles['DDRSubtitle']))
    
    story.append(Spacer(1, 120))
    
    # Cover Metadata Block
    meta_style = ParagraphStyle('CoverMeta', fontName='Helvetica', fontSize=10, leading=16, textColor=COLOR_TEXT, alignment=1)
    date_str = datetime.now().strftime("%B %d, %Y")
    story.append(Paragraph(f"<b>Generated Date:</b> {date_str}", meta_style))
    story.append(Paragraph("<b>Status:</b> Completed Analysis", meta_style))
    story.append(Paragraph("<b>Report Type:</b> Combined Diagnostics", meta_style))
    
    story.append(PageBreak())
    
    # ==================== PAGE 2+: REPORT CONTENT ====================
    
    # 1. Property Issue Summary
    story.append(Paragraph("1. Property Issue Summary", styles['DDRHeading1']))
    summary_text = analysis_data.get("property_issue_summary", "Not Available")
    story.append(Paragraph(summary_text, styles['DDRBody']))
    story.append(Spacer(1, 10))
    
    # 2. Area-wise Observations
    story.append(Paragraph("2. Area-wise Observations", styles['DDRHeading1']))
    observations = analysis_data.get("area_wise_observations", [])
    
    if not observations:
        story.append(Paragraph("Not Available", styles['DDRBody']))
    else:
        for idx, obs in enumerate(observations, start=1):
            area_title = f"Area {idx}: {obs.get('area', 'Unnamed Area')}"
            
            # Keep area observation unit together to avoid weird page splits
            area_story = []
            area_story.append(Paragraph(area_title, styles['DDRHeading2']))
            
            # Format observations as a key-value side-by-side or clean list layout
            obs_details = (
                f"<b>Observation:</b> {obs.get('observation', 'Not Available')}<br/>"
                f"<b>Supporting Evidence:</b> {obs.get('supporting_evidence', 'Not Available')}<br/>"
                f"<b>Related Thermal Finding:</b> {obs.get('related_thermal_finding', 'Not Available')}"
            )
            
            # Image Flowable
            img_file = obs.get("relevant_image_filename", "Image Not Available")
            img_flowable = get_image_flowable(img_file, temp_images_dir)
            
            # Create a table layout putting text on the left (wider) and image on the right (narrower)
            detail_p = Paragraph(obs_details, styles['DDRBody'])
            
            # Content table
            data = [[detail_p, img_flowable]]
            table_col_widths = [240, 260] # total width 500pt fits in margins (letter width is 612, -108 = 504)
            obs_table = Table(data, colWidths=table_col_widths)
            obs_table.setStyle(TableStyle([
                ('VALIGN', (0,0), (-1,-1), 'TOP'),
                ('RIGHTPADDING', (0,0), (0,0), 10),
                ('LEFTPADDING', (1,0), (1,0), 5),
                ('BOTTOMPADDING', (0,0), (-1,-1), 10),
            ]))
            
            area_story.append(obs_table)
            area_story.append(Spacer(1, 5))
            
            story.append(KeepTogether(area_story))
            
    story.append(Spacer(1, 10))
    
    # 3. Probable Root Cause
    story.append(Paragraph("3. Probable Root Cause Analysis", styles['DDRHeading1']))
    root_cause = analysis_data.get("probable_root_cause", "Not Available")
    story.append(Paragraph(root_cause, styles['DDRBody']))
    story.append(Spacer(1, 10))
    
    # 4. Severity Assessment
    story.append(Paragraph("4. Severity Assessment", styles['DDRHeading1']))
    severity_info = analysis_data.get("severity_assessment", {})
    severity_level = severity_info.get("level", "Low").strip()
    severity_reasoning = severity_info.get("reasoning", "Not Available")
    
    # Map level to color
    badge_color = SEVERITY_COLORS.get(severity_level.lower(), colors.HexColor("#64748B"))
    
    # Severity Badge Table
    badge_para = Paragraph(f"{severity_level.upper()}", styles['SeverityBadgeText'])
    badge_table = Table([[badge_para]], colWidths=[90], rowHeights=[24])
    badge_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), badge_color),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('TOPPADDING', (0,0), (-1,-1), 4),
    ]))
    
    # Create Side-by-Side: Badge on left, Reasoning on right
    reason_para = Paragraph(f"<b>Reasoning:</b> {severity_reasoning}", styles['DDRBody'])
    sev_table = Table([[badge_table, reason_para]], colWidths=[100, 400])
    sev_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('RIGHTPADDING', (0,0), (0,0), 10),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(KeepTogether([sev_table]))
    story.append(Spacer(1, 10))

    # 5. Recommended Actions
    story.append(Paragraph("5. Recommended Actions", styles['DDRHeading1']))
    recommendations = analysis_data.get("recommended_actions", [])
    if not recommendations:
        story.append(Paragraph("Not Available", styles['DDRBody']))
    else:
        for idx, rec in enumerate(recommendations, start=1):
            bullet_text = f"<b>{idx}.</b> {rec}"
            story.append(Paragraph(bullet_text, styles['DDRBody']))
    story.append(Spacer(1, 10))
    
    # 6. Additional Notes & Conflicts
    story.append(Paragraph("6. Additional Notes & Conflicts", styles['DDRHeading1']))
    
    # Render conflicts if detected
    conflicts = analysis_data.get("conflicts_detected", [])
    conflict_story = []
    
    if conflicts:
        conflict_story.append(Paragraph("<b>Contradictions and Conflicts Identified between Reports:</b>", styles['DDRHeading2']))
        for conf in conflicts:
            conflict_details = (
                f"<b>Conflict:</b> {conf.get('conflict_summary', 'Contradiction detected')}<br/>"
                f"• <i>Inspection Report:</i> {conf.get('inspection_finding', 'Not Available')}<br/>"
                f"• <i>Thermal Report:</i> {conf.get('thermal_finding', 'Not Available')}<br/>"
                f"<b>Recommendation:</b> {conf.get('recommendation', 'Further inspection required.')}"
            )
            
            # Format inside an alert box
            box_p = Paragraph(conflict_details, styles['ConflictText'])
            box_table = Table([[box_p]], colWidths=[490])
            box_table.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#FEF2F2")), # Very light red
                ('VALIGN', (0,0), (-1,-1), 'TOP'),
                ('BOX', (0,0), (-1,-1), 1, COLOR_ALERT),
                ('TOPPADDING', (0,0), (-1,-1), 8),
                ('BOTTOMPADDING', (0,0), (-1,-1), 8),
                ('LEFTPADDING', (0,0), (-1,-1), 10),
                ('RIGHTPADDING', (0,0), (-1,-1), 10),
            ]))
            conflict_story.append(box_table)
            conflict_story.append(Spacer(1, 5))
            
        story.append(KeepTogether(conflict_story))
        
    additional_notes = analysis_data.get("additional_notes", "Not Available")
    if additional_notes and additional_notes.lower() != "not available":
        story.append(Paragraph(additional_notes, styles['DDRBody']))
    elif not conflicts:
        story.append(Paragraph("Not Available", styles['DDRBody']))
        
    story.append(Spacer(1, 10))

    # 7. Missing or Unclear Information
    story.append(Paragraph("7. Missing or Unclear Information", styles['DDRHeading1']))
    missing_info = analysis_data.get("missing_or_unclear_information", "Not Available")
    story.append(Paragraph(missing_info, styles['DDRBody']))
    
    # Build Document using NumberedCanvas
    doc.build(story, canvasmaker=NumberedCanvas)
    logger.info(f"DDR Report PDF generated successfully at {output_pdf_path}")
