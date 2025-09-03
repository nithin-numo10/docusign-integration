# Standard Python imports
import base64
import json
import time
import requests
from datetime import datetime, timedelta
from jwt import encode, decode
from PyPDF2 import PdfReader, PdfWriter
from io import BytesIO

# Frappe framework imports
import frappe
from docusign_esign import ApiClient, EnvelopesApi, EnvelopeDefinition, TemplatesApi
from docusign_esign.client.api_exception import ApiException
from docusign_esign.models import (
    Document,
    Signer,
    Recipients,
    Tabs,
    SignHere,
    DateSigned,
    Text,
    CustomFields,
    TextCustomField,
    CompositeTemplate,
    ServerTemplate,
    InlineTemplate,
    TemplateRole
)

# Replace with your app's name
APP_NAME = "docusign_integration"

@frappe.whitelist()
def send_document_for_signature(doc=None, doctype=None, docname=None, template_id=None):
    """
    Sends a document from Frappe to DocuSign for signature using a template.
    This function handles calls from both the client-side
    (passing a 'doc' object) and server-side (passing 'doctype' and 'docname').

    Args:
        doc (frappe.document or str, optional): The Frappe document object or a JSON string. Defaults to None.
        doctype (str, optional): The DocType name. Used if 'doc' is not provided.
        docname (str, optional): The document name. Used if 'doc' is not provided.
        template_id (str, optional): The DocuSign template ID to be used.
    """
    # Log the start of the function and the received arguments
    frappe.log_error(f"Starting send_document_for_signature for {doctype} {docname} with template_id {template_id}", "DocuSign Debug")

    # Check if the doc argument is a string and parse it as JSON
    if isinstance(doc, str):
        doc = frappe.parse_json(doc)

    # If doc is not a Frappe document object, retrieve it from the database
    if isinstance(doc, dict):
        if not doc.get('doctype') or not doc.get('name'):
            frappe.throw("A valid document object or a valid doctype and docname must be provided.")
        doc = frappe.get_doc(doc.get('doctype'), doc.get('name'))

    

    if not doc.customer_email:
        frappe.throw("Recipient Email is required.")

    try:
        # 1. Get the JWT access token and API base path
        access_token, api_client_base_path, template_id = get_jwt_access_token()
        frappe.log_error("Successfully retrieved JWT access token.", "DocuSign Debug")
        if not template_id:
            frappe.throw("DocuSign Template ID is not set in DocuSign Settings.")
        # 2. Get user info and account ID
        user_info = get_user_info(access_token)
        account_id = user_info['accounts'][0]['account_id']


        api_client = ApiClient(api_client_base_path)
        api_client.set_default_header("Authorization", "Bearer " + access_token)
        templates_api = TemplatesApi(api_client)

        envelopes_api = EnvelopesApi(api_client)
        # 3. Create the envelope definition
        envelope_definition = get_merged_contract_for_signature(doc, template_id, account_id, templates_api, access_token, api_client_base_path)

        # 4. Add custom fields to identify the Frappe document in webhooks
        # The webhook events will be configured directly in DocuSign Connect
        
        # Create custom fields using the proper DocuSign SDK classes
        text_custom_fields = [
            TextCustomField(
                name="frappe_doctype",
                value=doc.doctype,
                required="false",
                show="false"
            ),
            TextCustomField(
                name="frappe_docname", 
                value=doc.name,
                required="false",
                show="false"
            )
        ]
        
        custom_fields = CustomFields(text_custom_fields=text_custom_fields)
        envelope_definition.custom_fields = custom_fields
        
        frappe.log_error("Successfully added custom fields to envelope definition.", "DocuSign Debug")

        # 5. Send the envelope
      

        frappe.log_error("Attempting to create and send the envelope.", "DocuSign Debug")
        results = envelopes_api.create_envelope(account_id, envelope_definition=envelope_definition)
        envelope_id = results.envelope_id

        # 6. Update the Frappe DocType
        doc.docusign_envelope_id = envelope_id
        doc.docusign_status = "Sent"
        doc.save()
        frappe.db.commit()

        frappe.msgprint("Document sent to DocuSign successfully!")
        frappe.log_error(f"Document sent successfully with Envelope ID: {envelope_id}. DocType updated.", "DocuSign Debug")
        return envelope_id

    except ApiException as ex:
        frappe.log_error(f"DocuSign API Error: {ex}", "DocuSign Integration")
        frappe.throw(f"DocuSign API Error: {ex.body}")
    except Exception as ex:
        frappe.log_error(f"General Error: {ex}", "DocuSign Integration")
        frappe.throw(f"An error occurred: {ex}")


# @frappe.whitelist(allow_guest=True)
# def handle_webhook():
#     """
#     Handles incoming webhook notifications from DocuSign.
#     """
#     frappe.log_error("DocuSign Webhook received.", "DocuSign Webhook")
#     try:
#         data = frappe.form_dict
#         frappe.log_error(f"Webhook Payload: {data}", "DocuSign Webhook")

#         envelope_id = data.get("envelopeId")
#         new_status = data.get("status")

#         # Get custom fields from the webhook payload
#         # Custom fields come in different structures depending on the webhook format
#         frappe_doctype = None
#         frappe_docname = None
        
#         # Try different possible structures for custom fields
#         if "customFields" in data:
#             custom_fields = data.get("customFields", {})
#             if "textCustomFields" in custom_fields:
#                 for field in custom_fields["textCustomFields"]:
#                     if field.get("name") == "frappe_doctype":
#                         frappe_doctype = field.get("value")
#                     elif field.get("name") == "frappe_docname":
#                         frappe_docname = field.get("value")
        
#         # Alternative: Direct field access (some webhook formats)
#         if not frappe_doctype:
#             frappe_doctype = data.get("frappe_doctype")
#         if not frappe_docname:
#             frappe_docname = data.get("frappe_docname")

#         frappe.log_error(f"Extracted: doctype={frappe_doctype}, docname={frappe_docname}, status={new_status}", "DocuSign Webhook")

#         if envelope_id and new_status and frappe_doctype and frappe_docname:
#             # Find the Frappe document using the dynamic DocType and name
#             frappe_doc = frappe.get_doc(frappe_doctype, frappe_docname)

#             if frappe_doc:
#                 frappe_doc.docusign_status = new_status
#                 frappe_doc.save()
#                 frappe.db.commit()
#                 frappe.log_error(f"Updated document {frappe_docname} ({frappe_doctype}) status to: {new_status}", "DocuSign Webhook")
#             else:
#                 frappe.log_error(f"No Frappe document found for envelope ID: {envelope_id}", "DocuSign Webhook")
#         else:
#             frappe.log_error("Missing required data in webhook payload.", "DocuSign Webhook")
#             frappe.log_error(f"envelope_id: {envelope_id}, status: {new_status}, doctype: {frappe_doctype}, docname: {frappe_docname}", "DocuSign Webhook")

#         frappe.response['http_status_code'] = 200
#         return "OK"

#     except Exception as e:
#         frappe.log_error(f"Error handling DocuSign webhook: {e}", "DocuSign Webhook")
#         frappe.response['http_status_code'] = 500
#         return "Error"

@frappe.whitelist(allow_guest=True)
def handle_webhook():
    """
    Handles incoming webhook notifications from DocuSign.
    """
    frappe.log_error("DocuSign Webhook received.", "DocuSign Webhook")
    
    try:
        # Get the raw request data
        data = None
        
        # Try to get JSON data from request body first
        if frappe.request and hasattr(frappe.request, 'data'):
            try:
                raw_data = frappe.request.data
                if isinstance(raw_data, bytes):
                    raw_data = raw_data.decode('utf-8')
                data = json.loads(raw_data) if raw_data else frappe.form_dict
            except (json.JSONDecodeError, AttributeError):
                data = frappe.form_dict
        else:
            data = frappe.form_dict

        frappe.log_error(f"Webhook Payload: {json.dumps(data, indent=2)}", "DocuSign Webhook")

        # Extract envelope information
        envelope_id = data.get("envelopeId") or data.get("data", {}).get("envelopeId")
        new_status = data.get("status") or data.get("data", {}).get("envelopeSummary", {}).get("status")
        
        # Initialize variables
        frappe_doctype = None
        frappe_docname = None
        
        # Method 1: Try to extract from customFields in the webhook data
        if "data" in data and "customFields" in data["data"]:
            custom_fields = data["data"]["customFields"]
            
            # Handle textCustomFields array
            if "textCustomFields" in custom_fields:
                for field in custom_fields["textCustomFields"]:
                    if field.get("name") == "frappe_doctype":
                        frappe_doctype = field.get("value")
                    elif field.get("name") == "frappe_docname":
                        frappe_docname = field.get("value")
        
        # Method 2: Try direct customFields access
        elif "customFields" in data:
            custom_fields = data.get("customFields", {})
            if "textCustomFields" in custom_fields:
                for field in custom_fields["textCustomFields"]:
                    if field.get("name") == "frappe_doctype":
                        frappe_doctype = field.get("value")
                    elif field.get("name") == "frappe_docname":
                        frappe_docname = field.get("value")
        
        # Method 3: Direct field access (fallback)
        if not frappe_doctype:
            frappe_doctype = data.get("frappe_doctype")
        if not frappe_docname:
            frappe_docname = data.get("frappe_docname")
            
        # Method 4: Try to extract from envelope custom fields if available
        if not frappe_doctype or not frappe_docname:
            envelope_data = data.get("data", {}).get("envelopeSummary", {})
            custom_fields = envelope_data.get("customFields", {})
            if "textCustomFields" in custom_fields:
                for field in custom_fields["textCustomFields"]:
                    if field.get("name") == "frappe_doctype" and not frappe_doctype:
                        frappe_doctype = field.get("value")
                    elif field.get("name") == "frappe_docname" and not frappe_docname:
                        frappe_docname = field.get("value")

        frappe.log_error(f"Extracted: doctype={frappe_doctype}, docname={frappe_docname}, status={new_status}, envelope_id={envelope_id}", "DocuSign Webhook")

        # Validate required data
        if not envelope_id:
            frappe.log_error("Missing envelope ID in webhook payload.", "DocuSign Webhook Error")
            frappe.response['http_status_code'] = 400
            return {"status": "error", "message": "Missing envelope ID"}

        if not new_status:
            frappe.log_error("Missing status in webhook payload.", "DocuSign Webhook Error")
            frappe.response['http_status_code'] = 400
            return {"status": "error", "message": "Missing status"}

        if not frappe_doctype or not frappe_docname:
            frappe.log_error(f"Missing Frappe document reference. DocType: {frappe_doctype}, DocName: {frappe_docname}", "DocuSign Webhook Error")
            frappe.response['http_status_code'] = 400
            return {"status": "error", "message": "Missing Frappe document reference"}

        # Validate DocType exists
        if not frappe.db.exists("DocType", frappe_doctype):
            frappe.log_error(f"Invalid DocType: {frappe_doctype}", "DocuSign Webhook Error")
            frappe.response['http_status_code'] = 400
            return {"status": "error", "message": f"Invalid DocType: {frappe_doctype}"}

        # Check if document exists
        if not frappe.db.exists(frappe_doctype, frappe_docname):
            frappe.log_error(f"Document not found: {frappe_doctype} - {frappe_docname}", "DocuSign Webhook Error")
            frappe.response['http_status_code'] = 404
            return {"status": "error", "message": f"Document not found: {frappe_doctype} - {frappe_docname}"}

        # Get and update the Frappe document
        frappe_doc = frappe.get_doc(frappe_doctype, frappe_docname)
        
        # Store old status for comparison
        old_status = getattr(frappe_doc, 'docusign_status', None)
        
        # Update document fields
        frappe_doc.docusign_status = new_status
        frappe_doc.docusign_envelope_id = envelope_id
        
        # Add timestamp for when status was updated
        frappe_doc.docusign_last_updated = frappe.utils.now()
        
        # Handle specific status changes
        if new_status.lower() == 'completed':
            frappe_doc.signature_completed_on = frappe.utils.now()
            # You might want to trigger additional workflows here
            
        elif new_status.lower() == 'declined':
            frappe_doc.signature_declined_on = frappe.utils.now()
            
        elif new_status.lower() == 'voided':
            frappe_doc.signature_voided_on = frappe.utils.now()

        # Save the document
        frappe_doc.flags.ignore_permissions = True  # Allow system updates
        frappe_doc.save()
        
        # Commit the transaction
        frappe.db.commit()
        
        frappe.log_error(f"Successfully updated document {frappe_docname} ({frappe_doctype}) status from '{old_status}' to '{new_status}'", "DocuSign Webhook Success")
        
        frappe.response['http_status_code'] = 200
        return {"status": "success", "message": f"Document updated successfully. Status: {new_status}"}

    except frappe.DoesNotExistError:
        error_msg = f"Document not found: {frappe_doctype} - {frappe_docname}"
        frappe.log_error(error_msg, "DocuSign Webhook Error")
        frappe.response['http_status_code'] = 404
        return {"status": "error", "message": error_msg}
        
    except frappe.ValidationError as ve:
        error_msg = f"Validation error updating document: {str(ve)}"
        frappe.log_error(error_msg, "DocuSign Webhook Error")
        frappe.response['http_status_code'] = 400
        return {"status": "error", "message": error_msg}
        
    except Exception as e:
        error_msg = f"Unexpected error handling DocuSign webhook: {str(e)}"
        frappe.log_error(error_msg, "DocuSign Webhook Error")
        frappe.response['http_status_code'] = 500
        return {"status": "error", "message": "Internal server error"}

def get_jwt_access_token():
    """
    Retrieves a JWT access token for DocuSign authentication from the DocuSign Settings DocType.
    """
    docusign_settings = frappe.get_cached_doc('DocuSign Settings', 'DocuSign Settings')
    private_key = docusign_settings.private_key
    client_id = docusign_settings.client_id
    template_id = docusign_settings.docusign_template_id
    impersonated_user_guid = docusign_settings.impersonated_user_guid
    if not private_key or not client_id or not impersonated_user_guid:
        frappe.throw("DocuSign credentials not set in DocuSign Settings.")

    now = int(time.time())
    exp = now + 3600 # 1 hour expiry
    payload = {
        "iss": client_id,
        "sub": impersonated_user_guid,
        "aud": "account-d.docusign.com",
        "iat": now,
        "exp": exp,
        "scope": "signature impersonation"
    }
    jwt_token = encode(payload, private_key, algorithm="RS256")
    url = "https://account-d.docusign.com/oauth/token"
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    body = {
        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
        "assertion": jwt_token
    }
    response = requests.post(url, headers=headers, data=body)
    response.raise_for_status()
    data = response.json()

    access_token = data.get("access_token")

    return access_token, "https://demo.docusign.net/restapi", template_id


def get_user_info(access_token):
    """
    Retrieves the user's account information using the access token.
    """
    url = "https://account-d.docusign.com/oauth/userinfo"
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json()




def merge_pdfs(docusign_pdf_bytes, custom_pdf_bytes):
    """
    Merge DocuSign template PDF with your custom PDF
    """
    try:
        # Create PDF readers
        docusign_reader = PdfReader(BytesIO(docusign_pdf_bytes))
        custom_reader = PdfReader(BytesIO(custom_pdf_bytes))
        
        # Create PDF writer
        writer = PdfWriter()
        
        # Add pages from DocuSign template first
        for page in docusign_reader.pages:
            writer.add_page(page)
        
        # Add pages from custom PDF
        for page in custom_reader.pages:
            writer.add_page(page)
        
        # Write to bytes
        output_buffer = BytesIO()
        writer.write(output_buffer)
        
        merged_pdf_bytes = output_buffer.getvalue()
        output_buffer.close()
        
        return merged_pdf_bytes
        
    except Exception as e:
        frappe.log_error(f"Error merging PDFs: {str(e)}", "PDF Merge Error")
        return None



def get_pdf_base64(doc):
    # Your existing PDF generation logic
    html = frappe.get_print(doc.doctype, doc.name)
    pdf = frappe.utils.pdf.get_pdf(html)
    import base64
    return base64.b64encode(pdf).decode()

def get_docusign_template_pdf(template_id, account_id, templates_api, access_token, base_path):
    """
    Get PDF bytes directly from DocuSign template (much better approach!)
    """
    try:
        # Initialize DocuSign client
        api_client = ApiClient()
        api_client.host = "https://demo.docusign.net/restapi"  # or production
        api_client.set_default_header("Authorization", "Bearer YOUR_ACCESS_TOKEN")

        # Get template info and PDF bytes directly
        frappe.log_error(f"account ID: {account_id}", "DocuSign Debug")
    
        # Get template information
        template_info = templates_api.get(account_id, template_id)
        

        # Get the first document from template (usually there's only one)
        if template_info.documents and len(template_info.documents) > 0:
            document_id = template_info.documents[0].document_id

            # Get the template PDF bytes directly
            template_pdf_file = get_template_document(
                access_token,
                account_id, 
                template_id, 
                document_id,
                base_path
            )
            
            # Read the bytes
            template_pdf_bytes = template_pdf_file
            return template_pdf_bytes
        else:
            frappe.log_error("No documents found in template", "DocuSign Template")
            return None
            
    except Exception as e:
        frappe.log_error(f"Error getting DocuSign template PDF: {str(e)}", "DocuSign Template PDF")
        return None


def get_template_document(access_token, account_id, template_id, document_id, base_path):
    """
    Retrieves a single PDF document from a DocuSign template.
    
    Args:
        access_token (str): The bearer access token.
        account_id (str): The DocuSign account ID.
        template_id (str): The template ID.
        document_id (str): The ID of the document within the template.
    
    Returns:
        The content of the document as a bytes object.
    """
    
    
    url = f"{base_path}/v2.1/accounts/{account_id}/templates/{template_id}/documents/{document_id}"
    
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    print(f"Making API call to: {url}")
    
    try:
        response = requests.get(url, headers=headers)

        response.raise_for_status()  # This will raise an HTTPError if the status is 4xx or 5xx
        # The response content is the raw PDF file
        return response.content
        
    except requests.exceptions.HTTPError as err:
        print(f"HTTP Error: {err}")
        print(f"Response Body: {err.response.text}")
        return None
    except Exception as err:
        print(f"An error occurred: {err}")
        return None

@frappe.whitelist()
def get_merged_contract_for_signature(doc, template_id, account_id, templates_api, access_token, base_path):
    """
    Send merged PDF for signature (without using template, just as document)
    """
    
    # Get merged PDF
    merged_contract = get_merged_contract(doc, template_id, account_id, templates_api, access_token, base_path)
    

    # Access Base64 for DocuSign
    merged_pdf_base64 = merged_contract["base64"]

    # Get total number of pages (for last page)
    # Access raw bytes
    merged_pdf_bytes = merged_contract["bytes"]
    reader = PdfReader(BytesIO(merged_pdf_bytes))
    total_pages = len(reader.pages)

    # Create simple envelope with merged PDF
    envelope_definition = EnvelopeDefinition()
    envelope_definition.email_subject = f"Contract for {doc.name} - Please Sign"
    envelope_definition.status = "sent"
    
    # Add merged document
    document = Document()
    document.document_base64 = merged_pdf_base64
    document.name = f"Contract_{doc.name}.pdf"
    document.file_extension = "pdf"
    document.document_id = "1"
    
    envelope_definition.documents = [document]
    
    # Add recipient
    # signer = Signer()
    # signer.email = doc.customer_email
    # signer.name = doc.customer_name
    # signer.recipient_id = "1"

    sender_signer = Signer(
    email=doc.supplier_email,  # Or doc.owner_email
    name=doc.supplier_name,
    recipient_id="1",
    routing_order="1"
    )   
    frappe.log_error('sender_signer', sender_signer)
    sender_sign_here = SignHere(
    document_id="1",
    page_number=str(total_pages), # Different page or same page
    x_position="50",
    y_position="700"
    )

    sender_signer.tabs = Tabs(sign_here_tabs=[sender_sign_here])

    # Receiver
    receiver_signer = Signer(
    email=doc.customer_email,
    name=doc.customer_name,
    recipient_id="2",
    routing_order="2"
    )
    frappe.log_error('receiver_signer', receiver_signer)
    receiver_sign_here = SignHere(
    document_id="1",
    page_number=str(total_pages),
    x_position="500",
    y_position="700"
    )   

    receiver_signer.tabs = Tabs(sign_here_tabs=[receiver_sign_here])

    # Add both signers
    envelope_definition.recipients = Recipients(signers=[receiver_signer, sender_signer])

    # Add signature tabs (you'll need to position these)
    # sign_here = SignHere()
    # sign_here.document_id = "1"
    # sign_here.page_number = "1"  # Adjust as needed
    # sign_here.x_position = "400"  # Adjust position
    # sign_here.y_position = "700"  # Adjust position
    
    # tabs = Tabs()
    # tabs.sign_here_tabs = [sign_here]
    # signer.tabs = tabs
    
    # envelope_definition.recipients = Recipients(signers=[signer])
    
    return envelope_definition

# def get_merged_contract_base64(doc, template_id, account_id, templates_api,  access_token, base_path):
#     """Get merged PDF as base64 for DocuSign sending"""
    
#     merged_pdf = create_merged_contract_pdf(doc, template_id, account_id, templates_api,  access_token, base_path)
#     return base64.b64encode(merged_pdf).decode()

def get_merged_contract(doc, template_id, account_id, templates_api, access_token, base_path):
    """Get merged PDF as both bytes and base64 for DocuSign sending"""
    
    merged_pdf_bytes = create_merged_contract_pdf(doc, template_id, account_id, templates_api, access_token, base_path)
    
    return {
        "bytes": merged_pdf_bytes,
        "base64": base64.b64encode(merged_pdf_bytes).decode()
    }


def generate_custom_contract_pdf(doc):
    """Generate a PDF from the Doctype data"""
    
    # Get the Doctype data as a dictionary
    # data = doc.as_dict()
    pdf_bytes = frappe.get_print(doc.doctype, doc.name, 'Standard', as_pdf=True)
    # Generate a PDF from the data
    # pdf_bytes = frappe.utils.pdf.get_pdf(data)
    
    return pdf_bytes

def create_merged_contract_pdf(doc, template_id, account_id, templates_api, access_token, base_path):
    """
    Create merged PDF: DocuSign template + Custom contract with amount
    """
    
    # Get DocuSign template PDF directly (much simpler!)
    docusign_pdf = get_docusign_template_pdf(template_id, account_id, templates_api, access_token, base_path)
    
    if not docusign_pdf:
        frappe.throw("Failed to get DocuSign template PDF")
    
    # Generate custom contract PDF
    custom_pdf = generate_custom_contract_pdf(doc)
    
    # Merge PDFs
    merged_pdf = merge_pdfs(docusign_pdf, custom_pdf)
    
    if not merged_pdf:
        frappe.throw("Failed to merge PDFs")
    
    return merged_pdf

