import os
import uuid
import logging
import fitz  # PyMuPDF
from PIL import Image
import io

logger = logging.getLogger(__name__)

def extract_images_from_pdf(pdf_path: str, doc_ref: str, output_dir: str) -> list:
    """
    Extract all images from a PDF file and save them as files.
    
    Args:
        pdf_path (str): Path to the source PDF.
        doc_ref (str): Label indicating source document (e.g. 'inspection' or 'thermal').
        output_dir (str): Base directory where images will be saved.
        
    Returns:
        list: A list of dicts with image metadata:
              [
                {
                  "filepath": "absolute/path/to/img.png",
                  "filename": "img.png",
                  "page": int,
                  "doc_ref": str,
                  "context": str (text on page)
                },
                ...
              ]
    """
    extracted_images = []
    
    if not os.path.exists(pdf_path):
        logger.error(f"Cannot extract images, source file not found: {pdf_path}")
        return extracted_images
        
    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)
    
    try:
        logger.info(f"Extracting images from {pdf_path} (ref: {doc_ref})")
        doc = fitz.open(pdf_path)
        
        total_images_saved = 0
        MAX_IMAGES_PER_PAGE = 5
        MAX_TOTAL_IMAGES = 50
        MIN_IMAGE_DIMENSION = 150
        
        for page_num in range(len(doc)):
            if total_images_saved >= MAX_TOTAL_IMAGES:
                logger.info(f"Reached max total images limit ({MAX_TOTAL_IMAGES}). Skipping remaining pages.")
                break
                
            page = doc[page_num]
            page_text = page.get_text().strip()
            image_list = page.get_images(full=True)
            
            logger.info(f"Page {page_num+1} has {len(image_list)} images.")
            
            page_images_saved = 0
            for img_idx, img in enumerate(image_list, start=1):
                if page_images_saved >= MAX_IMAGES_PER_PAGE:
                    logger.debug(f"Reached page image limit ({MAX_IMAGES_PER_PAGE}) on page {page_num+1}. Skipping remaining page images.")
                    break
                if total_images_saved >= MAX_TOTAL_IMAGES:
                    break
                    
                xref = img[0]
                base_image = doc.extract_image(xref)
                image_bytes = base_image["image"]
                image_ext = base_image["ext"]
                
                # Use PIL to load and verify/sanitize the image
                try:
                    image = Image.open(io.BytesIO(image_bytes))
                    
                    # Reject small images (icons, lines, grid lines, shapes)
                    if image.width < MIN_IMAGE_DIMENSION or image.height < MIN_IMAGE_DIMENSION:
                        logger.debug(f"Skipping decorative/small image {xref} of size {image.width}x{image.height}")
                        continue
                        
                    # Generate a unique secure filename to avoid conflicts and directory traversal
                    unique_id = uuid.uuid4().hex[:12]
                    filename = f"{doc_ref}_page_{page_num+1}_img_{img_idx}_{unique_id}.{image_ext}"
                    filepath = os.path.join(output_dir, filename)
                    
                    # Save the image
                    image.save(filepath)
                    
                    # Clean and shorten context text to save prompt tokens
                    cleaned_context = " ".join(page_text[:200].split())
                    extracted_images.append({
                        "filepath": filepath,
                        "filename": filename,
                        "page": page_num + 1,
                        "doc_ref": doc_ref,
                        "context": cleaned_context
                    })
                    
                    page_images_saved += 1
                    total_images_saved += 1
                    logger.info(f"Extracted image {filename} from page {page_num+1} (Total: {total_images_saved})")
                except Exception as img_err:
                    logger.error(f"Failed to process image xref {xref} on page {page_num+1}: {img_err}")
                    
        doc.close()
    except Exception as e:
        logger.error(f"Image extraction failed for {pdf_path}: {e}", exc_info=True)
        
    return extracted_images
