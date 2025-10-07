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
            
            // Load real-time machine performance data
            await loadMachinePerformance();
        } catch (error) {
            showStatus(error.message, 'error');
        }
    };

    const loadMachinePerformance = async () => {
        try {
            const response = await fetch('/api/admin/machine-performance');
            if (!response.ok) throw new Error('Failed to load machine performance data.');
            const performance = await response.json();
            
            // Update real-time displays
            document.getElementById('current-wash-time').textContent = 
                performance.washing?.average_cycle_time || '--';
            document.getElementById('current-dry-time').textContent = 
                performance.drying?.average_cycle_time || '--';
            document.getElementById('current-fold-time').textContent = 
                performance.folding?.average_cycle_time || '--';
        } catch (error) {
            console.warn('Could not load machine performance data:', error);
        }
    };

    const loadInventoryItems = async () => {
        try {
            const response = await fetch('/api/admin/inventory/summary');
            if (!response.ok) throw new Error('Failed to load inventory items.');
            const items = await response.json();
            console.log('Loaded inventory items:', items);
            renderInventoryTable(items);
        } catch (error) {
            console.error('Error loading inventory items:', error);
            showStatus(error.message, 'error');
        }
    };

    const renderInventoryTable = (items) => {
        console.log('Rendering inventory table with items:', items);
        inventoryTableBody.innerHTML = '';
        items.forEach(item => {
            const row = document.createElement('tr');
            row.dataset.sku = item.sku;
            row.innerHTML = `
                <td><input type="text" class="inv-name" value="${item.name || ''}"></td>
                <td><input type="text" class="inv-unit" value="${item.unit_of_measurement || 'units'}"></td>
                <td><input type="number" class="inv-threshold" step="0.1" value="${item.low_stock_threshold || 0}"></td>
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

        // Add new row to existing table without clearing it
        const row = document.createElement('tr');
        row.dataset.sku = sku;
        row.innerHTML = `
            <td><input type="text" class="inv-name" value="${name}"></td>
            <td><input type="text" class="inv-unit" value="units"></td>
            <td><input type="number" class="inv-threshold" step="0.1" value="0"></td>
        `;
        inventoryTableBody.appendChild(row);
        
        // Clear input fields
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
            const sku = row.dataset.sku;
            const name = row.querySelector('.inv-name').value;
            const unit = row.querySelector('.inv-unit').value;
            const threshold = row.querySelector('.inv-threshold').value;
            
            if (sku && name) { // Only include items with valid SKU and name
                inventoryItems.push({
                    sku: sku,
                    name: name,
                    unit: unit,
                    threshold: threshold
                });
            }
        });
        
        console.log('Saving inventory items:', inventoryItems);
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

    // Auto-refresh machine performance data every 30 seconds
    setInterval(loadMachinePerformance, 30000);

    loadSettings();
    loadInventoryItems();
});