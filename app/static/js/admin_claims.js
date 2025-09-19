// app/static/js/admin_users.js
document.addEventListener('DOMContentLoaded', () => {
    const usersTableBody = document.getElementById('users-table-body');
    const statusMessage = document.getElementById('status-message');
    const STATIONS = [
        { id: 'hub_intake', name: 'Hub Intake' }, { id: 'imaging', name: 'Imaging' },
        { id: 'pretreat', name: 'Pretreat' }, { id: 'washing', name: 'Washing' },
        { id: 'drying', name: 'Drying' }, { id: 'folding', name: 'Folding' },
        { id: 'qa_station', name: 'QA' }
    ];

    const showStatus = (message, type) => {
        statusMessage.textContent = message;
        statusMessage.className = `status-${type}`;
        statusMessage.style.display = 'block';
        setTimeout(() => { statusMessage.style.display = 'none'; }, 4000);
    };

    const fetchAndRenderUsers = async () => {
        try {
            const response = await fetch('/api/admin/users');
            if (!response.ok) throw new Error('Failed to fetch users.');
            const users = await response.json();
            renderUsers(users);
        } catch (error) {
            usersTableBody.innerHTML = `<tr><td colspan="4" style="color:red; text-align:center;">Error: ${error.message}</td></tr>`;
        }
    };

    const renderUsers = (users) => {
        usersTableBody.innerHTML = '';
        if (users.length === 0) {
            usersTableBody.innerHTML = `<tr><td colspan="4" style="text-align:center;">No staff or driver accounts found.</td></tr>`;
            return;
        }

        users.forEach(user => {
            const tr = document.createElement('tr');
            tr.dataset.userId = user.id;

            const isChecked = user.is_active ? 'checked' : '';
            const userAllowedStations = (user.allowed_stations || "").split(',');

            let permissionsHtml = 'N/A for drivers';
            if (user.role === 'staff') {
                const checkboxesHtml = STATIONS.map(station => `
                    <label>
                        <input type="checkbox" class="permission-cb" value="${station.id}" ${userAllowedStations.includes(station.id) ? 'checked' : ''}>
                        ${station.name}
                    </label>
                `).join('');
                permissionsHtml = `
                    <div class="permissions-grid">${checkboxesHtml}</div>
                    <button class="btn-save" data-action="save-permissions">Save</button>
                `;
            }

            tr.innerHTML = `
                <td>
                    <strong>${user.display_name}</strong><br>
                    <small>${user.username} | ${user.email}</small>
                </td>
                <td>${user.role}</td>
                <td>
                    <label class="switch">
                        <input type="checkbox" class="activation-toggle" ${isChecked}>
                        <span class="slider round"></span>
                    </label>
                </td>
                <td class="permissions-cell">${permissionsHtml}</td>
            `;
            usersTableBody.appendChild(tr);
        });
    };

    const handleTableClick = async (event) => {
        const target = event.target;
        const userId = target.closest('tr')?.dataset.userId;
        if (!userId) return;

        // Handle Activation Toggle
        if (target.classList.contains('activation-toggle')) {
            target.disabled = true;
            try {
                await fetch(`/api/admin/users/${userId}/toggle_activation`, { method: 'POST' });
                showStatus('User activation updated!', 'success');
                fetchAndRenderUsers();
            } catch (error) {
                showStatus('Error updating activation.', 'error');
                target.checked = !target.checked;
                target.disabled = false;
            }
        }

        // Handle Permissions Save
        if (target.dataset.action === 'save-permissions') {
            const row = target.closest('tr');
            const checkboxes = row.querySelectorAll('.permission-cb:checked');
            const allowed_stations = Array.from(checkboxes).map(cb => cb.value);

            target.disabled = true;
            target.textContent = 'Saving...';

            try {
                const response = await fetch(`/api/admin/users/${userId}/permissions`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ allowed_stations })
                });
                if (!response.ok) throw new Error('Failed to save permissions.');
                showStatus('Permissions saved successfully!', 'success');
            } catch (error) {
                showStatus(`Error saving permissions: ${error.message}`, 'error');
            } finally {
                target.disabled = false;
                target.textContent = 'Save';
            }
        }
    };

    usersTableBody.addEventListener('click', handleTableClick);
    fetchAndRenderUsers();
});