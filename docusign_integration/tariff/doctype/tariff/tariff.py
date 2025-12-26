# Copyright (c) 2025, nithin and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


import frappe
from docusign_integration.tariff.api import push_tariff_to_cms

class Tariff(Document):

    def on_update(self):
        # Detect transition to Active
        if self.status == "Active" and not self.get("__pushed_to_cms"):
            push_tariff_to_cms(self)
