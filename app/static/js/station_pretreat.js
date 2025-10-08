// app/static/js/station_pretreat.js
document.addEventListener('DOMContentLoaded', () => {
    // --- Config & State ---
    const HUB_ID = 1;
    const USER_ID = 1;
    const STATION_TYPE = 'Pretreat';
    const SOAKING_TIME_SECONDS = 20 * 60; // 20 minutes
    let activeBasketId = null;
    let basketDataCache = new Map();
    let timerInterval = null;

    // --- DOM Elements ---
    const queueList = document.getElementById('queue-list');
    const activeOrderDisplay = document.getElementById('active-order-display');
    const activeOrderInfo = document.getElementById('active-order-info');
    const startBtn = document.getElementById('start-btn');
    const completeBtn = document.getElementById('complete-btn');
    const timerDisplay = document.getElementById('timer-display');
    const stainedItemsGrid = document.getElementById('stained-items-grid');

    // --- UI Rendering ---
    const renderQueue = (baskets) => {
        queueList.innerHTML = '';
        if (baskets.length === 0) {
            queueList.innerHTML = '<p>Queue is empty.</p>';
            return;
        }
        baskets.forEach(basket => {
            basketDataCache.set(basket.id, basket);
            const itemDiv = document.createElement('div');
            itemDiv.className = 'queue-item';
            itemDiv.dataset.basketId = basket.id;
            itemDiv.textContent = `Order #${basket.order.id}.${basket.basket_index} - ${basket.order.customer_name}`;
            if (basket.id === activeBasketId) {
                itemDiv.classList.add('active');
            }
            queueList.appendChild(itemDiv);
        });
    };
    
    const formatTime = (totalSeconds) => {
        const minutes = Math.floor(totalSeconds / 60).toString().padStart(2, '0');
        const seconds = (Math.floor(totalSeconds) % 60).toString().padStart(2, '0');
        return `${minutes}:${seconds}`;
    };

    const renderActiveOrder = async () => {
        clearInterval(timerInterval);
        
        if (!activeBasketId || !basketDataCache.has(activeBasketId)) {
            activeOrderDisplay.style.display = 'none';
            return;
        }
        
        activeOrderDisplay.style.display = 'block';
        const basket = basketDataCache.get(activeBasketId);
        
        activeOrderInfo.innerHTML = `
            <h3>Order #${basket.order.id}.${basket.basket_index}</h3>
            <p><strong>Customer:</strong> ${basket.order.customer_name}</p>
        `;
        
        // The "Mark as Complete" button is now always enabled when a basket is active.
        completeBtn.disabled = false;
        
        if (basket.soaking_started_at) {
            startBtn.disabled = true;
            startRobustTimer(basket);
        } else {
            startBtn.disabled = false;
            timerDisplay.textContent = formatTime(SOAKING_TIME_SECONDS);
        }

        await fetchAndRenderStainedImages(basket.order_id);
    };

    const fetchAndRenderStainedImages = async (orderId) => {
        try {
            const response = await fetch(`/api/orders/${orderId}/stained-images`);
            if (!response.ok) throw new Error('Failed to fetch images.');
            const images = await response.json();
            
            stainedItemsGrid.innerHTML = '';
            if (images.length > 0) {
                images.forEach(image => {
                    const imgElement = document.createElement('img');
                    imgElement.src = `/${image.path.replace(/\\/g, '/')}`;
                    stainedItemsGrid.appendChild(imgElement);
                });
            } else {
                stainedItemsGrid.innerHTML = '<p>No items were flagged with stains for this order.</p>';
            }
        } catch (error) {
            stainedItemsGrid.innerHTML = '<p style="color:red;">Could not load images.</p>';
        }
    };
    
    // --- Core Logic ---
    const fetchQueue = async () => {
        try {
            const response = await fetch(`/api/queues/${HUB_ID}/${STATION_TYPE.toLowerCase()}`);
            if (!response.ok) throw new Error("Failed to fetch queue.");
            
            const baskets = await response.json();
            renderQueue(baskets);

            const activeBasketStillInQueue = baskets.some(b => b.id === activeBasketId);
            if (!activeBasketStillInQueue) {
                setActiveBasket(baskets.length > 0 ? baskets[0].id : null);
            } else {
                const updatedBasket = baskets.find(b => b.id === activeBasketId);
                if(updatedBasket) basketDataCache.set(activeBasketId, updatedBasket);
                renderActiveOrder();
            }

        } catch (error) {
            console.error("Error fetching queue:", error);
            queueList.innerHTML = '<p style="color: red;">Could not load queue.</p>';
        }
    };

    const setActiveBasket = (basketId) => {
        activeBasketId = basketId;
        const currentActive = document.querySelector('.queue-item.active');
        if (currentActive) currentActive.classList.remove('active');
        if (basketId) {
            const newActive = document.querySelector(`.queue-item[data-basket-id='${basketId}']`);
            if (newActive) newActive.classList.add('active');
        }
        renderActiveOrder();
    };
    
    const startRobustTimer = (basket) => {
        clearInterval(timerInterval);
        
        // Ensure the timestamp string is in a format JS Date can parse consistently,
        // especially if it doesn't already have a 'Z'.
        let startTimeStr = basket.soaking_started_at;
        if (!startTimeStr.endsWith('Z')) {
            startTimeStr += 'Z';
        }
        const startTime = new Date(startTimeStr);

        const update = () => {
            const now = new Date();
            const elapsedSeconds = Math.floor((now - startTime) / 1000);
            const remainingSeconds = SOAKING_TIME_SECONDS - elapsedSeconds;

            if (remainingSeconds > 0) {
                timerDisplay.textContent = formatTime(remainingSeconds);
            } else {
                timerDisplay.textContent = 'Soaking Complete!';
                clearInterval(timerInterval);
            }
        };
        update();
        timerInterval = setInterval(update, 1000);
    };
    
    const handleStartSoaking = async () => {
        if (!activeBasketId) return;
        startBtn.disabled = true;
        try {
            await fetch(`/api/baskets/${activeBasketId}/start_soaking`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user_id: USER_ID })
            });
        } catch (error) {
            alert(`Error starting timer: ${error.message}`);
            startBtn.disabled = false;
        }
    };
    
    const handleComplete = async () => {
        if (!activeBasketId) return;
        completeBtn.disabled = true;
        startBtn.disabled = true; // Also disable start button during submission
        completeBtn.textContent = 'Sending...';

        try {
            const response = await fetch(`/api/baskets/${activeBasketId}/finish_cycle?station_type=${STATION_TYPE}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user_id: USER_ID })
            });
            if (!response.ok) {
                const err = await response.json();
                throw new Error(err.detail || 'Failed to complete pretreat.');
            }
        } catch (error) {
            alert(`Error: ${error.message}`);
            // Re-enable on failure
            completeBtn.disabled = false;
            // Only re-enable start if timer hasn't been started
            const basket = basketDataCache.get(activeBasketId);
            if (!basket || !basket.soaking_started_at) {
                startBtn.disabled = false;
            }
        } finally {
            completeBtn.textContent = 'Mark Pretreat Complete & Send to Wash';
        }
    };

    // --- Event Listeners ---
    queueList.addEventListener('click', (e) => {
        const queueItem = e.target.closest('.queue-item');
        if (queueItem) {
            setActiveBasket(parseInt(queueItem.dataset.basketId, 10));
        }
    });
    startBtn.addEventListener('click', handleStartSoaking);
    completeBtn.addEventListener('click', handleComplete);

    // --- Socket Setup ---
    // --- THIS IS THE FIX: Use the global socket instance ---
    const socket = window.appSocket;

    function onConnect() {
        socket.emit('join', { room: `hub:${HUB_ID}` });
        fetchQueue();
    }
    socket.on('connect', onConnect);
    if(socket.connected) {
        onConnect();
    }
    // --- END OF FIX ---
    
    socket.on('order.updated', () => {
        fetchQueue();
    });

    fetchQueue();
});