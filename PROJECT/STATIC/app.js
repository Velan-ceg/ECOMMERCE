
document.addEventListener('DOMContentLoaded', () => {
 
  document.body.addEventListener('click', (ev) => {
    const addBtn = ev.target.closest('.btn-add');
    if (addBtn) {
      const id = addBtn.dataset.id;
      addToCart(id, 1);
      return;
    }
    const detBtn = ev.target.closest('.btn-details');
    if (detBtn) {
      const id = detBtn.dataset.id;
      toggleDetails(id);
      return;
    }
    const removeBtn = ev.target.closest('.remove');
    if (removeBtn) {
      ev.preventDefault();
      const cid = removeBtn.dataset.id;
      removeCartItem(cid);
      return;
    }
  });

 
  const updateBtn = document.getElementById('update-cart');
  if (updateBtn) {
    updateBtn.addEventListener('click', (e) => {
      e.preventDefault();
      updateCartFromForm();
    });
  }
});

function toggleDetails(productId) {
  const el = document.getElementById('details-' + productId);
  if (!el) {
   
    fetch('/api/product/' + productId).then(r => r.json()).then(j => {
      if (j.ok && j.product) {
        const p = j.product;
        const card = document.querySelector('[data-product-id="' + productId + '"]');
        if (card) {
          let detail = card.querySelector('.details');
          detail.innerHTML = `<div><strong>SKU:</strong> ${p.sku}</div>
            <div><strong>Stock:</strong> ${p.qty}</div>
            <div style="margin-top:6px">${p.description}</div>`;
          detail.style.display = 'block';
        }
      }
    });
    return;
  }
  el.style.display = (el.style.display === 'block') ? 'none' : 'block';
}

function addToCart(productId, qty) {
  if (!window.ECOM_USER) {
    alert('Please log in to add items to cart');
    window.location.href = '/login';
    return;
  }
  fetch('/api/cart/add', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({product_id: productId, qty: qty})
  }).then(r => {
    if (r.status === 401) {
      alert('Login required');
      window.location = '/login';
      return;
    }
    return r.json();
  }).then(j => {
    if (j && j.ok) {
      alert('Added to cart');
    } else {
      alert('Could not add to cart');
    }
  });
}

function removeCartItem(cartItemId) {
  
  updateCart([{cart_item_id: cartItemId, qty: 0}]);
}

function updateCart(payloadItems) {
  fetch('/api/cart/update', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({items: payloadItems})
  }).then(r => r.json()).then(j => {
    if (j.ok) {
      window.location.reload();
    } else {
      alert('Failed to update cart');
    }
  });
}

function updateCartFromForm(){
  const inputs = document.querySelectorAll('input[data-cart-item-id]');
  const items = [];
  inputs.forEach(inp => {
    items.push({cart_item_id: inp.dataset.cartItemId, qty: Number(inp.value)});
  });
  updateCart(items);
}
