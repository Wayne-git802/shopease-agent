function renderOrderCards(container, data) {
    var orders = Array.isArray(data) ? data : (data.orders || [data]);
    if (!orders.length) return;
    var wrapper = document.createElement('div');
    wrapper.className = 'order-cards-wrapper';
    var statusLabels = {paid:'已付款',shipped:'已发货',completed:'已完成',refunding:'退款中',cancelled:'已取消',refunded:'已退款'};
    orders.forEach(function(order) {
        var status = statusLabels[order.status] || order.status;
        var refundable = ['paid','shipped','completed','refunding'].indexOf(order.status) >= 0;
        var card = document.createElement('div');
        card.className = 'order-card';
        var dateStr = order.created_at ? new Date(order.created_at).toLocaleDateString() : '';
        card.innerHTML =
            '<div class="order-card-main">' +
                '<div class="order-card-product">' + escapeHtml(order.product_name) + '</div>' +
                '<div class="order-card-meta">' +
                    '<span class="order-card-price">' + (order.price || '') + '</span>' +
                    '<span class="order-card-status' + (refundable ? ' refundable' : '') + '">' + status + '</span>' +
                    '<span class="order-card-date">' + dateStr + '</span>' +
                '</div>' +
            '</div>';
        if (refundable) {
            var btn = document.createElement('button');
            btn.className = 'order-refund-btn';
            btn.textContent = '退款';
            btn.onclick = (function(oid) {
                return function() {
                    document.getElementById('workspaceInput').value = '退款 ' + oid;
                    submitWorkspace();
                };
            })(order.order_id);
            card.appendChild(btn);
        }
        wrapper.appendChild(card);
    });
    container.appendChild(wrapper);
}