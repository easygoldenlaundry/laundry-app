// app/static/js/dashboard.js
document.addEventListener('DOMContentLoaded', () => {
    const HUB_ID = 1;
    const ordersContainer = document.getElementById('orders-container');
    const statusIndicator = document.getElementById('connection-status');
    
    const TIMELINE_STEPS = [
        {'id': 'Booked', 'label': 'Booked', 'icon': 'fa-solid fa-file-alt'},
        {'id': 'PickedUp', 'label': 'Picked Up', 'icon': 'fa-solid fa-truck-pickup'},
        {'id': 'AtHub', 'label': 'At Hub', 'icon': 'fa-solid fa-warehouse'},
        {'id': 'Imaging', 'label': 'Imaging', 'icon': 'fa-solid fa-camera'},
        {'id': 'Pretreat', 'label': 'Pretreat', 'icon': 'fa-solid fa-spray-can'},
        {'id': 'Washing', 'label': 'Washing', 'icon': 'fa-solid fa-tint'},
        {'id': 'Drying', 'label': 'Drying', 'icon': 'fa-solid fa-wind'},
        {'id': 'Folding', 'label': 'Folding', 'icon': 'fa-solid fa-tshirt'},
        {'id': 'QA', 'label': 'QA', 'icon': 'fa-solid fa-clipboard-check'},
        {'id': 'Ready', 'label': 'Ready', 'icon': 'fa-solid fa-box-open'},
        {'id': 'OnTheWay', 'label': 'On The Way', 'icon': 'fa-solid fa-truck-fast'},
        {'id': 'Delivered', 'label': 'Delivered', 'icon': 'fa-solid fa-home'},
    ];

    const STATUS_TO_TIMELINE_ID = {
        "Created": "Booked", "AssignedToDriver": "Booked", "PickedUp": "PickedUp",
        "DeliveredToHub": "AtHub", "Imaging": "Imaging", "Processing": "Processing",
        "QA": "QA", // This status now maps to the QA step directly
        "ReadyForDelivery": "Ready", "OutForDelivery": "OnTheWay", "OnRouteToCustomer": "OnTheWay",
        "Delivered": "Delivered", "Closed": "Delivered"
    };

    const BASKET_STATUS_TO_TIMELINE_ID = {
        "Pretreat": "Pretreat", "Washing": "Washing", "Drying": "Drying", "Folding": "Folding", "QA": "QA"
    };
    
    // --- THIS IS THE FIX: Use the global socket instance created in base.html ---
    const socket = window.appSocket;

    function onConnect() {
        statusIndicator.textContent = 'Connected';
        statusIndicator.className = 'status-connected';
        // The join to hub:1 is already handled by base.html
        fetchAllActiveOrders();
    }

    socket.on('connect', onConnect);

    // If the socket is already connected when this script runs, the 'connect'
    // event may have already fired, so we need to manually trigger the setup.
    if (socket.connected) {
        onConnect();
    }
    // --- END OF FIX ---

    socket.on('disconnect', () => {
        statusIndicator.textContent = 'Disconnected';
        statusIndicator.className = 'status-disconnected';
    });

    socket.on('order.updated', (order) => {
        updateOrInsertOrderCard(order);
    });
    
    const createOrderCard = (order) => {
        const card = document.createElement('div');
        card.className = 'order-card';
        card.id = `order-${order.id}`;
        card.dataset.createdAt = order.created_at;
        if (order.sla_deadline) {
            card.dataset.slaDeadline = order.sla_deadline;
        }

        const timelineStepIds = TIMELINE_STEPS.map(step => step.id);
        const totalSteps = timelineStepIds.length;
        let markersHTML = '';
        let overallProgressPercent = 0;
        
        const orderTimelineId = STATUS_TO_TIMELINE_ID[order.status];

        let furthestMarkerIndex = -1;

        if (orderTimelineId !== "Processing") {
            try {
                const currentIndex = timelineStepIds.indexOf(orderTimelineId);
                const progress = (currentIndex + 0.5) / totalSteps * 100;
                overallProgressPercent = currentIndex / (totalSteps - 1) * 100;
                furthestMarkerIndex = currentIndex;
                
                const icon = (order.status === "OutForDelivery" || order.status === "OnRouteToCustomer") ? 'fa-solid fa-truck' : 'fa-solid fa-box';
                
                markersHTML = `
                    <div class="timeline-marker" style="left: ${progress}%;">
                        <div class="marker-icon"><i class="${icon}"></i></div>
                    </div>`;
            } catch(e) { /* ignore status not on timeline */ }

        } else { // Order status is "Processing", so we show basket markers
            const imagingIndex = timelineStepIds.indexOf('Imaging');
            overallProgressPercent = imagingIndex / (totalSteps - 1) * 100;
            
            const basketGroups = {};
            (order.baskets || []).forEach(basket => {
                const cleanStatus = basket.status.split('-')[0]; // 'Washing-InProgress' -> 'Washing'
                const basketTimelineId = BASKET_STATUS_TO_TIMELINE_ID[cleanStatus];
                if (basketTimelineId) {
                    basketGroups[basketTimelineId] = (basketGroups[basketTimelineId] || 0) + 1;
                }
            });
            
            let maxBasketIndex = -1;
            Object.entries(basketGroups).forEach(([timelineId, count]) => {
                try {
                    const currentIndex = timelineStepIds.indexOf(timelineId);
                    maxBasketIndex = Math.max(maxBasketIndex, currentIndex);
                    const progress = (currentIndex + 0.5) / totalSteps * 100;
                    
                    markersHTML += `
                        <div class="timeline-marker" style="left: ${progress}%;">
                            <div class="marker-icon">
                                <i class="fa-solid fa-box-open"></i>
                                ${count > 1 ? `<span class="marker-count">${count}</span>` : ''}
                            </div>
                        </div>`;
                } catch(e) { /* ignore */ }
            });
            furthestMarkerIndex = maxBasketIndex > -1 ? maxBasketIndex : imagingIndex;
        }

        let stepsHTML = '';
        TIMELINE_STEPS.forEach((step, index) => {
            let statusClass = 'pending';
            if (index < furthestMarkerIndex) {
                statusClass = 'completed';
            } else if (index === furthestMarkerIndex) {
                statusClass = 'active';
            }
            stepsHTML += `
                <li class="step ${statusClass}">
                    <div class="step-icon"><i class="${step.icon}"></i></div>
                    <div class="step-label">${step.label}</div>
                </li>
            `;
        });

        card.innerHTML = `
            <div class="order-header">
                <div class="order-title">
                    <h3><a href="/track/${order.tracking_token}" target="_blank">Order #${order.id}</a></h3>
                    <p>${order.customer_name}</p>
                </div>
                <div class="timers-container-inline">
                    <div class="sla-details"></div>
                </div>
            </div>

            <div class="timeline-container">
                <div class="timeline-track"></div>
                <div class="timeline-progress" style="width: ${overallProgressPercent}%;"></div>
                <div class="timeline-markers">${markersHTML}</div>
                <ul class="timeline-steps">${stepsHTML}</ul>
            </div>
        `;
        return card;
    };

    const updateOrInsertOrderCard = (order) => {
        const existingCard = document.getElementById(`order-${order.id}`);
        const isInactive = ["Delivered", "Closed", "Cancelled"].includes(order.status);

        if (isInactive) {
            if (existingCard) existingCard.remove();
            return;
        }
        
        const newCard = createOrderCard(order);
        if (existingCard) {
            ordersContainer.replaceChild(newCard, existingCard);
        } else {
            ordersContainer.prepend(newCard);
        }
    };

    const fetchAllActiveOrders = async () => {
        try {
            const response = await fetch(`/api/admin/orders/active?hub_id=${HUB_ID}`, {
                credentials: 'include'
            });
            if (!response.ok) throw new Error('Failed to fetch active orders');
            const orders = await response.json();
            ordersContainer.innerHTML = '';
            orders.forEach(order => ordersContainer.appendChild(createOrderCard(order)));
        } catch (error) {
            console.error(error);
            ordersContainer.innerHTML = '<p style="color: red; text-align: center;">Could not load orders.</p>';
        }
    };
    
    const formatTime = (totalSeconds) => {
        const hours = Math.floor(totalSeconds / 3600).toString().padStart(2, '0');
        const minutes = Math.floor((totalSeconds % 3600) / 60).toString().padStart(2, '0');
        const seconds = (totalSeconds % 60).toString().padStart(2, '0');
        return `${hours}:${minutes}:${seconds}`;
    };

    const updateAllTimers = () => {
        const now = new Date();
        document.querySelectorAll('.order-card').forEach(card => {
            const createdAt = new Date(card.dataset.createdAt); 
            const slaDetails = card.querySelector('.sla-details');
            if (!slaDetails) return;
            if (card.dataset.slaDeadline) {
                const deadline = new Date(card.dataset.slaDeadline);
                const ageInSeconds = Math.round((now - createdAt) / 1000);
                const diffSeconds = Math.round((deadline - now) / 1000);
                const isBreached = diffSeconds < 0;
                const deadlineTime = deadline.getHours().toString().padStart(2, '0') + ':' + deadline.getMinutes().toString().padStart(2, '0');
                const ageString = formatTime(ageInSeconds);
                const timeLeftString = (isBreached ? '+' : '-') + formatTime(Math.abs(diffSeconds));
                slaDetails.innerHTML = `<span class="sla-deadline-time">${deadlineTime}</span><span class="sla-time-breakdown">${ageString} / ${timeLeftString}</span>`;
                const totalDurationSeconds = (deadline - createdAt) / 1000;
                let isWarning = false;
                if (totalDurationSeconds > 60) {
                    isWarning = !isBreached && (ageInSeconds / totalDurationSeconds) >= 0.9;
                }
                slaDetails.classList.remove('sla-warning', 'sla-breached');
                if (isBreached) {
                    slaDetails.classList.add('sla-breached');
                } else if (isWarning) {
                    slaDetails.classList.add('sla-warning');
                }
            } else {
                const ageInSeconds = Math.round((now - createdAt) / 1000);
                slaDetails.innerHTML = `<span class="sla-time-breakdown">Age: ${formatTime(ageInSeconds)}</span>`;
                slaDetails.classList.remove('sla-warning', 'sla-breached');
            }
        });
    };

    // --- Initialization ---
    fetchAllActiveOrders();
    setInterval(updateAllTimers, 1000);
});