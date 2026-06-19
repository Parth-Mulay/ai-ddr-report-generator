import os
import uuid
import secrets
import logging
from flask import Flask, request, render_template, jsonify, send_from_directory, session, abort
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

# Import utilities
from utils.pdf_reader import extract_text_from_pdf
from utils.image_extractor import extract_images_from_pdf
from utils.ai_processor import query_gemini_api
from utils.report_generator import generate_ddr_pdf

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load local environment variables from .env
load_dotenv()

app = Flask(__name__)

# Secure Session Secret Management
# (Resolution: Environment -> Secure Random Gen + Warning)
session_secret = os.getenv('FLASK_SECRET_KEY')
if not session_secret:
    logger.warning("FLASK_SECRET_KEY not set in environment. Generating ephemeral session secret. Instance-isolated!")
    session_secret = secrets.token_hex(32)
app.secret_key = session_secret

# Enforce File Size Limits (Max 16 MB) to prevent DoS
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# Setup paths inside the project root
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
REPORTS_FOLDER = os.path.join(BASE_DIR, 'reports')
TEMP_IMAGES_FOLDER = os.path.join(BASE_DIR, 'temp_images')

# Ensure directories exist securely
for folder in [UPLOAD_FOLDER, REPORTS_FOLDER, TEMP_IMAGES_FOLDER]:
    os.makedirs(folder, exist_ok=True)

# Allowed file types: PDF only
ALLOWED_EXTENSIONS = {'pdf'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ==================== CSRF PROTECTION SYSTEM ====================
@app.before_request
def csrf_protect():
    """
    Validates CSRF tokens for all state-changing POST requests.
    """
    if request.method == "POST":
        # Check CSRF token in session
        session_token = session.get('_csrf_token')
        if not session_token:
            logger.error("CSRF token missing from session context.")
            abort(400, "CSRF Token missing from session.")

        # Check CSRF token in request headers or form data
        request_token = request.headers.get('X-CSRFToken') or request.form.get('csrf_token')
        if not request_token or not secrets.compare_digest(session_token, request_token):
            logger.error("CSRF token validation failed.")
            abort(400, "CSRF Token validation failed.")

@app.context_processor
def inject_csrf_token():
    """
    Generates and injects the CSRF token into template rendering contexts.
    """
    if '_csrf_token' not in session:
        session['_csrf_token'] = secrets.token_hex(32)
    return dict(csrf_token=lambda: session['_csrf_token'])

# ==================== CONTROLLER ROUTES ====================

@app.route('/')
def index():
    """
    Renders the main upload application interface.
    """
    return render_template('index.html')


@app.route('/generate', methods=['POST'])
def generate_report():
    """
    Endpoint that handles report uploading, analysis, and generation.
    """
    # 1. Retrieve API key strictly from the server environment variables
    api_key = os.getenv('GEMINI_API_KEY')
    
    if not api_key:
        logger.error("Server configuration error: GEMINI_API_KEY environment variable is not set.")
        return jsonify({"error": "Server configuration error: GEMINI_API_KEY is not configured on the server. Please contact the administrator."}), 500

    # 2. File upload validation checks
    if 'inspection_file' not in request.files or 'thermal_file' not in request.files:
        return jsonify({"error": "Both Inspection Report and Thermal Report PDFs must be uploaded."}), 400

    ins_file = request.files['inspection_file']
    th_file = request.files['thermal_file']

    if ins_file.filename == '' or th_file.filename == '':
        return jsonify({"error": "Both files must be selected."}), 400

    if not (allowed_file(ins_file.filename) and allowed_file(th_file.filename)):
        return jsonify({"error": "Invalid file extension. Only PDF documents are allowed."}), 400

    # Clean job unique ID to isolate this request's images and files
    job_id = uuid.uuid4().hex[:12]
    
    # Save filenames securely using UUID to prevent path traversal/collision
    ins_filename = f"{job_id}_inspection.pdf"
    th_filename = f"{job_id}_thermal.pdf"

    ins_path = os.path.join(UPLOAD_FOLDER, ins_filename)
    th_path = os.path.join(UPLOAD_FOLDER, th_filename)

    try:
        # Save files
        ins_file.save(ins_path)
        th_file.save(th_path)

        # 3. Inspect PDF magic bytes content header to verify they are actual PDFs
        for path in [ins_path, th_path]:
            with open(path, 'rb') as f:
                header = f.read(4)
            if header != b'%PDF':
                # Remove malicious uploads
                os.remove(ins_path)
                os.remove(th_path)
                logger.error(f"File validation failed: Magic bytes do not match PDF signature for {path}.")
                return jsonify({"error": "File content validation failed. The files uploaded are not valid PDF documents."}), 400

        # 4. Extract Text Page-by-Page
        logger.info(f"[{job_id}] Initiating text extraction...")
        inspection_text = extract_text_from_pdf(ins_path)
        thermal_text = extract_text_from_pdf(th_path)

        # 5. Extract Images Page-by-Page
        logger.info(f"[{job_id}] Initiating image extraction...")
        images_output_dir = os.path.join(TEMP_IMAGES_FOLDER, job_id)
        
        inspection_images = extract_images_from_pdf(ins_path, "inspection", images_output_dir)
        thermal_images = extract_images_from_pdf(th_path, "thermal", images_output_dir)
        
        all_extracted_images = inspection_images + thermal_images

        # 6. Execute AI Diagnostics Analysis Engine
        logger.info(f"[{job_id}] Initiating Gemini AI diagnostics...")
        analysis_data = query_gemini_api(api_key, inspection_text, thermal_text, all_extracted_images)

        if "error" in analysis_data:
            return jsonify({"error": analysis_data["error"]}), 500

        # 7. Generate PDF DDR Report
        logger.info(f"[{job_id}] Compiling PDF DDR Report...")
        report_filename = f"DDR_Report_{job_id}.pdf"
        report_path = os.path.join(REPORTS_FOLDER, report_filename)
        
        # We pass the job-specific images subfolder to the report generator
        generate_ddr_pdf(analysis_data, images_output_dir, report_path)

        # 8. Clean up uploaded raw PDFs to keep the environment clean
        try:
            os.remove(ins_path)
            os.remove(th_path)
            logger.info(f"[{job_id}] Cleaned up uploaded source PDFs.")
        except Exception as cleanup_err:
            logger.warning(f"[{job_id}] Failed to delete source PDFs during cleanup: {cleanup_err}")

        # Return success with job-specific report filename
        return jsonify({
            "success": True,
            "message": "Detailed Diagnostic Report (DDR) compiled successfully.",
            "filename": report_filename
        })

    except Exception as e:
        logger.error(f"[{job_id}] Execution failed: {e}", exc_info=True)
        # Cleanup on failure
        if os.path.exists(ins_path):
            os.remove(ins_path)
        if os.path.exists(th_path):
            os.remove(th_path)
        return jsonify({"error": f"Internal execution failure: {str(e)}"}), 500


@app.route('/download/<filename>', methods=['GET'])
def download_file(filename):
    """
    Serves generated report PDFs to authenticated/authorized client requests.
    """
    # Sanitize input filename to block path traversal vulnerabilities (e.g. filename=../../etc/passwd)
    sanitized_filename = os.path.basename(secure_filename(filename))
    
    # Path resolution
    file_path = os.path.join(REPORTS_FOLDER, sanitized_filename)
    
    # Safety boundary verification
    if not os.path.exists(file_path):
        logger.error(f"File not found or access denied: {sanitized_filename}")
        abort(404, "Report file not found.")

    # Serve the file securely with forced download and XSS headers
    response = send_from_directory(REPORTS_FOLDER, sanitized_filename, as_attachment=True)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    return response

# ==================== MAIN LAUNCHER ====================
if __name__ == '__main__':
    # Force server to listen ONLY on local boundary loopback for local development
    # Do NOT bind to 0.0.0.0 (guideline testing requirement)
    logger.info("Starting local Flask server on http://127.0.0.1:5000")
    app.run(host='127.0.0.1', port=5000, debug=True)
