// app/static/js/settings.js
document.addEventListener('DOMContentLoaded', () => {
    const saveBtn = document.getElementById('save-btn');
    const statusMessage = document.getElementById('status-message');
    const settingsForm = document.getElementById('settings-form');
    
    // Inventory Management Elements
    const inventoryTableBody = document.getElementById('inventory-table-body');
    const addInvBtn = document.getElementById('add-inv-btn');
    const newInvNameInput = document.getElementById('new-inv-name');
    const newInvSkuInput = document.getElementById('new-inv-sku');

    const showStatus = (message, type) => {
        statusMessage.textContent = message;
        statusMessage.className = type === 'success' ? 'status-success' : 'status-error';
        statusMessage.style.display = 'block';
        setTimeout(() => {
            statusMessage.style.display = 'none';
        }, 4000);
    };

    const loadSettings = async () => {
        try {
            const response = await fetch('/api/admin/settings');
            if (!response.ok) throw new Error('Failed to load settings.');
            const settings = await response.json();

            for (const [key, value] of Object.entries(settings)) {
                const input = settingsForm.elements[key];
                if (input) {
                    input.value = value;
                }
            }
        } catch (error) {
            showStatus(error.message, 'error');
        }
    };

    const loadInventoryItems = async () => {
        try {
            const response = await fetch('/api/admin/inventory/summary');
            if (!response.ok) throw new Error('Failed to load inventory items.');
            const items = await response.json();
            renderInventoryTable(items);
        } catch (error) {
            showStatus(error.message, 'error');
        }
    };

    const renderInventoryTable = (items) => {
        inventoryTableBody.innerHTML = '';
        items.forEach(item => {
            const row = document.createElement('tr');
            row.dataset.sku = item.sku;
            row.innerHTML = `
                <td><input type="text" class="inv-name" value="${item.name}"></td>
                <td><input type="text" class="inv-unit" value="${item.unit_of_measurement}"></td>
                <td><input type="number" class="inv-threshold" step="0.1" value="${item.low_stock_threshold}"></td>
            `;
            inventoryTableBody.appendChild(row);
        });
    };
    
    addInvBtn.addEventListener('click', () => {
        const name = newInvNameInput.value.trim();
        const sku = newInvSkuInput.value.trim().toUpperCase();
        if (!name || !sku) {
            alert('Both Name and SKU are required to add an inventory item.');
            return;
        }
        
        // Check for duplicate SKU
        if (inventoryTableBody.querySelector(`tr[data-sku="${sku}"]`)) {
            alert('This SKU is already in use.');
            return;
        }

        const items = [{ sku, name, unit: 'units', threshold: 0 }];
        renderInventoryTable(items);
        newInvNameInput.value = '';
        newInvSkuInput.value = '';
    });

    const saveSettings = async () => {
        saveBtn.disabled = true;
        saveBtn.textContent = 'Saving...';

        const formData = new FormData(settingsForm);
        const settingsPayload = Object.fromEntries(formData.entries());
        
        // Serialize inventory table data
        const inventoryItems = [];
        inventoryTableBody.querySelectorAll('tr').forEach(row => {
            inventoryItems.push({
                sku: row.dataset.sku,
                name: row.querySelector('.inv-name').value,
                unit: row.querySelector('.inv-unit').value,
                threshold: row.querySelector('.inv-threshold').value
            });
        });
        settingsPayload.inventory_items_json = JSON.stringify(inventoryItems);

        try {
            const response = await fetch('/api/admin/settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(settingsPayload)
            });

            if (!response.ok) {
                const err = await response.json();
                throw new Error(err.detail || 'Failed to save settings.');
            }

            showStatus('Settings saved successfully!', 'success');
        } catch (error) {
            showStatus(error.message, 'error');
        } finally {
            saveBtn.disabled = false;
            saveBtn.textContent = 'Save All Settings';
        }
    };

    saveBtn.addEventListener('click', saveSettings);

    loadSettings();
    loadInventoryItems();
});