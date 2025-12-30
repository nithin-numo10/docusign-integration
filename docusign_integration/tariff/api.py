# your_doctype.py
import frappe
import requests

@frappe.whitelist()
def fetch_chargepoint_list():
    try:
        docusign_settings = frappe.get_cached_doc(
            'DocuSign Settings',
            'DocuSign Settings'
        )

        base_url = docusign_settings.cms_base_url.rstrip("/")
        api_key = docusign_settings.cms_api_key

        url = f"{base_url}/frapeencmsasset/chargepoint/get/cpDisplayName"

        headers = {
            "x-api-key": api_key,
            "Accept": "application/json"
        }

        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()

    except requests.exceptions.RequestException as e:
        frappe.log_error(
            message=str(e),
            title="ChargePoint fetch failed"
        )
        return []

    # Expected structure:
    # data["Document"] = { "cp_name": "display_name", ... }

    document = data.get("Document", {})

    # Return list of dicts (ideal for dropdown mapping)
    return [
        {
            "name": display_name,   # what user sees
            "identifier": cp_name   # what gets stored
        }
        for cp_name, display_name in document.items()
    ]

@frappe.whitelist()
def fetch_tax_list():
    try:
        docusign_settings = frappe.get_cached_doc(
            'DocuSign Settings',
            'DocuSign Settings'
        )

        base_url = docusign_settings.cms_base_url.rstrip("/")
        api_key = docusign_settings.cms_api_key

        url = f"{base_url}/frapeetariff/api/fetch-tax?numotype=ocpp"

        headers = {
            "x-api-key": api_key,
            "Accept": "application/json"
        }

        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()

    except requests.exceptions.RequestException as e:
        frappe.log_error(
            message=str(e),
            title="Tax fetch failed"
        )
        return []

    # ✅ RETURN NORMALIZED DATA
    return [
        {
            "name": tax.get("name"),             # shown in dropdown
            "identifier": tax.get("identifier")  # stored value
        }
        for tax in data
        if tax.get("name") and tax.get("identifier")
    ]

def push_tariff_to_cms(tariff_doc):
    try:
        settings = frappe.get_cached_doc(
            "DocuSign Settings",
            "DocuSign Settings"
        )

        url = f"{settings.cms_base_url.rstrip('/')}/frapeetariff/api/tariff"

        payload = {
            "name": tariff_doc.tariff_name,
            "taxId": tariff_doc.tax_identifier,
            "currencyType": tariff_doc.currency,
            "numotype": "ocpp",
            "services": []
        }

        if tariff_doc.type == "Energy":
            payload["services"].append({
                "type": "energyInkWh",
                "rate": tariff_doc.value
            })

        if tariff_doc.service_fee:
            payload["services"].append({
                "type": "serviceFee",
                "rate": tariff_doc.service_fee
            })

        headers = {
            "x-api-key": settings.cms_api_key,
            "Content-Type": "application/json"
        }

        resp = requests.post(url, json=payload, headers=headers, timeout=15)
        resp.raise_for_status()
                # Extract the identifier from CMS response
        frappe.log_error(
            title="Tariff CMS push response",
            message=resp.json()
        )        
        cms_id = resp.json().get("identifier")

        if cms_id:
            tariff_doc.db_set("cms_tariff_id", cms_id)
            tariff_doc.db_set("pushed_to_cms", 1)


    except Exception as e:
        frappe.log_error(
            title="Tariff CMS Push Failed",
            message=frappe.get_traceback()
        )
        frappe.throw("Failed to push tariff to CMS. Check error logs.")




@frappe.whitelist()
def fetch_chargepoint_connectors(cp_id):
    try:
        settings = frappe.get_cached_doc(
            "DocuSign Settings",
            "DocuSign Settings"
        )

        base_url = settings.cms_base_url.rstrip("/")
        api_key = settings.cms_api_key

        url = f"{base_url}/frapeencmsasset/chargepoint/connectors"
        params = {"cpId": cp_id}

        headers = {
            "x-api-key": api_key,
            "Accept": "application/json"
        }

        resp = requests.get(
            url,
            headers=headers,
            params=params,
            timeout=15
        )
        resp.raise_for_status()
        data = resp.json()

    except Exception as e:
        frappe.log_error(
            title="Fetch ChargePoint Connectors Failed",
            message=str(e)
        )
        return []

    # ✅ SAFE extraction
    document = data.get("Document") or []

    # ✅ Return only what UI needs
    return [
        {
            "connector_number": d.get("ChargePointConnectorNumber")
        }
        for d in document
        if d.get("ChargePointConnectorNumber")
    ]




@frappe.whitelist()
def assign_tariff_to_cms(assign_tariff_name):
    """
    Assign tariff to charge points & connectors in CMS
    Triggered when Assign Tariff status becomes Active
    """

    frappe.log_error(
        title="Assign Tariff to CMS Called",
        message=f"Assign Tariff {assign_tariff_name} triggered"
    )

    try:
        # 🔹 Load CMS settings
        settings = frappe.get_cached_doc(
            "DocuSign Settings",
            "DocuSign Settings"
        )

        base_url = settings.cms_base_url.rstrip("/")
        api_key = settings.cms_api_key

        url = f"{base_url}/frapeetariff/api/tariffChargePointMapping"

        headers = {
            "x-api-key": api_key,
            "Accept": "application/json",
            "Content-Type": "application/json"
        }

        # 🔹 Load Assign Tariff document
        assign_tariff_doc = frappe.get_doc("Assign Tariff", assign_tariff_name)

        frappe.log_error(
            title="Assign Tariff Loaded",
            message=f"Charge Point: {assign_tariff_doc.charge_point_name}"
        )

        tariff_mappings = []

        # 🔹 Loop connector table (CORRECT)
        for connector in assign_tariff_doc.connectors:
            if not connector.cms_tariff_id:
                continue

            tariff_mappings.append({
                "tariffId": connector.cms_tariff_id,
                "chargePointId": assign_tariff_doc.charge_point_name,
                "connectorId": connector.connector_number
            })

        if not tariff_mappings:
            frappe.throw("No valid connector mappings found")

        payload = {
            "numotype": "ocpp",
            "tariff": tariff_mappings
        }

        resp = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=20
        )
        resp.raise_for_status()
        data = resp.json()

    except Exception:
        frappe.log_error(
            title="Assign Tariff to CMS Failed",
            message=frappe.get_traceback()
        )
        return {
            "success": False,
            "message": "Failed to assign tariff to CMS"
        }

    # ✅ Mark Assign Tariff as pushed
    assign_tariff_doc.db_set("pushed_to_cms", 1)

    return {
        "success": True,
        "message": "Tariff assigned to CMS successfully",
        "response": data
    }
