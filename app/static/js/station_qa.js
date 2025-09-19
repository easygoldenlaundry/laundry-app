// app/static/js/station_qa.js
document.addEventListener('DOMContentLoaded', () => {
    // --- Config & State ---
    const HUB_ID = 1;
    const USER_ID = 1; // Hardcoded operator ID
    const STATION_TYPE = 'QA';
    let activeOrderId = null;
    let orderDataCache = new Map();

    // --- DOM Elements ---
    const queueList = document.getElementById('queue-list');
    const activeOrderDisplay = document.getElementById('active-order-display');
    const activeOrderInfo = document.getElementById('active-order-info');
    const passBtn = document.getElementById('pass-btn');
    const failBtn = document.getElementById('fail-btn');
    const notesTextArea = document.getElementById('notes');
    const checkboxes = document.querySelectorAll('.qa-checklist input[type="checkbox"]');
    const stainedImagesList = document.getElementById('stained-images-list');

    // --- UI Rendering ---
    const renderQueue = (readyOrders, summaryItems) => {
        queueList.innerHTML = '';
        if (readyOrders.length === 0 && summaryItems.length === 0) {
            queueList.innerHTML = '<p>Queue is empty.</p>';
            return;
        }
        
        // Render fully ready orders first
        readyOrders.forEach(order => {
            orderDataCache.set(order.id, order);
            const itemDiv = document.createElement('div');
            itemDiv.className = 'queue-item';
            itemDiv.dataset.orderId = order.id;
            itemDiv.textContent = `Order #${order.id} - ${order.customer_name}`;
            if (order.id === activeOrderId) {
                itemDiv.classList.add('active');
            }
            queueList.appendChild(itemDiv);
        });
        
        // Render partially arrived orders
        summaryItems.forEach(item => {
            const order = item.order;
            const itemDiv = document.createElement('div');
            itemDiv.className = 'queue-item';
            itemDiv.style.backgroundColor = '#f0f0f0';
            itemDiv.style.cursor = 'not-allowed';
            itemDiv.style.color = '#888';
            itemDiv.dataset.orderId = order.id;
            itemDiv.textContent = `Order #${order.id} - Awaiting Baskets (${item.baskets_at_qa}/${item.total_baskets})`;
            queueList.appendChild(itemDiv);
        });
    };

    const renderActiveOrder = async () => {
        if (!activeOrderId || !orderDataCache.has(activeOrderId)) {
            activeOrderDisplay.style.display = 'none';
            passBtn.disabled = true;
            failBtn.disabled = true;
            return;
        }
        
        activeOrderDisplay.style.display = 'block';
        passBtn.disabled = false;
        failBtn.disabled = false;
        const order = orderDataCache.get(activeOrderId);
        activeOrderInfo.innerHTML = `
            <h3>Order #${order.id}</h3>
            <p><strong>Customer:</strong> ${order.customer_name}</p>
            <p><strong>Items:</strong> ${order.total_items} (${order.basket_count} baskets)</p>
        `;
        notesTextArea.value = '';
        checkboxes.forEach(cb => cb.checked = false);
        await fetchAndRenderStainedImages(activeOrderId);
    };

    const fetchAndRenderStainedImages = async (orderId) => {
        try {
            const response = await fetch(`/api/orders/${orderId}/stained-images`);
            if (!response.ok) throw new Error('Failed to fetch images.');
            const images = await response.json();
            
            stainedImagesList.innerHTML = '';
            if (images.length > 0) {
                images.forEach(image => {
                    stainedImagesList.appendChild(createStainedItemCard(image));
                });
            } else {
                stainedImagesList.innerHTML = '<p>No items were flagged for stains.</p>';
            }
        } catch (error) {
            stainedImagesList.innerHTML = '<p style="color:red;">Could not load images.</p>';
        }
    };

    const createStainedItemCard = (image) => {
        const card = document.createElement('div');
        card.className = 'stained-item-card';
        card.dataset.imageId = image.id;
        card.innerHTML = `
            <img src="/${image.path}" alt="Stained item">
            <select class="qa-status-select">
                <option value="pending" ${image.qa_status === 'pending' ? 'selected' : ''}>Pending</option>
                <option value="removed" ${image.qa_status === 'removed' ? 'selected' : ''}>Stain Removed</option>
                <option value="non_removable" ${image.qa_status === 'non_removable' ? 'selected' : ''}>Non-removable</option>
                <option value="retry" ${image.qa_status === 'retry' ? 'selected' : ''}>Retry Pretreat</option>
            </select>
        `;
        return card;
    };

    // --- Core Logic ---
    const fetchQueue = async () => {
        try {
            const [readyRes, summaryRes] = await Promise.all([
                fetch(`/api/queues/qa/ready?hub_id=${HUB_ID}`),
                fetch(`/api/queues/qa/summary?hub_id=${HUB_ID}`)
            ]);
            if (!readyRes.ok || !summaryRes.ok) throw new Error("Failed to fetch QA queues.");
            
            const readyOrders = await readyRes.json();
            const summaryItems = await summaryRes.json();
            renderQueue(readyOrders, summaryItems);

            const activeOrderStillInQueue = readyOrders.some(o => o.id === activeOrderId);
            if (!activeOrderStillInQueue) {
                setActiveOrder(readyOrders.length > 0 ? readyOrders[0].id : null);
            }

        } catch (error) {
            console.error("Error fetching queue:", error);
            queueList.innerHTML = '<p style="color: red;">Could not load queue.</p>';
        }
    };

    const setActiveOrder = (orderId) => {
        activeOrderId = orderId;
        const currentActive = document.querySelector('.queue-item.active');
        if (currentActive) currentActive.classList.remove('active');
        if (orderId) {
            const newActive = document.querySelector(`.queue-item[data-order-id='${orderId}']`);
            if (newActive) newActive.classList.add('active');
        }
        renderActiveOrder();
    };

    const handleQaDecision = async (passed) => {
        if (!activeOrderId) return;
        const notes = notesTextArea.value.trim();
        if (!passed && !notes) {
            alert('Notes are required when failing an order.');
            return;
        }
        passBtn.disabled = true;
        failBtn.disabled = true;
        try {
            await fetch(`/api/orders/${activeOrderId}/qa`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user_id: USER_ID, passed: passed, notes: notes })
            });
        } catch (error) {
            const err = await error.response.json();
            alert(`Error: ${err.detail || 'Failed to process QA decision.'}`);
            passBtn.disabled = false;
            failBtn.disabled = false;
        }
    };

    const handleStainStatusChange = async (event) => {
        const selectElement = event.target;
        const imageId = selectElement.closest('.stained-item-card').dataset.imageId;
        const newStatus = selectElement.value;
        try {
            await fetch(`/api/orders/images/${imageId}/qa-update`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ qa_status: newStatus })
            });
        } catch (error) {
            alert('Failed to update stain status.');
            fetchAndRenderStainedImages(activeOrderId);
        }
    };

    // --- Event Listeners ---
    queueList.addEventListener('click', (e) => {
        const queueItem = e.target.closest('.queue-item');
        if (queueItem && !queueItem.style.cursor) { // Only allow click on non-disabled items
            setActiveOrder(parseInt(queueItem.dataset.orderId, 10));
        }
    });
    passBtn.addEventListener('click', () => handleQaDecision(true));
    failBtn.addEventListener('click', () => handleQaDecision(false));
    stainedImagesList.addEventListener('change', handleStainStatusChange);

    // --- Socket Setup ---
    const socket = io({ transports: ['websocket'] });
    socket.on('connect', () => {
        socket.emit('join', { room: `hub:${HUB_ID}` });
        fetchQueue();
    });
    
    socket.on('order.updated', () => fetchQueue());
    fetchQueue();
});