# Standard Python imports
import base64
import json
import time
import requests
from datetime import datetime, timedelta
from jwt import encode, decode

# Frappe framework imports
import frappe
from docusign_esign import ApiClient, EnvelopesApi, EnvelopeDefinition
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
    TextCustomField
)

# Replace with your app's name
APP_NAME = "docusign_integration"

@frappe.whitelist()
def send_document_for_signature(doc=None, doctype=None, docname=None):
    """
    Sends a document from Frappe to DocuSign for signature.
    This function handles calls from both the client-side
    (passing a 'doc' object) and server-side (passing 'doctype' and 'docname').

    Args:
        doc (frappe.document or str, optional): The Frappe document object or a JSON string. Defaults to None.
        doctype (str, optional): The DocType name. Used if 'doc' is not provided.
        docname (str, optional): The document name. Used if 'doc' is not provided.
    """
    # Log the start of the function and the received arguments
    frappe.log_error(f"Starting send_document_for_signature for {doctype} {docname}", "DocuSign Debug")

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
        access_token, api_client_base_path = get_jwt_access_token()
        frappe.log_error("Successfully retrieved JWT access token.", "DocuSign Debug")

        # 2. Get user info and account ID
        frappe.log_error("access_token: ", access_token)
        user_info = get_user_info(access_token)
        frappe.log_error("user_info: ", user_info)
        account_id = user_info['accounts'][0]['account_id']
        frappe.log_error(f"Successfully retrieved account ID: {account_id}", "DocuSign Debug")

        # 3. Create the envelope definition
        envelope_definition = create_envelope_definition(doc, api_client_base_path)

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
        api_client = ApiClient(api_client_base_path)
        api_client.set_default_header("Authorization", "Bearer " + access_token)
        envelopes_api = EnvelopesApi(api_client)

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


@frappe.whitelist(allow_guest=True)
def handle_webhook():
    """
    Handles incoming webhook notifications from DocuSign.
    """
    frappe.log_error("DocuSign Webhook received.", "DocuSign Webhook")
    try:
        data = frappe.form_dict
        frappe.log_error(f"Webhook Payload: {data}", "DocuSign Webhook")

        envelope_id = data.get("envelopeId")
        new_status = data.get("status")

        # Get custom fields from the webhook payload
        # Custom fields come in different structures depending on the webhook format
        frappe_doctype = None
        frappe_docname = None
        
        # Try different possible structures for custom fields
        if "customFields" in data:
            custom_fields = data.get("customFields", {})
            if "textCustomFields" in custom_fields:
                for field in custom_fields["textCustomFields"]:
                    if field.get("name") == "frappe_doctype":
                        frappe_doctype = field.get("value")
                    elif field.get("name") == "frappe_docname":
                        frappe_docname = field.get("value")
        
        # Alternative: Direct field access (some webhook formats)
        if not frappe_doctype:
            frappe_doctype = data.get("frappe_doctype")
        if not frappe_docname:
            frappe_docname = data.get("frappe_docname")

        frappe.log_error(f"Extracted: doctype={frappe_doctype}, docname={frappe_docname}, status={new_status}", "DocuSign Webhook")

        if envelope_id and new_status and frappe_doctype and frappe_docname:
            # Find the Frappe document using the dynamic DocType and name
            frappe_doc = frappe.get_doc(frappe_doctype, frappe_docname)

            if frappe_doc:
                frappe_doc.docusign_status = new_status
                frappe_doc.save()
                frappe.db.commit()
                frappe.log_error(f"Updated document {frappe_docname} ({frappe_doctype}) status to: {new_status}", "DocuSign Webhook")
            else:
                frappe.log_error(f"No Frappe document found for envelope ID: {envelope_id}", "DocuSign Webhook")
        else:
            frappe.log_error("Missing required data in webhook payload.", "DocuSign Webhook")
            frappe.log_error(f"envelope_id: {envelope_id}, status: {new_status}, doctype: {frappe_doctype}, docname: {frappe_docname}", "DocuSign Webhook")

        frappe.response['http_status_code'] = 200
        return "OK"

    except Exception as e:
        frappe.log_error(f"Error handling DocuSign webhook: {e}", "DocuSign Webhook")
        frappe.response['http_status_code'] = 500
        return "Error"


def get_jwt_access_token():
    """
    Retrieves a JWT access token for DocuSign authentication from the DocuSign Settings DocType.
    """
    docusign_settings = frappe.get_cached_doc('DocuSign Settings', 'DocuSign Settings')
    private_key = docusign_settings.private_key
    client_id = docusign_settings.client_id
    impersonated_user_guid = docusign_settings.impersonated_user_guid
    frappe.log_error(f"private_key:", private_key)
    frappe.log_error(f"docusign_settings", docusign_settings)
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
    frappe.log_error(f"access token input payload is ", payload)
    jwt_token = encode(payload, private_key, algorithm="RS256")
    frappe.log_error(f"access token jwt token ", jwt_token)
    url = "https://account-d.docusign.com/oauth/token"
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    body = {
        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
        "assertion": jwt_token
    }
    response = requests.post(url, headers=headers, data=body)
    response.raise_for_status()
    data = response.json()
    frappe.log_error(f"access token data", data)

    access_token = data.get("access_token")

    return access_token, "https://demo.docusign.net/restapi"


def get_user_info(access_token):
    """
    Retrieves the user's account information using the access token.
    """
    url = "https://account-d.docusign.com/oauth/userinfo"
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(url, headers=headers)
    frappe.log_error(f"Response from user info: {response.status_code}" , "DocuSign Debug")
    response.raise_for_status()
    return response.json()


def create_envelope_definition(doc, api_client_base_path):
    """
    Creates the DocuSign envelope by generating a PDF from the Frappe document.

    Args:
        doc (frappe.document): The Frappe document object to be converted to PDF.
    """
    content_bytes = frappe.get_print(doc.doctype, doc.name, 'Standard', as_pdf=True)
    base64_file_content = base64.b64encode(content_bytes).decode('utf-8')

    docusign_doc = Document(
        document_base64=base64_file_content,
        name=doc.name,
        file_extension="pdf",
        document_id="1"
    )

    sign_here_tab = SignHere(
        document_id="1",
        page_number="1",
        x_position="100",
        y_position="100"
    )

    date_tab = DateSigned(
        document_id="1",
        page_number="1",
        x_position="200",
        y_position="100"
    )

    signer = Signer(
        email=doc.customer_email,
        name=doc.customer_name,
        recipient_id="1",
        routing_order="1",
        tabs=Tabs(sign_here_tabs=[sign_here_tab], date_signed_tabs=[date_tab])
    )

    recipients = Recipients(signers=[signer])

    envelope_definition = EnvelopeDefinition(
        email_subject="Document for Signature: " + doc.name,
        documents=[docusign_doc],
        recipients=recipients,
        status="sent"
    )

    return envelope_definition