import json
import logging
import requests

logger = logging.getLogger(__name__)

def query_gemini_api(api_key: str, inspection_text: str, thermal_text: str, extracted_images: list, model: str = "gemini-2.5-flash") -> dict:
    """
    Sends combined document content and image metadata to the Gemini API REST endpoint 
    using a strict response schema to get a structured JSON DDR.
    
    Args:
        api_key (str): The Gemini API key.
        inspection_text (str): Extracted text from the inspection report.
        thermal_text (str): Extracted text from the thermal report.
        extracted_images (list): Metadata list of extracted images from both PDFs.
        model (str): Gemini model to use. Defaults to "gemini-2.5-flash".
        
    Returns:
        dict: The structured analysis response from Gemini.
    """
    if not api_key:
        logger.error("Gemini API key is missing.")
        return {"error": "API Key is required to perform AI analysis."}
        
    # Format the images metadata to present to the LLM
    images_prompt_section = ""
    if extracted_images:
        images_prompt_section = "Available Extracted Images from Reports:\n"
        for img in extracted_images:
            images_prompt_section += (
                f"- Filename: {img['filename']}\n"
                f"  Source Document: {img['doc_ref']}\n"
                f"  Source Page: {img['page']}\n"
                f"  Text Context on Page: {img['context']}\n\n"
            )
    else:
        images_prompt_section = "No images were extracted from the reports.\n"

    # Define the System Instruction / Prompt
    system_instruction = (
        "You are a professional building diagnostics and property inspection expert.\n"
        "Your task is to create a Detailed Diagnostic Report (DDR) by analyzing both the Inspection Report and the Thermal Report.\n\n"
        "Rules:\n"
        "1. Never invent facts. Use ONLY information found in the provided report texts.\n"
        "2. Merge duplicate observations across reports.\n"
        "3. Detect conflicts or contradictions between the Inspection Report and the Thermal Report (e.g. one report says water leakage observed, while the other says no moisture detected). For each conflict, explain it clearly and recommend further inspection.\n"
        "4. Explicitly mention missing or unclear information. If details are not present, write 'Not Available'.\n"
        "5. Use client-friendly language.\n"
        "6. Keep recommendations practical and actionable.\n"
        "7. Map each area observation to the single most relevant image filename from the list of extracted images. "
        "Match them based on matching descriptions, locations, page references, and context. "
        "If no image is relevant or if no images are available, set the relevant image filename to 'Image Not Available'."
    )

    # Combine data into user prompt
    user_prompt = (
        f"--- INSPECTION REPORT TEXT ---\n{inspection_text}\n\n"
        f"--- THERMAL REPORT TEXT ---\n{thermal_text}\n\n"
        f"--- IMAGES LIST ---\n{images_prompt_section}\n\n"
        "Please analyze this data and generate a Detailed Diagnostic Report matching the required JSON schema structure."
    )

    # Request URL
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    
    # JSON Schema definition for response content
    schema = {
        "type": "OBJECT",
        "properties": {
            "property_issue_summary": {
                "type": "STRING",
                "description": "A high-level summary of the overall property issues identified."
            },
            "area_wise_observations": {
                "type": "ARRAY",
                "description": "Detailed observations organized by property area.",
                "items": {
                    "type": "OBJECT",
                    "properties": {
                        "area": {"type": "STRING", "description": "Name of the area (e.g. Master Bedroom, Kitchen)."},
                        "observation": {"type": "STRING", "description": "Specific observation for this area."},
                        "supporting_evidence": {"type": "STRING", "description": "Evidence from the inspection report."},
                        "related_thermal_finding": {"type": "STRING", "description": "Related finding from the thermal report. Write 'Not Available' if none."},
                        "relevant_image_filename": {"type": "STRING", "description": "Filename of the relevant image from the image list, or 'Image Not Available'."}
                    },
                    "required": ["area", "observation", "supporting_evidence", "related_thermal_finding", "relevant_image_filename"]
                }
            },
            "probable_root_cause": {
                "type": "STRING",
                "description": "Probable root cause analysis based on the reports."
            },
            "severity_assessment": {
                "type": "OBJECT",
                "description": "Overall severity level and reasoning.",
                "properties": {
                    "level": {
                        "type": "STRING",
                        "enum": ["Low", "Medium", "High", "Critical"],
                        "description": "The determined severity level."
                    },
                    "reasoning": {"type": "STRING", "description": "Reasoning for the severity assessment."}
                },
                "required": ["level", "reasoning"]
            },
            "recommended_actions": {
                "type": "ARRAY",
                "description": "List of practical and actionable recommendations.",
                "items": {"type": "STRING"}
            },
            "additional_notes": {
                "type": "STRING",
                "description": "Any additional comments or notes."
            },
            "missing_or_unclear_information": {
                "type": "STRING",
                "description": "Information that was missing or unclear in the provided reports. If none, write 'Not Available'."
            },
            "conflicts_detected": {
                "type": "ARRAY",
                "description": "List of conflicts or contradictions found between the inspection and thermal reports.",
                "items": {
                    "type": "OBJECT",
                    "properties": {
                        "conflict_summary": {"type": "STRING", "description": "A short summary of the contradiction."},
                        "inspection_finding": {"type": "STRING", "description": "What the inspection report indicates."},
                        "thermal_finding": {"type": "STRING", "description": "What the thermal report indicates."},
                        "recommendation": {"type": "STRING", "description": "Recommended action to resolve the conflict (e.g. further moisture inspection)."}
                    },
                    "required": ["conflict_summary", "inspection_finding", "thermal_finding", "recommendation"]
                }
            }
        },
        "required": [
            "property_issue_summary",
            "area_wise_observations",
            "probable_root_cause",
            "severity_assessment",
            "recommended_actions",
            "additional_notes",
            "missing_or_unclear_information",
            "conflicts_detected"
        ]
    }

    # API Request Payload
    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": user_prompt
                    }
                ]
            }
        ],
        "systemInstruction": {
            "parts": [
                {
                    "text": system_instruction
                }
            ]
        },
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": schema,
            "temperature": 0.1  # Low temperature for factuality
        }
    }

    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": api_key
    }

    try:
        logger.info(f"Sending analysis request to Gemini REST API using model {model}...")
        response = requests.post(url, json=payload, headers=headers, timeout=90)
        
        if response.status_code != 200:
            logger.error(f"Gemini API returned error code {response.status_code}: {response.text}")
            return {"error": f"Gemini API Error (Status {response.status_code}): {response.text}"}
            
        result_json = response.json()
        
        # Extract text content from response structure
        try:
            candidates = result_json.get("candidates", [])
            if not candidates:
                return {"error": "No candidates returned from Gemini API."}
                
            candidate = candidates[0]
            parts = candidate.get("content", {}).get("parts", [])
            if not parts:
                return {"error": "No parts returned in candidate content."}
                
            response_text = parts[0].get("text", "").strip()
            
            # Parse the returned JSON text string
            logger.info("Successfully received response text from Gemini API. Parsing JSON...")
            data = json.loads(response_text)
            return data
            
        except (KeyError, IndexError, json.JSONDecodeError) as parse_err:
            logger.error(f"Failed to parse Gemini response payload: {parse_err}. Raw body: {result_json}")
            return {"error": f"Failed to parse AI response: {str(parse_err)}"}
            
    except Exception as e:
        logger.error(f"Request to Gemini API failed: {e}", exc_info=True)
        return {"error": f"Connection to Gemini API failed: {str(e)}"}
