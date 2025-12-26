frappe.ui.form.on('Assign Tariff Connector', {
    tariff: function(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        
        // Validate if selected tariff is active
        if (row.tariff) {
            frappe.db.get_value('Tariff', row.tariff, 'status', function(r) {
                if (r && r.status !== 'Active') {
                    frappe.model.set_value(cdt, cdn, 'tariff', '');
                    frappe.throw(__('Please select a tariff with Active status'));
                }
            });
        }
    },
    
    setup: function(frm) {
        // Set query filter for tariff field
        frm.set_query('tariff', 'connectors', function() {
            return {
                filters: {
                    'status': 'Active'
                }
            };
        });
    }
});