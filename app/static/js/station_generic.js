// app/static/js/station_generic.js
document.addEventListener('DOMContentLoaded', () => {
    // --- Config & State ---
    const HUB_ID = 1;
    const USER_ID = 1;
    const STATION_TYPE = document.body.dataset.stationType;
    const STATION_TITLE = document.body.dataset.stationTitle;

    let activeBasketId = null;
    let basketDataCache = new Map();
    let machineStates = new Map();
    let countdownInterval = null;

    // --- DOM Elements ---
    const stationTitleElement = document.getElementById('station-title');
    const queueList = document.getElementById('queue-list');
    const activeOrderDisplay = document.getElementById('active-order-display');
    const activeOrderInfo = document.getElementById('active-order-info');
    const timerDisplay = document.getElementById('timer-display');
    const startBtn = document.getElementById('start-btn');
    const finishBtn = document.getElementById('finish-btn');
    const claimBtn = document.getElementById('claim-btn');
    const machineStatusElement = document.getElementById('machine-status');

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

    const renderActiveOrder = () => {
        clearInterval(countdownInterval);

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
        
        const runningMachine = findMachineForBasket(activeBasketId);

        if (runningMachine && runningMachine.cycle_started_at) {
            startBtn.disabled = true;
            finishBtn.disabled = false;
            claimBtn.disabled = true;
            startTimer(runningMachine);
        } else {
            startBtn.disabled = false;
            finishBtn.disabled = true;
            claimBtn.disabled = false;
            timerDisplay.textContent = '00:00 / ' + formatTime(getCycleTime());
        }
    };
    
    const getCycleTime = () => {
        for (const machine of machineStates.values()) {
            return machine.cycle_time_seconds;
        }
        const defaults = { 'washing': 1800, 'drying': 2400, 'folding': 300 };
        return defaults[STATION_TYPE] || 1800;
    };

    const startTimer = (runningMachine) => {
        clearInterval(countdownInterval);
        
        let startTimeStr = runningMachine.cycle_started_at;
        if (!startTimeStr.endsWith('Z')) {
            startTimeStr += 'Z';
        }
        const startTime = new Date(startTimeStr);
        const targetDuration = runningMachine.cycle_time_seconds;

        const update = () => {
            const now = new Date();
            const elapsedSeconds = (now.getTime() - startTime.getTime()) / 1000;
            
            timerDisplay.textContent = `${formatTime(elapsedSeconds)} / ${formatTime(targetDuration)}`;
        };

        update();
        countdownInterval = setInterval(update, 1000);
    };

    const fetchAndRenderMachineStatus = async () => {
        try {
            const response = await fetch(`/api/stations/${STATION_TYPE}/machines`);
            if (!response.ok) throw new Error('Failed to fetch machine status.');
            const machines = await response.json();
            
            machineStates.clear();
            machines.forEach(m => machineStates.set(m.id, m));
            
            const availableMachines = machines.filter(m => m.state === 'idle').length;
            const totalMachines = machines.length;

            machineStatusElement.innerHTML = `
                <strong>${availableMachines} / ${totalMachines}</strong> Machines Available
            `;
            machineStatusElement.className = availableMachines > 0 ? 'status-available' : 'status-full';
        } catch (error) {
            console.error('Error fetching machine status:', error);
            machineStatusElement.textContent = 'Could not load machine status.';
            machineStatusElement.className = 'status-error';
        }
    };

    const findMachineForBasket = (basketId) => {
        for (const machine of machineStates.values()) {
            if (machine.current_basket_id === basketId) {
                return machine;
            }
        }
        return null;
    };


    // --- Core Logic ---
    const fetchQueue = async () => {
        try {
            await fetchAndRenderMachineStatus();
            const response = await fetch(`/api/queues/${HUB_ID}/${STATION_TYPE}`);
            if (!response.ok) throw new Error("Failed to fetch queue.");
            
            const basketsInQueue = await response.json();
            let allBasketsToDisplay = [...basketsInQueue];
            let idToSetActive = null;

            let runningBasketId = null;
            for (const machine of machineStates.values()) {
                if (machine.state === 'running' && machine.current_basket_id) {
                    runningBasketId = machine.current_basket_id;
                    break;
                }
            }

            if (runningBasketId) {
                idToSetActive = runningBasketId;
                if (!allBasketsToDisplay.some(b => b.id === runningBasketId)) {
                    const basketRes = await fetch(`/api/baskets/${runningBasketId}`);
                    if (basketRes.ok) {
                        const runningBasketData = await basketRes.json();
                        allBasketsToDisplay.unshift(runningBasketData);
                    }
                }
            } else if (basketsInQueue.length > 0) {
                idToSetActive = basketsInQueue[0].id;
            }

            renderQueue(allBasketsToDisplay);
            setActiveBasket(idToSetActive);

        } catch (error) {
            console.error("Error fetching queue:", error);
            queueList.innerHTML = `<p style="color: red;">Could not load queue.</p>`;
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

    const handleStartCycle = async () => {
        if (!activeBasketId) return;
        startBtn.disabled = true;
        try {
            await fetch(`/api/baskets/${activeBasketId}/start_cycle?station_type=${STATION_TYPE}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user_id: USER_ID })
            });
        } catch (error) {
            alert(`Error: ${error.message}`);
            startBtn.disabled = false;
        }
    };
    
    const handleFinishCycle = async () => {
        if (!activeBasketId) return;
        finishBtn.disabled = true;
        try {
            await fetch(`/api/baskets/${activeBasketId}/finish_cycle?station_type=${STATION_TYPE}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user_id: USER_ID })
            });
        } catch (error) {
            alert(`Error: ${error.message}`);
            finishBtn.disabled = false;
        }
    };

    // --- Event Listeners & Sockets ---
    queueList.addEventListener('click', (e) => {
        const queueItem = e.target.closest('.queue-item');
        if (queueItem) {
            setActiveBasket(parseInt(queueItem.dataset.basketId, 10));
        }
    });

    startBtn.addEventListener('click', handleStartCycle);
    finishBtn.addEventListener('click', handleFinishCycle);
    claimBtn.addEventListener('click', () => alert('Issue reporting not implemented yet.'));

    document.addEventListener('keydown', (e) => {
        if (!activeBasketId) return;
        if (e.key.toUpperCase() === 'S' && !startBtn.disabled) {
            e.preventDefault();
            handleStartCycle();
        } else if (e.key.toUpperCase() === 'F' && !finishBtn.disabled) {
            e.preventDefault();
            handleFinishCycle();
        }
    });

    // --- THIS IS THE FIX: Use the global socket instance ---
    const socket = window.appSocket;
    
    function onConnect() {
        console.log(`${STATION_TITLE} socket connected.`);
        socket.emit('join', { room: `station:${HUB_ID}:${STATION_TYPE}` });
        socket.emit('join', { room: `hub:${HUB_ID}` });
        fetchQueue();
    }
    socket.on('connect', onConnect);
    if (socket.connected) {
        onConnect();
    }
    // --- END OF FIX ---
    
    socket.on('order.updated', () => fetchQueue());

    socket.on('machine.updated', async () => {
        // This is a crucial change: we refetch the whole queue to get the correct active basket
        await fetchQueue();
    });

    // --- Initialization ---
    stationTitleElement.textContent = STATION_TITLE;
    fetchQueue();
});