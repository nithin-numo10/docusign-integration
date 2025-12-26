console.log("=== ASSIGN TARIFF JS FILE LOADED ===");

frappe.ui.form.on('Assign Tariff', {
    setup(frm) {
        frm.chargepoints_loaded = false;

        // ✅ Show only Active tariffs

    },

    refresh(frm) {
        if (!frm.chargepoints_loaded) {
            load_chargepoints(frm);
        }
        hide_grid_buttons(frm);
        set_tariff_filter(frm);
    },
      
    onload: function(frm) {
        hide_grid_buttons(frm);
        set_tariff_filter(frm);
    },
    connectors_add: function(frm, cdt, cdn) {
        hide_grid_buttons(frm);
    },
    charge_point(frm) {
        console.log('Charge point changed:', frm.doc.charge_point);

        // clear dependent fields
        frm.set_value('charge_point_name', null);

        if (!frm.doc.charge_point) return;

        // set charge point name
        if (frm.chargepoint_list) {
            const selected = frm.chargepoint_list.find(
                cp => cp.name === frm.doc.charge_point
            );
            if (selected?.identifier) {
                frm.set_value('charge_point_name', selected.identifier);
            }
        }

        // 🔥 Fetch connectors
        fetch_connectors(frm);
    }
});


frappe.ui.form.on('Assign Tariff Connector', {
    tariff: function(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        
        if (row.tariff) {
            // Fetch cms_tariff_id from the selected Tariff
            frappe.db.get_value('Tariff', row.tariff, ['cms_tariff_id', 'status'], function(r) {
                if (r) {
                    // Check if tariff is active
                    if (r.status !== 'Active') {
                        frappe.model.set_value(cdt, cdn, 'tariff', '');
                        frappe.throw(__('Please select a tariff with Active status'));
                        return;
                    }
                    
                    // Store cms_tariff_id in the child table row
                    frappe.model.set_value(cdt, cdn, 'cms_tariff_id', r.cms_tariff_id);
                }
            });
            
            // Auto-close the row after selection (optional)
            let grid_row = frm.fields_dict.connectors.grid.grid_rows_by_docname[cdn];
            if (grid_row) {
                setTimeout(function() {
                    grid_row.toggle_view(false);
                }, 300);
            }
        }
    },
    form_render: function(frm, cdt, cdn) {
        hide_row_buttons();
        add_close_button(frm, cdt, cdn);
    },
    
    before_connectors_remove: function(frm, cdt, cdn) {
        // Prevent deletion
        frappe.throw(__('Cannot delete connector rows'));
        return false;
    }
});


function load_chargepoints(frm) {
    if (frm.loading_chargepoints) return;

    frm.loading_chargepoints = true;

    frappe.call({
        method: "docusign_integration.tariff.api.fetch_chargepoint_list",
        callback(r) {
            frm.loading_chargepoints = false;

            if (Array.isArray(r.message)) {
                frm.chargepoint_list = r.message;

                const options = r.message.map(cp => cp.name).join('\n');
                frm.set_df_property('charge_point', 'options', options);
                frm.refresh_field('charge_point');

                frm.chargepoints_loaded = true;
            }
        }
    });
}


function fetch_connectors(frm) {
    console.log('Fetching connectors for charge point:', frm.doc.charge_point);

    frappe.call({
        method: "docusign_integration.tariff.api.fetch_chargepoint_connectors",
        args: {
            cp_id: frm.doc.charge_point_name   // ✅ MUST be cp_id
        },
        callback(r) {
            console.log('Connectors:', r);
            frm.clear_table('connectors');
            if (!r.message || !r.message.length) {
                frappe.msgprint(__('No connectors found'));
                return;
            }
            r.message.forEach(conn => {
                console.log('connector:', conn.connector_number);
                let row = frm.add_child("connectors");
                row.connector_number = conn.connector_number;
            });
    
            frm.refresh_field("connectors");
        }
    });
    
}

function disable_connector_row_operations(frm) {
    if (frm.fields_dict.connectors) {
        // Hide add row buttons
        frm.fields_dict.connectors.grid.wrapper.find('.grid-add-row').hide();
        frm.fields_dict.connectors.grid.wrapper.find('.grid-remove-rows').hide();
        frm.fields_dict.connectors.grid.wrapper.find('.grid-add-multiple-rows').hide();
        
        // Hide row operation buttons for each row
        frm.fields_dict.connectors.grid.grid_rows.forEach(function(row) {
            row.wrapper.find('.grid-delete-row').hide();
            row.wrapper.find('.grid-duplicate-row').hide();
            row.wrapper.find('.grid-insert-row').hide();
            row.wrapper.find('.grid-insert-row-below').hide();
            row.wrapper.find('.grid-move-row').hide();
        });
        
        // Hide footer buttons
        frm.fields_dict.connectors.grid.wrapper.find('.grid-footer').hide();
    }
}

function hide_grid_buttons(frm) {
    if (!frm.fields_dict.connectors) return;
    
    let grid = frm.fields_dict.connectors.grid;
    
    // Use CSS to forcefully hide buttons
    let style = `
        <style>
            [data-fieldname="connectors"] .grid-add-row,
            [data-fieldname="connectors"] .grid-remove-rows,
            [data-fieldname="connectors"] .grid-add-multiple-rows,
            [data-fieldname="connectors"] .grid-footer,
            [data-fieldname="connectors"] .grid-delete-row,
            [data-fieldname="connectors"] .grid-duplicate-row,
            [data-fieldname="connectors"] .grid-insert-row,
            [data-fieldname="connectors"] .grid-insert-row-below,
            [data-fieldname="connectors"] .grid-move-row,
            [data-fieldname="connectors"] [data-action="insert_below"],
            [data-fieldname="connectors"] [data-action="insert_above"],
            [data-fieldname="connectors"] [data-action="duplicate"],
            [data-fieldname="connectors"] [data-action="move"],
            [data-fieldname="connectors"] .btn-open-row ~ .grid-delete-row {
                display: none !important;
            }
        </style>
    `;
    
    if (!$('#hide-connector-buttons-style').length) {
        $('head').append($(style).attr('id', 'hide-connector-buttons-style'));
    }
    
    // Also hide via JavaScript
    setTimeout(function() {
        grid.wrapper.find('.grid-add-row').hide();
        grid.wrapper.find('.grid-remove-rows').hide();
        grid.wrapper.find('.grid-add-multiple-rows').hide();
        grid.wrapper.find('.grid-footer').hide();
        
        grid.grid_rows.forEach(function(row) {
            row.wrapper.find('.grid-delete-row').hide();
            row.wrapper.find('.grid-duplicate-row').hide();
            row.wrapper.find('[data-action]').hide();
        });
    }, 100);
}

function hide_row_buttons() {
    setTimeout(function() {
        $('.grid-row-open').find('.grid-delete-row').hide();
        $('.grid-row-open').find('[data-action="insert_below"]').hide();
        $('.grid-row-open').find('[data-action="insert_above"]').hide();
        $('.grid-row-open').find('[data-action="duplicate"]').hide();
        $('.grid-row-open').find('[data-action="move"]').hide();
        $('.grid-row-open').find('.grid-footer-toolbar').hide();
    }, 50);
}

function set_tariff_filter(frm) {
    // Filter tariff dropdown to show only Active tariffs
    frm.set_query('tariff', 'connectors', function() {
        return {
            filters: {
                'status': 'Active'
            }
        };
    });
}
function add_close_button(frm, cdt, cdn) {
    let grid_row = frm.fields_dict.connectors.grid.grid_rows_by_docname[cdn];
    
    if (grid_row && grid_row.wrapper.find('.btn-close-row').length === 0) {
        // Add close button to the row toolbar
        let close_btn = $(`
            <button class="btn btn-xs btn-close-row" style="margin-left: 5px;">
                <svg class="icon icon-sm"><use href="#icon-close"></use></svg>
                Close
            </button>
        `);
        
        close_btn.on('click', function() {
            grid_row.toggle_view(false);
        });
        
        // Insert the button in the row's toolbar
        grid_row.wrapper.find('.grid-row-toolbar').prepend(close_btn);
    }
}