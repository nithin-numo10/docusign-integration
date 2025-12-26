import frappe
from frappe.model.document import Document

class AssignTariff(Document):
    def on_update(self):
        # Log everything to see what's happening
        frappe.log_error(
            title="AssignTariff Debug - on_update called",
            message=f"""
            Document: {self.name}
            Current Status: {self.status}
            DB Status: {self.get_db_value('status')}
            Pushed to CMS: {self.pushed_to_cms}
            """
        )
        
        # Check the condition
        if (
            self.status == "Active"
            and not self.pushed_to_cms
        ):
            frappe.log_error(
                title="AssignTariff - Condition Matched",
                message=f"Triggering API for {self.name}"
            )
            try:
                from docusign_integration.tariff.api import assign_tariff_to_cms
                assign_tariff_to_cms(self.name)
                frappe.msgprint("Tariff assigned to CMS successfully", indicator="green")
            except Exception as e:
                frappe.log_error(f"Error in AssignTariff.on_update: {str(e)}")
                frappe.throw(f"Failed to assign tariff: {str(e)}")
        else:
            frappe.log_error(
                title="AssignTariff - Condition NOT Matched",
                message=f"""
                Status is Active: {self.status == 'Active'}
                Status changed: {self.get_db_value('status') != 'Active'}
                Not pushed: {not self.pushed_to_cms}
                """
            )