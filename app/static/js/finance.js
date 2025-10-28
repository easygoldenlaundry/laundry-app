// app/static/js/finance.js
document.addEventListener('DOMContentLoaded', () => {
    let currentPeriod = 'month';

    const loadingState = document.getElementById('loading-state');
    const financeContent = document.getElementById('finance-content');
    const periodButtons = document.querySelectorAll('.period-selector button');
    
    // Electricity Tracker selectors
    const electricityUsageDisplay = document.getElementById('electricity-usage-display');
    const electricityProgressFill = document.getElementById('electricity-progress-fill');
    const electricityUsageInput = document.getElementById('electricity-usage-input');
    const saveElectricityBtn = document.getElementById('btn-save-electricity');
    
    // Modal selectors
    const modal = document.getElementById('withdrawal-modal');
    const openModalBtn = document.getElementById('btn-record-withdrawal');
    const closeModalBtn = modal.querySelector('.close-btn');
    const withdrawalForm = document.getElementById('withdrawal-form');
    const withdrawalTypeSelect = document.getElementById('withdrawal-type');
    
    const inventoryFields = document.getElementById('inventory-fields');
    const fixedCostFields = document.getElementById('fixed-cost-fields');
    const descriptionField = document.getElementById('description-field');
    const inventoryItemSelect = document.getElementById('inventory-item-sku');

    const formatCurrency = (amount) => `R ${amount.toFixed(2)}`;

    const fetchData = async () => {
        loadingState.style.display = 'block';
        financeContent.style.display = 'none';

        try {
            const [summaryRes, transactionsRes, inventoryRes] = await Promise.all([
                fetch(`/api/admin/finance/summary?period=${currentPeriod}`, { cache: 'no-cache', credentials: 'include' }),
                fetch(`/api/admin/finance/transactions?period=${currentPeriod}`, { cache: 'no-cache', credentials: 'include' }),
                fetch(`/api/admin/inventory/summary`, { cache: 'no-cache', credentials: 'include' })
            ]);

            if (!summaryRes.ok || !transactionsRes.ok || !inventoryRes.ok) {
                throw new Error('Failed to fetch financial data.');
            }

            const summary = await summaryRes.json();
            const transactions = await transactionsRes.json();
            const inventory = await inventoryRes.json();
            
            renderSummary(summary);
            renderUtilityTrackers(summary); // New function call
            renderTransactions(transactions);
            renderInventory(inventory);
            populateInventorySelect(inventory);

            loadingState.style.display = 'none';
            financeContent.style.display = 'block';

        } catch (error) {
            loadingState.innerHTML = `<p style="color: red;">Error: ${error.message}</p>`;
        }
    };

    const renderSummary = (data) => {
        document.getElementById('live-balance').textContent = formatCurrency(data.live_business_balance);
        document.getElementById('bd-revenue').textContent = formatCurrency(data.total_revenue);
        document.getElementById('bd-withdrawals').textContent = formatCurrency(data.total_withdrawals);
        document.getElementById('bd-bills').textContent = formatCurrency(data.set_aside_for_bills);
        document.getElementById('bd-buffer').textContent = formatCurrency(data.safety_buffer_target);
        
        const guidanceCard = document.getElementById('guidance-card');
        const guidanceMessage = document.getElementById('guidance-message');
        guidanceMessage.textContent = data.guidance_message;
        guidanceCard.className = 'guidance-card';
        if (data.guidance_message.startsWith('Healthy')) {
            guidanceCard.classList.add('healthy');
        } else if (data.guidance_message.startsWith('Caution')) {
            guidanceCard.classList.add('caution');
        } else if (data.guidance_message.startsWith('Warning')) {
            guidanceCard.classList.add('warning');
        }
    };

    const renderUtilityTrackers = (summary) => {
        const data = summary.electricity_tracker;
        if (!data) return;

        electricityUsageDisplay.textContent = `${data.used.toFixed(1)} / ${data.budget.toFixed(1)} kWh`;
        electricityUsageInput.value = data.used.toFixed(1);

        const percentage = data.budget > 0 ? (data.used / data.budget) * 100 : 0;
        electricityProgressFill.style.width = `${Math.min(100, percentage)}%`;
        electricityProgressFill.textContent = `${percentage.toFixed(0)}%`;

        electricityProgressFill.classList.remove('critical', 'low', 'progress-bar-fill');
        electricityProgressFill.classList.add('progress-bar-fill');

        // Warning logic: Is the REMAINING buffer less than the threshold for 15 loads?
        if (data.remaining < data.threshold) {
            electricityProgressFill.classList.add('critical');
        } else if (percentage > 85) { // General "getting high" warning
            electricityProgressFill.classList.add('low');
        }
    };
    
    const renderInventory = (inventoryItems) => {
        const list = document.getElementById('inventory-list');
        list.innerHTML = '';
        if (inventoryItems.length === 0) {
            list.innerHTML = '<p>No inventory items are being tracked.</p>';
            return;
        }
        inventoryItems.forEach(item => {
            const percentage = item.low_stock_threshold > 0 ? (item.current_stock_level / item.low_stock_threshold) * 50 : 100;
            const fillClass = item.current_stock_level < item.low_stock_threshold ? 'critical' :
                              item.current_stock_level < item.low_stock_threshold * 1.5 ? 'low' : '';

            const itemDiv = document.createElement('div');
            itemDiv.className = 'inventory-item';
            itemDiv.innerHTML = `
                <div class="inventory-item-header">
                    <span>${item.name}</span>
                    <span>${item.current_stock_level.toFixed(2)} ${item.unit_of_measurement}</span>
                </div>
                <div class="progress-bar">
                    <div class="progress-bar-fill ${fillClass}" style="width: ${Math.min(100, percentage)}%;">
                        ${Math.min(100, percentage).toFixed(0)}%
                    </div>
                </div>
            `;
            list.appendChild(itemDiv);
        });
    };

    const renderTransactions = (transactions) => {
        const tableBody = document.getElementById('transactions-table-body');
        tableBody.innerHTML = '';

        if (transactions.length === 0) {
            tableBody.innerHTML = '<tr><td colspan="4" style="text-align: center;">No transactions found.</td></tr>';
            return;
        }

        transactions.forEach(tx => {
            const tr = document.createElement('tr');
            const sign = tx.is_withdrawal ? '-' : '+';
            const amountClass = tx.is_withdrawal ? 'withdrawal' : 'revenue';
            tr.innerHTML = `
                <td>${new Date(tx.timestamp).toLocaleString()}</td>
                <td>${tx.description}</td>
                <td>${tx.type}</td>
                <td><strong class="${amountClass}">${sign}${formatCurrency(tx.amount)}</strong></td>
            `;
            tableBody.appendChild(tr);
        });
    };
    
    const populateInventorySelect = (inventoryItems) => {
        inventoryItemSelect.innerHTML = '<option value="">Select Item...</option>';
        inventoryItems.forEach(item => {
            const option = document.createElement('option');
            option.value = item.sku;
            option.textContent = `${item.name} (${item.unit_of_measurement})`;
            inventoryItemSelect.appendChild(option);
        });
    };

    // Event Listeners
    periodButtons.forEach(button => {
        button.addEventListener('click', () => {
            periodButtons.forEach(btn => btn.classList.remove('active'));
            button.classList.add('active');
            currentPeriod = button.dataset.period;
            fetchData();
        });
    });

    saveElectricityBtn.addEventListener('click', async () => {
        const newValue = electricityUsageInput.value;
        if (newValue === null || newValue.trim() === '' || isNaN(parseFloat(newValue))) {
            alert('Please enter a valid number for electricity usage.');
            return;
        }

        saveElectricityBtn.disabled = true;
        saveElectricityBtn.textContent = 'Saving...';

        try {
            const response = await fetch('/api/admin/settings/monthly_tracker_electricity_kwh', {
                credentials: 'include',
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ value: newValue })
            });
            if (!response.ok) {
                const err = await response.json();
                throw new Error(err.detail || 'Failed to update setting.');
            }
            await fetchData();
            alert('Electricity tracker updated successfully!');

        } catch (error) {
            alert(`Error: ${error.message}`);
        } finally {
            saveElectricityBtn.disabled = false;
            saveElectricityBtn.textContent = 'Save';
        }
    });

    // Modal Logic
    openModalBtn.onclick = () => { modal.style.display = 'block'; };
    closeModalBtn.onclick = () => { modal.style.display = 'none'; };
    window.onclick = (event) => { if (event.target == modal) modal.style.display = 'none'; };

    withdrawalTypeSelect.addEventListener('change', () => {
        document.querySelectorAll('.conditional-fields').forEach(el => el.style.display = 'none');
        const type = withdrawalTypeSelect.value;
        if (type === 'cost_reimbursement') {
            inventoryFields.style.display = 'block';
        } else if (type === 'fixed_cost') {
            fixedCostFields.style.display = 'block';
        } else if (type === 'profit_draw' || type === 'capital_expenditure') {
            descriptionField.style.display = 'block';
        }
    });
    
    withdrawalForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const feedbackDiv = document.getElementById('withdrawal-feedback');
        feedbackDiv.textContent = 'Processing...';

        const type = withdrawalTypeSelect.value;
        let description = '';
        if (type === 'fixed_cost') {
            description = document.getElementById('fixed-cost-type').value;
        } else {
            description = document.getElementById('withdrawal-description').value;
        }

        const payload = {
            amount: parseFloat(document.getElementById('withdrawal-amount').value),
            description: description,
            withdrawal_type: type,
            inventory_item_sku: document.getElementById('inventory-item-sku').value,
            quantity_purchased: parseFloat(document.getElementById('inventory-quantity').value) || null
        };

        try {
            const response = await fetch('/api/admin/finance/withdrawals', {
                credentials: 'include',
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const result = await response.json();
            if (!response.ok) throw new Error(result.detail || 'Failed to record withdrawal.');

            feedbackDiv.style.color = 'green';
            feedbackDiv.textContent = result.message;
            
            withdrawalForm.reset();
            document.querySelectorAll('.conditional-fields').forEach(el => el.style.display = 'none');
            setTimeout(() => {
                modal.style.display = 'none';
                feedbackDiv.textContent = '';
                fetchData();
            }, 2000);
        } catch (error) {
            feedbackDiv.style.color = 'red';
            feedbackDiv.textContent = `Error: ${error.message}`;
        }
    });

    fetchData(); // Initial load
});