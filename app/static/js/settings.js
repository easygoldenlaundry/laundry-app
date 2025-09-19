// app/static/js/settings.js
document.addEventListener('DOMContentLoaded', () => {
    const saveBtn = document.getElementById('save-btn');
    const statusMessage = document.getElementById('status-message');
    const allInputs = document.querySelectorAll('.settings-card input');

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

            allInputs.forEach(input => {
                const key = input.dataset.key;
                if (settings[key] !== undefined) {
                    input.value = settings[key];
                }
            });
        } catch (error) {
            showStatus(error.message, 'error');
        }
    };

    const saveSettings = async () => {
        saveBtn.disabled = true;
        saveBtn.textContent = 'Saving...';

        const settingsPayload = {};
        allInputs.forEach(input => {
            const key = input.dataset.key;
            settingsPayload[key] = input.value;
        });

        try {
            const response = await fetch('/api/admin/settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ settings: settingsPayload })
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

    // Initial load
    loadSettings();
});