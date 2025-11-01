// app/static/js/hub_intake.js
document.addEventListener('DOMContentLoaded', () => {
    const ordersList = document.getElementById('orders-list');
    const HUB_ID = 1;
    const USER_ID = 1;

    const fetchIntakeOrders = async () => {
        try {
            // This endpoint now returns the dispatch_method
            const response = await fetch(`/api/queues/${HUB_ID}/deliveredtohub`, { credentials: 'include' });
            if (!response.ok) {
                throw new Error('Failed to fetch orders for intake.');
            }
            
            const orders = await response.json();

            ordersList.innerHTML = '';

            if (orders.length === 0) {
                ordersList.innerHTML = '<p style="text-align:center; color: #888;">No orders currently awaiting intake.</p>';
            } else {
                 orders.forEach(order => {
                    ordersList.appendChild(createOrderCard(order));
                });
            }
        } catch (error) {
            console.error('Error fetching intake orders:', error);
            ordersList.innerHTML = '<p style="color: red; text-align:center;">Could not load orders.</p>';
        }
    };

    const socket = io({ transports: ['websocket'] });

    socket.on('connect', () => {
        console.log('Hub Intake socket connected!');
        socket.emit('join', { room: `hub:${HUB_ID}` });
        fetchIntakeOrders();
    });

    socket.on('order.updated', (order) => {
        console.log(`[WebSocket] Received update for Order #${order.id}. Refreshing intake list.`);
        fetchIntakeOrders();
    });
    
    socket.on('disconnect', () => {
        console.log('Hub Intake socket disconnected.');
    });

    const createOrderCard = (order) => {
        const card = document.createElement('div');
        card.className = 'order-card';
        card.id = `order-${order.id}`;
        
        const expectedBagCode = order.bags && order.bags.length > 0 ? order.bags[0].bag_code : 'N/A';

        let loadCountHtml = '';
        if (order.dispatch_method === 'uber') {
            loadCountHtml = `
                <div class="form-group" style="margin-top: 0.75em;">
                    <label for="load-count-${order.id}" style="flex-basis: 120px;"><strong>Loads:</strong></label>
                    <input type="number" name="load_count" id="load-count-${order.id}" min="1" required value="1" style="flex-grow: 0; width: 80px; text-align: center;">
                </div>
            `;
        }

        card.innerHTML = `
            <div class="order-card-header">
                <strong>Order #${order.id}</strong>
                <span>${order.customer_name}</span>
            </div>
            <p style="margin: 0.5em 0;">Expected Bag Code: <strong>${expectedBagCode}</strong></p>
            <form class="intake-form" data-order-id="${order.id}">
                ${loadCountHtml}
                <div class="form-group" style="margin-top: 0.5em;">
                    <input type="text" name="bag_code" placeholder="Scan or type Bag QR Code" required>
                    <button type="submit">Submit</button>
                </div>
            </form>
            <div class="scan-feedback"></div>
        `;
        return card;
    };

    const handleFormSubmit = async (event) => {
        event.preventDefault();
        const form = event.target;
        const orderId = form.dataset.orderId;
        const bagCode = form.querySelector('input[name="bag_code"]').value.trim();
        const feedbackDiv = form.nextElementSibling;
        if (!bagCode) return;

        const loadCountInput = form.querySelector('input[name="load_count"]');
        const loadCount = loadCountInput ? parseInt(loadCountInput.value, 10) : null;

        const payload = {
            order_id: parseInt(orderId),
            bag_code: bagCode,
            user_id: USER_ID
        };
        if (loadCount) {
            payload.load_count = loadCount;
        }

        try {
            const response = await fetch('/api/bags/scan', { credentials: 'include',
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload) // Send the new payload
            });
            const result = await response.json();
            
            if (response.ok) {
                feedbackDiv.textContent = `Success! Bag '${bagCode}' verified.`;
                feedbackDiv.className = 'scan-feedback scan-success';
                feedbackDiv.style.display = 'block';
            } else {
                feedbackDiv.textContent = `Error: ${result.detail}`;
                feedbackDiv.className = 'scan-feedback scan-error';
                feedbackDiv.style.display = 'block';
            }
        } catch (error) {
            console.error('Submission error:', error);
            feedbackDiv.textContent = 'A network error occurred. Please try again.';
            feedbackDiv.className = 'scan-feedback scan-error';
            feedbackDiv.style.display = 'block';
        }
    };

    ordersList.addEventListener('submit', handleFormSubmit);
});