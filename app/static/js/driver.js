// app/static/js/driver.js
document.addEventListener('DOMContentLoaded', () => {
    const userId = document.body.dataset.userId;
    const offlineBanner = document.getElementById('offline-banner');
    const availableJobsList = document.getElementById('available-jobs-list');
    const availableDeliveriesList = document.getElementById('available-deliveries-list');
    const myJobsList = document.getElementById('my-jobs-list');

    const createJobCard = (order, jobType = 'pickup', isAccepted = false) => {
        const card = document.createElement('div');
        card.className = 'job-card';
        card.id = `order-${order.id}`;
        
        let actionsHtml = '';
        let jobTypeHtml = '';
        let notesHtml = order.notes_for_driver ? `<p><strong>Notes:</strong> ${order.notes_for_driver}</p>` : '';

        if (isAccepted) {
            // This is a job in "My Jobs"
            switch (order.status) {
                case 'AssignedToDriver':
                    jobTypeHtml = `<p class="job-type pickup">Customer Pickup</p>`;
                    // --- THIS IS THE FIX: Add load count input field ---
                    actionsHtml = `
                        <div class="pickup-proof">
                            <label for="load-count-${order.id}">Number of Loads:</label>
                            <input type="number" id="load-count-${order.id}" placeholder="e.g., 2" required min="1" />
                            <label for="pin-${order.id}">Customer PIN:</label>
                            <input type="text" id="pin-${order.id}" placeholder="e.g., 1234" required />
                            <button class="btn btn-action" data-action="picked_up" data-order-id="${order.id}">Mark as Picked Up</button>
                        </div>`;
                    // --- END OF FIX ---
                    break;
                case 'PickedUp':
                     jobTypeHtml = `<p class="job-type pickup">En-route to Hub</p>`;
                    actionsHtml = `
                        <div class="hub-delivery-proof">
                            <label>Scan Hub Delivery QR Code:</label>
                            <input type="text" id="hub-qr-${order.id}" placeholder="Scan QR at hub entrance" required />
                            <button class="btn btn-action" data-action="delivered_to_hub" data-order-id="${order.id}">Deliver to Hub</button>
                        </div>`;
                    break;
                case 'OutForDelivery':
                    jobTypeHtml = `<p class="job-type delivery">Hub Pickup</p>`;
                    actionsHtml = `
                        <div class="hub-pickup-proof">
                            <label>Scan Hub Pickup QR Code:</label>
                            <input type="text" id="hub-qr-${order.id}" placeholder="Scan QR at hub dispatch" required />
                            <button class="btn btn-action" data-action="pickup_from_hub" data-order-id="${order.id}">Confirm Hub Pickup</button>
                        </div>`;
                    break;
                case 'OnRouteToCustomer':
                    jobTypeHtml = `<p class="job-type delivery">Customer Delivery</p>`;
                    actionsHtml = `
                        <div class="delivery-proof">
                            <label>Customer Confirmation Code:</label>
                            <input type="text" id="pin-${order.id}" placeholder="Enter code from customer" required />
                            <button class="btn btn-action" data-action="delivered" data-order-id="${order.id}">Mark as Delivered</button>
                        </div>`;
                    break;
                default:
                    actionsHtml = `<p><strong>Status: ${order.status}</strong></p><p>(In progress at hub)</p>`;
                    break;
            }
        } else {
            // This is an available job
            if (jobType === 'pickup') {
                jobTypeHtml = `<p class="job-type pickup">New Customer Pickup</p>`;
                actionsHtml = `<button class="btn btn-accept" data-action="accept" data-order-id="${order.id}">Accept Job</button>`;
            } else { // delivery
                jobTypeHtml = `<p class="job-type delivery">New Delivery from Hub</p>`;
                actionsHtml = `<button class="btn btn-accept" data-action="accept_delivery" data-order-id="${order.id}">Accept Delivery</button>`;
            }
        }

        card.innerHTML = `
            ${jobTypeHtml}
            <p><strong>Order #${order.id}</strong></p>
            <p>Address: ${order.customer_address}</p>
            ${notesHtml}
            ${actionsHtml}`;
        return card;
    };
    
    const handleActionClick = (e) => {
        const target = e.target;
        if (!target.matches('button[data-action]')) return;
        
        const action = target.dataset.action;
        const orderId = target.dataset.orderId;
        
        target.disabled = true;
        
        let endpoint = `/api/drivers/${userId}/${action}`;
        const formData = new FormData();
        formData.append('order_id', orderId);

        let useFormData = false;
        let useJson = false;
        let payload = {};

        if (action === 'accept' || action === 'accept_delivery') {
            useJson = true;
            payload = { order_id: parseInt(orderId) };
        } else {
            useFormData = true;
            if (action === 'picked_up') {
                // --- THIS IS THE FIX: Get and validate load count before sending ---
                const loadCountInput = document.getElementById(`load-count-${orderId}`);
                const pinInput = document.getElementById(`pin-${orderId}`);
                
                if (!loadCountInput || !loadCountInput.value || parseInt(loadCountInput.value) < 1) {
                    alert('Number of loads is required and must be at least 1.');
                    target.disabled = false; return;
                }
                if (!pinInput || !pinInput.value) {
                    alert('Customer PIN is required.');
                    target.disabled = false; return;
                }
                formData.append('load_count', loadCountInput.value);
                formData.append('pin', pinInput.value);
                // --- END OF FIX ---
            } else if (action === 'delivered_to_hub') {
                const qrInput = document.getElementById(`hub-qr-${orderId}`);
                if (!qrInput || !qrInput.value) {
                    alert('Hub Delivery QR Code is required.');
                    target.disabled = false; return;
                }
                formData.append('hub_qr_code', qrInput.value);
            } else if (action === 'pickup_from_hub') {
                const qrInput = document.getElementById(`hub-qr-${orderId}`);
                if (!qrInput || !qrInput.value) {
                    alert('Hub Pickup QR Code is required.');
                    target.disabled = false; return;
                }
                formData.append('hub_qr_code', qrInput.value);
            } else if (action === 'delivered') {
                const pinInput = document.getElementById(`pin-${orderId}`);
                if (!pinInput || !pinInput.value) {
                    alert('Customer confirmation code is required.');
                    target.disabled = false; return;
                }
                formData.append('pin', pinInput.value);
            }
        }

        const body = useFormData ? formData : JSON.stringify(payload);
        const headers = useJson ? { 'Content-Type': 'application/json' } : {};

        fetch(endpoint, {
            method: 'POST',
            headers: headers,
            body: body
        }).then(res => {
            if (!res.ok) {
                return res.json().then(err => { throw new Error(err.detail || `Action ${action} failed`) });
            }
            console.log(`Action ${action} for order ${orderId} successful.`);
        }).catch(err => {
            console.error(err);
            target.disabled = false;
            alert(`An error occurred: ${err.message}`);
        });
    };
    document.body.addEventListener('click', handleActionClick);

    const socket = io({ transports: ['websocket'] });

    socket.on('connect', () => {
        console.log('Socket connected');
        socket.emit('join', { room: `driver:${userId}` });
        socket.emit('join', { room: `hub:1` });
        fetchInitialJobs();
    });

    socket.on('order.updated', (order) => {
        console.log('Order updated event received, refreshing all job lists:', order);
        fetchInitialJobs();
    });

    const fetchInitialJobs = async () => {
        availableJobsList.innerHTML = '<p>Loading...</p>';
        availableDeliveriesList.innerHTML = '<p>Loading...</p>';
        myJobsList.innerHTML = '<p>Loading...</p>';
        try {
            const [pickupsRes, deliveriesRes, myJobsRes] = await Promise.all([
                fetch('/api/drivers/available_orders'),
                fetch('/api/drivers/available_deliveries'),
                fetch('/api/drivers/my_jobs')
            ]);

            if (!pickupsRes.ok || !deliveriesRes.ok || !myJobsRes.ok) {
                throw new Error('Failed to fetch initial job lists.');
            }

            const pickups = await pickupsRes.json();
            const deliveries = await deliveriesRes.json();
            const myJobs = await myJobsRes.json();

            availableJobsList.innerHTML = '';
            availableDeliveriesList.innerHTML = '';
            myJobsList.innerHTML = '';

            pickups.forEach(order => availableJobsList.appendChild(createJobCard(order, 'pickup', false)));
            deliveries.forEach(order => availableDeliveriesList.appendChild(createJobCard(order, 'delivery', false)));
            myJobs.forEach(order => myJobsList.appendChild(createJobCard(order, '', true)));

            if (pickups.length === 0) availableJobsList.innerHTML = '<p>No available pickups right now.</p>';
            if (deliveries.length === 0) availableDeliveriesList.innerHTML = '<p>No available deliveries right now.</p>';
            if (myJobs.length === 0) myJobsList.innerHTML = '<p>You have no active jobs.</p>';

        } catch (error) {
            console.error(error);
            availableJobsList.innerHTML = '<p style="color: red;">Could not load jobs.</p>';
            availableDeliveriesList.innerHTML = '<p style="color: red;">Could not load jobs.</p>';
            myJobsList.innerHTML = '<p style="color: red;">Could not load jobs.</p>';
        }
    };
    
    fetchInitialJobs();
});