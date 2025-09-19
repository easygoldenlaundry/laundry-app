// app/static/js/hub_intake.js
document.addEventListener('DOMContentLoaded', () => {
    const ordersList = document.getElementById('orders-list');
    const videoContainer = document.getElementById('video-container');
    const videoElement = document.getElementById('scanner-video');
    const HUB_ID = 1;
    const USER_ID = 1; 
    let codeReader;

    /**
     * LOGIC FIX: This function now ONLY fetches orders in the 'DeliveredToHub' state.
     * It is the single source of truth for what should be displayed on this page.
     */
    const fetchIntakeOrders = async () => {
        try {
            const response = await fetch(`/api/queues/${HUB_ID}/deliveredtohub`);
            if (!response.ok) {
                throw new Error('Failed to fetch orders for intake.');
            }
            
            const orders = await response.json();

            ordersList.innerHTML = ''; // Clear the list before rendering.

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
        // Fetch the initial list when the page loads.
        fetchIntakeOrders();
    });

    /**
     * REAL-TIME FIX: This is the definitive real-time solution.
     * When any order is updated, we simply re-run the fetch function.
     * This is robust and guarantees the page always shows the correct, latest data.
     */
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
        card.innerHTML = `
            <div class="order-card-header">
                <strong>Order #${order.id}</strong>
                <span>${order.customer_name}</span>
            </div>
            <form class="intake-form" data-order-id="${order.id}">
                <div class="form-group">
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

        try {
            const response = await fetch('/api/bags/scan', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ order_id: parseInt(orderId), bag_code: bagCode, user_id: USER_ID })
            });
            const result = await response.json();
            
            if (response.ok) {
                // The WebSocket will automatically trigger a list refresh now, removing the card.
                feedbackDiv.textContent = `Success! Bag '${bagCode}' associated.`;
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

    const initScanner = async () => {
        codeReader = new ZXing.BrowserMultiFormatReader();
        try {
            const videoInputDevices = await codeReader.listVideoInputDevices();
            if (videoInputDevices.length > 0) {
                videoContainer.style.display = 'block';
                codeReader.decodeFromVideoDevice(videoInputDevices[0].deviceId, 'scanner-video', (result, err) => {
                    if (result) {
                        const firstInput = ordersList.querySelector('input[name="bag_code"]');
                        if (firstInput) { firstInput.value = result.text; firstInput.focus(); }
                    }
                    if (err && !(err instanceof ZXing.NotFoundException)) { console.error(err); }
                });
            } else { console.warn('No video input devices found.'); }
        } catch (error) { console.error('Error initializing scanner:', error); }
    };

    ordersList.addEventListener('submit', handleFormSubmit);
    initScanner();
});