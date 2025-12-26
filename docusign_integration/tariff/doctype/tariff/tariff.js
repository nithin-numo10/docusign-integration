frappe.ui.form.on('Tariff', {
    refresh(frm) {
        if (!frm.taxes_loaded) {
            load_taxes(frm);
        }
    },

    tax(frm) {
        if (!frm.doc.tax) {
            frm.set_value('tax_identifier', null);
            return;
        }

        const selected = frm.tax_list?.find(
            t => t.name === frm.doc.tax
        );

        if (selected) {
            frm.set_value('tax_identifier', selected.identifier);
        }
    }
});


function load_taxes(frm) {
    if (frm.loading_taxes) return;

    frm.loading_taxes = true;
    console.log("Loading taxes...");

    frappe.call({
        method: "docusign_integration.tariff.api.fetch_tax_list",
        callback(r) {
            frm.loading_taxes = false;
            console.log("Taxes loaded", r.message); 
            if (r.message && Array.isArray(r.message)) {
                frm.tax_list = r.message;
                frm.set_df_property(
                    'tax',
                    'options',
                    r.message.map(t => t.name).join('\n')
                );

                frm.refresh_field('tax');
                frm.taxes_loaded = true;
            }
        },
        error(err) {
            frm.loading_taxes = false;
            frm.taxes_loaded = false;
            console.error("Tax API failed", err);
        }
    });
}
