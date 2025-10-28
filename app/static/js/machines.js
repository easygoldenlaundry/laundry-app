// app/static/js/machines.js
document.addEventListener('DOMContentLoaded', () => {
    const stationsList = document.getElementById('stations-list');
    const statusMessage = document.getElementById('status-message');

    const fetchMachineCounts = async () => {
        try {
            const response = await fetch('/api/admin/machines', {
                credentials: 'include'
            });
            if (!response.ok) throw new Error('Failed to fetch machine data.');

            const stations = await response.json();
            renderStations(stations);
        } catch (error) {
            showStatus(error.message, 'error');
        }
    };

    const renderStations = (stations) => {
        stationsList.innerHTML = '';
        stations.forEach(station => {
            const card = document.createElement('div');
            card.className = 'station-card';
            card.innerHTML = `
                <div class="station-info">
                    <h3>${station.station_type} Station</h3>
                    <p>ID: ${station.station_id}</p>
                </div>
                <div class="controls" data-station-id="${station.station_id}">
                    <label for="count-${station.station_id}">Machines:</label>
                    <input type="number" id="count-${station.station_id}" value="${station.current_count}" min="0">
                    <button class="update-btn">Update</button>
                </div>
            `;
            stationsList.appendChild(card);
        });
    };

    const showStatus = (message, type) => {
        statusMessage.textContent = message;
        statusMessage.className = type === 'success' ? 'status-success' : 'status-error';
        statusMessage.style.display = 'block';
        setTimeout(() => {
            statusMessage.style.display = 'none';
        }, 4000);
    };

    const handleUpdate = async (event) => {
        const target = event.target;
        if (!target.classList.contains('update-btn')) return;

        target.disabled = true;
        target.textContent = 'Updating...';

        const controlsDiv = target.closest('.controls');
        const stationId = controlsDiv.dataset.stationId;
        const newCount = controlsDiv.querySelector('input').value;

        try {
            const response = await fetch('/api/admin/machines/update', {
                credentials: 'include'
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    station_id: parseInt(stationId),
                    new_count: parseInt(newCount)
                })
            });

            const result = await response.json();

            if (!response.ok) {
                throw new Error(result.detail || 'Failed to update.');
            }
            
            showStatus(result.message, 'success');
            fetchMachineCounts(); // Refresh the list

        } catch (error) {
            showStatus(error.message, 'error');
        } finally {
            target.disabled = false;
            target.textContent = 'Update';
        }
    };

    stationsList.addEventListener('click', handleUpdate);

    // Initial load
    fetchMachineCounts();
});