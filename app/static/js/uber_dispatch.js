// app/static/js/uber_dispatch.js
document.addEventListener('DOMContentLoaded', () => {
    // --- STATE & CONFIG ---
    let currentChatOrderId = null;

    // --- DOM SELECTORS ---
    const ordersTableBody = document.getElementById('orders-table-body');
    const statusMessage = document.getElementById('status-message');
    const chatModal = document.getElementById('chat-modal');
    const modalTitle = document.getElementById('modal-title');
    const chatHistory = document.getElementById('modal-chat-history');
    const chatForm = document.getElementById('modal-chat-form');
    const chatInput = document.getElementById('modal-chat-input');
    const closeModalBtn = chatModal.querySelector('.close-btn');

    // --- UTILITY & RENDER FUNCTIONS ---
    const showStatus = (message, type) => {
        statusMessage.textContent = message;
        statusMessage.className = `status-${type}`;
        statusMessage.style.display = 'block';
        setTimeout(() => { statusMessage.style.display = 'none'; }, 4000);
    };

    const fetchAndRenderOrders = async () => {
        try {
            const response = await fetch('/api/admin/uber-orders');
            if (!response.ok) throw new Error('Failed to fetch orders.');
            const orders = await response.json();
            renderOrders(orders);
        } catch (error) {
            ordersTableBody.innerHTML = `<tr><td colspan="6" style="color:red; text-align:center;">Error: ${error.message}</td></tr>`;
        }
    };

    const renderOrders = (orders) => {
        ordersTableBody.innerHTML = '';
        if (orders.length === 0) {
            ordersTableBody.innerHTML = `<tr><td colspan="6" style="text-align:center;">No active Uber dispatch orders found.</td></tr>`;
            return;
        }
        orders.forEach(order => {
            const tr = document.createElement('tr');
            tr.id = `order-row-${order.id}`;

            const unreadBadge = order.unread_message_count > 0
                ? `<span class="unread-count-badge">${order.unread_message_count}</span>`
                : '0';
            
            let actionButtonsHtml = '';
            const isCompleted = ['Delivered', 'Closed'].includes(order.status);

            if (isCompleted && order.unread_message_count > 0) {
                 actionButtonsHtml += `<button data-action="finish_chat" data-order-id="${order.id}">Finish Chat</button>`;
            } else if (!isCompleted) {
                if (order.status === 'Created') {
                    actionButtonsHtml = `<button data-action="picked_up" data-order-id="${order.id}">Mark Picked Up</button>`;
                } else if (order.status === 'PickedUp') {
                    actionButtonsHtml = `<button data-action="delivered_to_hub" data-order-id="${order.id}">Mark at Hub</button>`;
                } else if (order.status === 'OutForDelivery') {
                    actionButtonsHtml = `<button data-action="picked_up_from_hub" data-order-id="${order.id}">Mark Picked Up from Hub</button>`;
                } else if (order.status === 'OnRouteToCustomer') {
                    actionButtonsHtml = `<button data-action="delivered_to_customer" data-order-id="${order.id}">Mark Delivered</button>`;
                }
            }

            tr.innerHTML = `
                <td><a href="/track/${order.tracking_token}" target="_blank">${order.id}</a></td>
                <td>${order.customer_name}</td>
                <td>${order.status}</td>
                <td class="unread-cell">${unreadBadge}</td>
                <td><a class="phone-link" href="tel:${order.customer_phone}">${order.customer_phone}</a></td>
                <td class="actions">
                    <button data-action="chat" data-order-id="${order.id}">Chat</button>
                    ${actionButtonsHtml}
                </td>
            `;
            ordersTableBody.appendChild(tr);
        });
    };
    
    const renderChatHistory = (messages) => {
        chatHistory.innerHTML = '';
        messages.forEach(msg => {
            appendMessageToChat(msg);
        });
        chatHistory.scrollTop = chatHistory.scrollHeight;
    };

    const appendMessageToChat = (msg) => {
        const messageDiv = document.createElement('div');
        messageDiv.className = `chat-message ${msg.sender_role}`;
        
        const timestamp = new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

        messageDiv.innerHTML = `
            <p>${msg.content}</p>
            <div class="meta">${timestamp}</div>
        `;
        chatHistory.appendChild(messageDiv);
        chatHistory.scrollTop = chatHistory.scrollHeight;
    };

    // --- EVENT HANDLERS ---
    const handleTableClick = async (event) => {
        const target = event.target;
        const action = target.dataset.action;
        const orderId = target.dataset.orderId;
        if (!action || !orderId) return;

        if (action === 'chat') {
            currentChatOrderId = parseInt(orderId);
            socket.emit('join', { room: `order:${currentChatOrderId}` });
            
            modalTitle.textContent = `Chat for Order #${orderId}`;
            chatHistory.innerHTML = '<p>Loading chat...</p>';
            chatModal.style.display = 'block';
            
            try {
                await fetch(`/api/orders/${orderId}/messages/mark-read`, { method: 'POST' });
                document.dispatchEvent(new CustomEvent('unreadMessagesUpdated'));
                
                fetchAndRenderOrders(); 
                
                const response = await fetch(`/api/orders/${orderId}/messages`);
                const messages = await response.json();
                renderChatHistory(messages);
            } catch (error) {
                chatHistory.innerHTML = '<p style="color:red;">Could not load chat history.</p>';
            }

        } else if (action === 'finish_chat') {
            target.disabled = true;
            try {
                await fetch(`/api/admin/orders/${orderId}/resolve-chat`, { method: 'POST' });
                showStatus(`Chat for order #${orderId} has been resolved.`, 'success');
                target.closest('tr').remove();
            } catch (error) {
                showStatus('Could not resolve chat.', 'error');
                target.disabled = false;
            }

        } else { // Handle all status update actions
            target.disabled = true;
            try {
                const response = await fetch('/api/admin/uber-orders/update-status', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ order_id: parseInt(orderId), action: action })
                });
                if (!response.ok) {
                    const err = await response.json();
                    throw new Error(err.detail || 'Failed to update status.');
                }
                showStatus(`Order #${orderId} status updated successfully.`, 'success');
                fetchAndRenderOrders();
            } catch (error) {
                showStatus(`Error: ${error.message}`, 'error');
                target.disabled = false;
            }
        }
    };

    const handleChatSubmit = async (event) => {
        event.preventDefault();
        const content = chatInput.value.trim();
        if (!content || !currentChatOrderId) return;
        
        chatInput.disabled = true;
        try {
            await fetch(`/api/orders/${currentChatOrderId}/messages`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: content }) // Ensure key is "message"
            });
            chatInput.value = ''; // Message will be appended via WebSocket
        } catch (error) {
            showStatus('Failed to send message.', 'error');
        } finally {
            chatInput.disabled = false;
            chatInput.focus();
        }
    };

    // --- SOCKET.IO ---
    // --- THIS IS THE FIX: Use the global socket instance ---
    const socket = window.appSocket;

    function onConnect() {
        console.log('Admin socket connected for Uber dispatch.');
    }
    socket.on('connect', onConnect);
    if (socket.connected) {
        onConnect();
    }
    // --- END OF FIX ---

    socket.on('order.updated', (order) => {
        fetchAndRenderOrders();
    });

    socket.on('message.new', (message) => {
        if (message.order_id === currentChatOrderId) {
            appendMessageToChat(message);
        } else {
            fetchAndRenderOrders();
        }
    });

    const closeModal = () => {
        if (currentChatOrderId) {
            // Leave the order-specific room when the modal is closed
            socket.emit('leave', { room: `order:${currentChatOrderId}` });
        }
        chatModal.style.display = 'none';
        currentChatOrderId = null;
    };

    // --- INITIALIZATION ---
    ordersTableBody.addEventListener('click', handleTableClick);
    chatForm.addEventListener('submit', handleChatSubmit);
    closeModalBtn.onclick = closeModal;
    window.onclick = (event) => {
        if (event.target == chatModal) {
            closeModal();
        }
    };
    
    fetchAndRenderOrders();
});