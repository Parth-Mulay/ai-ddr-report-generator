import logging
import os
import fitz  # PyMuPDF
import pdfplumber

logger = logging.getLogger(__name__)

def extract_text_from_pdf(pdf_path: str) -> str:
    """
    Extract text content from a PDF file using PyMuPDF (fitz) with fallback to pdfplumber.
    
    Args:
        pdf_path (str): The absolute path to the PDF file.
        
    Returns:
        str: The extracted text content.
    """
    if not os.path.exists(pdf_path):
        logger.error(f"PDF file not found at path: {pdf_path}")
        return "Error: File not found."
    
    extracted_text = ""
    
    # Primary: PyMuPDF (fitz)
    try:
        logger.info(f"Attempting primary text extraction with PyMuPDF for: {pdf_path}")
        doc = fitz.open(pdf_path)
        pages_text = []
        for page_num, page in enumerate(doc, start=1):
            text = page.get_text()
            if text:
                pages_text.append(f"--- Page {page_num} ---\n{text}")
        
        extracted_text = "\n".join(pages_text).strip()
        doc.close()
        
        if len(extracted_text) > 50:
            logger.info(f"PyMuPDF successfully extracted {len(extracted_text)} characters.")
            return extracted_text
        else:
            logger.warning("PyMuPDF extracted very little or empty text. Trying fallback parser...")
    except Exception as e:
        logger.error(f"PyMuPDF text extraction failed: {str(e)}. Attempting fallback parser...", exc_info=True)
    
    # Fallback: pdfplumber
    try:
        logger.info(f"Attempting fallback text extraction with pdfplumber for: {pdf_path}")
        pages_text = []
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages, start=1):
                text = page.extract_text()
                if text:
                    pages_text.append(f"--- Page {page_num} ---\n{text}")
        
        extracted_text = "\n".join(pages_text).strip()
        if extracted_text:
            logger.info(f"pdfplumber successfully extracted {len(extracted_text)} characters.")
            return extracted_text
    except Exception as e:
        logger.error(f"Fallback pdfplumber text extraction failed: {str(e)}", exc_info=True)
    
    if not extracted_text:
        logger.warning(f"Failed to extract any text from: {pdf_path}")
        return "Extraction issue: Could not read text content from PDF."
        
    return extracted_text
