// app/static/js/imaging.js
document.addEventListener('DOMContentLoaded', () => {
    const HUB_ID = 1;
    const USER_ID = 1; // Hardcoded operator ID

    // --- DOM Elements ---
    const videoElement = document.getElementById('video-feed');
    const canvasElement = document.getElementById('capture-canvas');
    const ordersDisplay = document.getElementById('current-order-display');
    const orderInfo = document.getElementById('order-info');
    const bagInfo = document.getElementById('bag-info');
    const itemInfo = document.getElementById('item-info');
    const thumbnailStrip = document.getElementById('thumbnail-strip');
    const stainBtn = document.getElementById('stain-btn');
    const finalizeBtn = document.getElementById('finalize-btn');
    const completionArea = document.getElementById('completion-area');
    const queueList = document.getElementById('queue-list');
    const queueSidebar = document.getElementById('queue-sidebar');
    const basketCountInput = document.getElementById('basket-count');

    // --- State Management ---
    let orderStates = new Map(); // Stores state for ALL orders in the queue
    let activeOrderId = null; // The ID of the order currently being worked on
    let stainFlagged = false;
    let stream = null;

    // --- Camera Control ---
    const startCamera = async () => {
        try {
            stream = await navigator.mediaDevices.getUserMedia({ 
                video: { facingMode: 'environment' } 
            });
            videoElement.srcObject = stream;
            videoElement.play();
        } catch (err) {
            console.error("Error accessing camera: ", err);
            ordersDisplay.innerHTML = '<h2 style="color:red;">Error: Camera access denied or unavailable.</h2>';
        }
    };

    // --- UI Rendering ---
    const renderQueueSidebar = () => {
        queueList.innerHTML = '';
        if (orderStates.size === 0) {
            queueList.innerHTML = '<p>Queue is empty.</p>';
            return;
        }
        for (const [orderId, state] of orderStates.entries()) {
            const itemDiv = document.createElement('div');
            itemDiv.className = 'queue-item';
            itemDiv.dataset.orderId = orderId;
            itemDiv.textContent = `Order #${orderId} - ${state.orderData.customer_name}`;
            if (orderId === activeOrderId) {
                itemDiv.classList.add('active');
            }
            queueList.appendChild(itemDiv);
        }
    };

    const renderActiveOrder = () => {
        if (!activeOrderId || !orderStates.has(activeOrderId)) {
            ordersDisplay.querySelector('h2').textContent = 'Awaiting Next Order...';
            orderInfo.textContent = 'Select an order from the queue or wait for one to arrive.';
            bagInfo.textContent = '';
            itemInfo.textContent = '';
            thumbnailStrip.innerHTML = '';
            completionArea.style.display = 'none';
            stainBtn.disabled = true;
            return;
        }

        const state = orderStates.get(activeOrderId);
        ordersDisplay.querySelector('h2').textContent = `Order #${state.orderData.id} - ${state.orderData.customer_name}`;
        orderInfo.textContent = `Tracking: ${state.orderData.tracking_token}`;
        bagInfo.textContent = `Bag Code: ${state.bagData.bag_code}`;
        itemInfo.textContent = `Ready to scan Item #${state.currentItemIndex}`;
        stainBtn.disabled = false;
        stainBtn.textContent = 'Flag Stain (S)';
        stainBtn.style.backgroundColor = '';
        stainBtn.style.color = '';


        thumbnailStrip.innerHTML = '';
        state.imagesCaptured.forEach(img => {
            renderThumbnail(img.blob, img.itemIndex, img.isStain);
        });

        completionArea.style.display = state.imagesCaptured.length > 0 ? 'block' : 'none';
    };

    const renderThumbnail = (imageBlob, itemIndex, isStain) => {
        const url = URL.createObjectURL(imageBlob);
        const itemDiv = document.createElement('div');
        itemDiv.className = 'thumbnail-item';
        itemDiv.innerHTML = `
            <span class="item-index">#${itemIndex}</span>
            <img src="${url}" alt="Item Scan ${itemIndex}">
            <span class="stain-flag" style="display: ${isStain ? 'block' : 'none'};">STAIN</span>
        `;
        thumbnailStrip.appendChild(itemDiv);
        thumbnailStrip.scrollLeft = thumbnailStrip.scrollWidth;
    };


    // --- Core Logic ---
    const setActiveOrder = (orderId) => {
        if (orderId === activeOrderId) return;
        activeOrderId = orderId;
        renderActiveOrder();
        renderQueueSidebar();
    };

    const fetchAndSyncQueue = async () => {
        try {
            const response = await fetch(`/api/queues/${HUB_ID}/imaging`);
            if (!response.ok) throw new Error("Failed to fetch queue.");
            
            const orders = await response.json();
            const currentOrderIds = new Set(orders.map(o => o.id));

            for (const orderId of orderStates.keys()) {
                if (!currentOrderIds.has(orderId)) {
                    orderStates.delete(orderId);
                }
            }

            for (const order of orders) {
                if (!orderStates.has(order.id)) {
                    const bagResponse = await fetch(`/api/orders/${order.id}/bag`);
                    const bagData = await bagResponse.json();
                    orderStates.set(order.id, {
                        orderData: order,
                        bagData: bagData,
                        imagesCaptured: [],
                        currentItemIndex: 1
                    });
                }
            }
            
            if (!activeOrderId || !orderStates.has(activeOrderId)) {
                activeOrderId = orders.length > 0 ? orders[0].id : null;
            }

            renderQueueSidebar();
            renderActiveOrder();

        } catch (error) {
            console.error("Error syncing queue:", error);
        }
    };
    
    const captureImage = async () => {
        if (!activeOrderId || !stream) return;

        const state = orderStates.get(activeOrderId);
        const context = canvasElement.getContext('2d');
        canvasElement.width = videoElement.videoWidth;
        canvasElement.height = videoElement.videoHeight;
        context.drawImage(videoElement, 0, 0, videoElement.videoWidth, videoElement.videoHeight);

        canvasElement.toBlob(async (blob) => {
            const itemIndex = state.currentItemIndex;
            const isStain = stainFlagged;
            
            const formData = new FormData();
            formData.append('bag_id', state.bagData.id);
            formData.append('item_index', itemIndex);
            formData.append('user_id', USER_ID);
            formData.append('is_stain', isStain);
            formData.append('proof_photo', blob, `item_${itemIndex}.jpg`);
            
            try {
                const response = await fetch(`/api/orders/${activeOrderId}/upload-image`, { method: 'POST', body: formData });
                if (!response.ok) {
                    const errorResult = await response.json();
                    throw new Error(errorResult.detail || 'Failed to upload image to server.');
                }
                
                state.imagesCaptured.push({ itemIndex, isStain, blob });
                renderThumbnail(blob, itemIndex, isStain);
                state.currentItemIndex++;
                stainFlagged = false;
                renderActiveOrder();

            } catch(e) {
                console.error(e);
                alert(`Error: ${e.message}`);
            }
        }, 'image/jpeg', 0.8);
    };
    
    const completeImaging = async () => {
        if (!activeOrderId) return;
        const state = orderStates.get(activeOrderId);
        
        if (state.imagesCaptured.length === 0) {
            return alert('You must scan at least one item before finalizing.');
        }
        
        finalizeBtn.disabled = true;
        const basketCount = parseInt(basketCountInput.value, 10) || 1;

        try {
            const response = await fetch(`/api/orders/${activeOrderId}/complete-imaging`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    user_id: USER_ID,
                    basket_count: basketCount
                })
            });

             if (!response.ok) {
                const errorResult = await response.json();
                throw new Error(errorResult.detail || 'Failed to finalize imaging.');
            }
            // Success! Websocket will handle the UI update.
        } catch (error) {
            alert("An error occurred while finalizing: " + error.message);
        } finally {
            // This ensures the button is re-enabled even if the websocket update is slow
            // or if an error occurred.
            finalizeBtn.disabled = false;
        }
    };
    
    const flagStain = () => {
        stainFlagged = true;
        stainBtn.textContent = "Stain Flagged for Next Item!";
        stainBtn.style.backgroundColor = '#e74c3c';
        stainBtn.style.color = 'white';
    };

    // --- Event Listeners ---
    queueSidebar.addEventListener('click', (e) => {
        const queueItem = e.target.closest('.queue-item');
        if (queueItem) {
            setActiveOrder(parseInt(queueItem.dataset.orderId, 10));
        }
    });

    document.addEventListener('keydown', (e) => {
        if (!activeOrderId) return;
        if (document.activeElement.tagName === 'INPUT') return; // Ignore shortcuts if typing in an input
        if (e.key === ' ') { e.preventDefault(); captureImage(); } 
        else if (e.key.toUpperCase() === 'S') { e.preventDefault(); flagStain(); }
        else if (e.key.toUpperCase() === 'Q' && e.shiftKey) { e.preventDefault(); completeImaging(); }
    });

    stainBtn.addEventListener('click', flagStain);
    finalizeBtn.addEventListener('click', completeImaging);

    // --- Socket Setup ---
    function initializeSocket() {
        const socket = window.appSocket;
        if (!socket) {
            console.log('Socket not ready, retrying in 100ms...');
            setTimeout(initializeSocket, 100);
            return;
        }

        function onConnect() {
            document.getElementById('connection-status').textContent = 'Connected';
            socket.emit('join', { room: `station:${HUB_ID}:Imaging` });
            socket.emit('join', { room: `hub:${HUB_ID}` });
            fetchAndSyncQueue();
        }

        socket.on('connect', onConnect);
        socket.on('order.updated', () => {
            fetchAndSyncQueue();
        });
        
        if (socket.connected) {
            onConnect();
        }
    }
    
    initializeSocket();
    
    // --- Initialization ---
    startCamera();
});