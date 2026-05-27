// Cart functionality
let cart = JSON.parse(localStorage.getItem('cart')) || [];

// ==================== JWT Token 管理 ====================

function getValidToken() {
    const accessToken = localStorage.getItem('access_token');
    if (!accessToken) return null;

    try {
        const payload = JSON.parse(atob(accessToken.split('.')[1]));
        if (payload.exp * 1000 > Date.now()) {
            return accessToken;
        }
    } catch (e) {
        // Invalid token format
    }

    // Token expired or invalid — try to use refresh token
    const refreshToken = localStorage.getItem('refresh_token');
    if (refreshToken) {
        // Sync refresh (we can't await in a sync function, but we can fire and hope)
        fetch('/api/users/token/refresh/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ refresh: refreshToken })
        }).then(r => r.json()).then(data => {
            if (data.access) {
                localStorage.setItem('access_token', data.access);
            } else {
                localStorage.removeItem('access_token');
                localStorage.removeItem('refresh_token');
            }
        }).catch(() => {});
    }
    return null;
}

function getAuthHeaders() {
    const token = getValidToken();
    const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value;
    return {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfToken || '',
        ...(token ? { 'Authorization': 'Bearer ' + token } : {})
    };
}

function isLoggedIn() {
    return !!localStorage.getItem('access_token');
}

// ==================== 购物车基础操作 ====================

function updateCartBadge() {
    const badge = document.querySelector('.cart-badge');
    if (badge) {
        const total = cart.reduce((sum, item) => sum + item.quantity, 0);
        badge.textContent = total;
        badge.style.display = total > 0 ? 'block' : 'none';
    }
}

async function addToCart(productId, productName, price, image, quantity = 1) {
    if (!isLoggedIn()) {
        showNotification('Please login first to add items to cart', 'warning');
        setTimeout(() => {
            window.location.href = '/users/login/?next=' + encodeURIComponent(window.location.href);
        }, 1000);
        return;
    }

    const existingItem = cart.find(item => item.id === productId);

    if (existingItem) {
        existingItem.quantity += quantity;
    } else {
        cart.push({
            id: productId,
            name: productName,
            price: price,
            image: image,
            quantity: quantity
        });
    }

    localStorage.setItem('cart', JSON.stringify(cart));
    updateCartBadge();
    showNotification('Added to cart!');

    // Sync to backend
    try {
        await fetch('/api/orders/cart/add/', {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify({
                product_id: productId,
                quantity: quantity
            })
        });
    } catch (e) {
        console.log('Sync to server failed, will sync later');
    }
}

function updateQuantity(productId, quantity) {
    const item = cart.find(item => item.id === productId);
    if (item) {
        if (quantity <= 0) {
            removeFromCart(productId);
        } else {
            item.quantity = quantity;
            localStorage.setItem('cart', JSON.stringify(cart));
            updateCartBadge();
            if (typeof renderCart === 'function') renderCart();
        }
    }
}

function removeFromCart(productId) {
    cart = cart.filter(item => item.id !== productId);
    localStorage.setItem('cart', JSON.stringify(cart));
    updateCartBadge();
    if (typeof renderCart === 'function') renderCart();
}

function clearCart() {
    cart = [];
    localStorage.setItem('cart', JSON.stringify(cart));
    updateCartBadge();
    if (typeof renderCart === 'function') renderCart();
}

function getCartTotal() {
    return cart.reduce((sum, item) => sum + (item.price * item.quantity), 0);
}

function showNotification(message, type = 'success') {
    const notification = document.createElement('div');
    notification.className = `alert alert-${type}`;
    notification.style.cssText = `
        position: fixed;
        top: 80px;
        right: 20px;
        z-index: 1000;
        animation: slideIn 0.3s ease-out;
    `;
    notification.textContent = message;
    document.body.appendChild(notification);

    setTimeout(() => {
        notification.remove();
    }, 3000);
}

// ==================== 订单弹窗 ====================

let orderModalMode = 'checkout'; // 'checkout' | 'direct'

function openOrderModal(mode, productData = null) {
    orderModalMode = mode;
    const modal = document.getElementById('orderModal');
    const title = document.getElementById('modalTitle');
    const summary = document.getElementById('modalOrderSummary');
    const submitBtn = document.getElementById('modalSubmitBtn');

    // Pre-fill from user profile if available
    const savedAddress = localStorage.getItem('order_address') || '';
    const savedName = localStorage.getItem('order_receiver_name') || '';
    const savedPhone = localStorage.getItem('order_receiver_phone') || '';

    document.getElementById('modal_address').value = savedAddress;
    document.getElementById('modal_receiver_name').value = savedName;
    document.getElementById('modal_receiver_phone').value = savedPhone;
    document.getElementById('modal_remark').value = '';

    if (mode === 'direct' && productData) {
        title.textContent = 'Confirm Order';
        summary.innerHTML = `
            <div class="summary-row">
                <span>${productData.name} × ${productData.quantity}</span>
                <span>¥${(productData.price * productData.quantity).toFixed(2)}</span>
            </div>
            <div class="summary-row total">
                <span>Total</span>
                <span>¥${(productData.price * productData.quantity).toFixed(2)}</span>
            </div>
        `;
        submitBtn.textContent = 'Place Order';
        // Store product data for direct purchase
        submitBtn.dataset.productId = productData.id;
        submitBtn.dataset.quantity = productData.quantity;
        submitBtn.dataset.price = productData.price;
        submitBtn.dataset.name = productData.name;
        submitBtn.dataset.image = productData.image || '';
    } else {
        // Cart checkout mode
        title.textContent = 'Checkout';
        const subtotal = getCartTotal();
        summary.innerHTML = `
            <div class="summary-row">
                <span>Items (${cart.reduce((s, i) => s + i.quantity, 0)})</span>
                <span>¥${subtotal.toFixed(2)}</span>
            </div>
            <div class="summary-row">
                <span>Shipping</span>
                <span style="color: var(--success);">Free</span>
            </div>
            <div class="summary-row total">
                <span>Total</span>
                <span>¥${subtotal.toFixed(2)}</span>
            </div>
        `;
        submitBtn.textContent = 'Place Order';
    }

    modal.classList.add('active');
}

function closeOrderModal() {
    document.getElementById('orderModal').classList.remove('active');
}

async function syncCartToServer() {
    if (!isLoggedIn() || cart.length === 0) return true;

    for (const item of cart) {
        try {
            const resp = await fetch('/api/orders/cart/add/', {
                method: 'POST',
                headers: getAuthHeaders(),
                body: JSON.stringify({
                    product_id: item.id,
                    quantity: item.quantity
                })
            });
            const data = await resp.json();
            if (data.code !== 0) {
                console.error('Cart sync error for item', item.id, data.msg);
                return false;
            }
        } catch (e) {
            console.error('Cart sync network error:', e);
            return false;
        }
    }
    return true;
}

async function submitOrder() {
    const address = document.getElementById('modal_address').value.trim();
    const receiverName = document.getElementById('modal_receiver_name').value.trim();
    const receiverPhone = document.getElementById('modal_receiver_phone').value.trim();
    const remark = document.getElementById('modal_remark').value.trim();

    if (!address) { showNotification('Please enter your address', 'danger'); return; }
    if (!receiverName) { showNotification('Please enter receiver name', 'danger'); return; }
    if (!receiverPhone) { showNotification('Please enter receiver phone', 'danger'); return; }

    // Save for next time
    localStorage.setItem('order_address', address);
    localStorage.setItem('order_receiver_name', receiverName);
    localStorage.setItem('order_receiver_phone', receiverPhone);

    const submitBtn = document.getElementById('modalSubmitBtn');
    submitBtn.disabled = true;
    submitBtn.textContent = 'Processing...';

    try {
        const headers = getAuthHeaders();

        let response;
        let orderData;

        if (orderModalMode === 'direct') {
            // 直接购买模式
            const productId = parseInt(document.getElementById('modalSubmitBtn').dataset.productId);
            const quantity = parseInt(document.getElementById('modalSubmitBtn').dataset.quantity);

            response = await fetch('/api/orders/direct-create/', {
                method: 'POST',
                headers: headers,
                body: JSON.stringify({
                    product_id: productId,
                    quantity: quantity,
                    address: address,
                    receiver_name: receiverName,
                    receiver_phone: receiverPhone,
                    remark: remark
                })
            });

            const data = await response.json();

            if (data.code === 0) {
                orderData = data.data;
                showNotification('Order placed successfully! Order No: ' + orderData.order_no);
            } else {
                showNotification(data.msg || 'Order failed', 'danger');
                submitBtn.disabled = false;
                submitBtn.textContent = 'Place Order';
                return;
            }
        } else {
            // Cart checkout mode - send items from localStorage
            if (cart.length === 0) {
                showNotification('Your cart is empty', 'danger');
                submitBtn.disabled = false;
                submitBtn.textContent = 'Place Order';
                return;
            }

            const items = cart.map(item => ({
                product_id: item.id,
                quantity: item.quantity
            }));

            response = await fetch('/api/orders/create/', {
                method: 'POST',
                headers: headers,
                body: JSON.stringify({
                    address: address,
                    receiver_name: receiverName,
                    receiver_phone: receiverPhone,
                    remark: remark,
                    items: items
                })
            });

            const data = await response.json();

            if (data.code === 0) {
                orderData = data.data;
                clearCart();
                // Also clear backend cart
                await fetch('/api/orders/cart/clear/', {
                    method: 'DELETE',
                    headers: headers
                }).catch(() => {});
                showNotification('Order placed successfully! Order No: ' + orderData.order_no);
            } else {
                showNotification(data.msg || 'Order failed', 'danger');
                submitBtn.disabled = false;
                submitBtn.textContent = 'Place Order';
                return;
            }
        }

        closeOrderModal();
        setTimeout(() => {
            window.location.href = '/orders/';
        }, 1500);

    } catch (error) {
        console.error('Order error:', error);
        showNotification('Order failed. Please try again.', 'danger');
        submitBtn.disabled = false;
        submitBtn.textContent = 'Place Order';
    }
}

// ==================== 购物车页面渲染 ====================

function renderCart() {
    const cartContainer = document.getElementById('cart-items');
    const cartSubtotal = document.getElementById('cart-subtotal');
    const cartTotal = document.getElementById('cart-total');

    if (!cartContainer) return;

    if (cart.length === 0) {
        cartContainer.innerHTML = `
            <div class="empty-state">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="120" height="120">
                    <circle cx="9" cy="21" r="1"></circle>
                    <circle cx="20" cy="21" r="1"></circle>
                    <path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6"></path>
                </svg>
                <h3>Your cart is empty</h3>
                <p>Start shopping to add items to your cart</p>
                <a href="/products/" class="btn btn-primary">Browse Products</a>
            </div>
        `;
        if (cartSubtotal) cartSubtotal.textContent = '¥0.00';
        if (cartTotal) cartTotal.textContent = '¥0.00';
        return;
    }

    const subtotal = cart.reduce((sum, item) => sum + (item.price * item.quantity), 0);

    cartContainer.innerHTML = cart.map(item => `
        <div class="card" style="display: flex; align-items: center; padding: 1rem; margin-bottom: 1rem;">
            <img src="${item.image}" alt="${item.name}" style="width: 100px; height: 100px; object-fit: cover; border-radius: 8px;">
            <div style="flex: 1; margin-left: 1.5rem;">
                <h3 style="margin-bottom: 0.5rem;">${item.name}</h3>
                <p class="price">¥${item.price.toFixed(2)}</p>
            </div>
            <div class="quantity-control">
                <button class="quantity-btn" onclick="updateQuantity(${item.id}, ${item.quantity - 1})">-</button>
                <input type="number" class="quantity-input" value="${item.quantity}" min="1" readonly>
                <button class="quantity-btn" onclick="updateQuantity(${item.id}, ${item.quantity + 1})">+</button>
            </div>
            <div style="text-align: right; margin-left: 1.5rem;">
                <p class="price">¥${(item.price * item.quantity).toFixed(2)}</p>
                <button class="btn btn-danger btn-sm" onclick="removeFromCart(${item.id})" style="margin-top: 0.5rem;">Remove</button>
            </div>
        </div>
    `).join('');

    if (cartSubtotal) cartSubtotal.textContent = '¥' + subtotal.toFixed(2);
    if (cartTotal) cartTotal.textContent = '¥' + subtotal.toFixed(2);
}

// ==================== 初始化 ====================

document.addEventListener('DOMContentLoaded', function() {
    updateCartBadge();
    renderCart();
});

// Add CSS for slideIn animation
const style = document.createElement('style');
style.textContent = `
    @keyframes slideIn {
        from { transform: translateX(100%); opacity: 0; }
        to { transform: translateX(0); opacity: 1; }
    }
`;
document.head.appendChild(style);
