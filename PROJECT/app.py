# app.py
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
import psycopg2
from psycopg2.extras import RealDictCursor
from werkzeug.security import generate_password_hash, check_password_hash
from decimal import Decimal
import os

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET', 'dev_secret_key_change_me')

# Database config
DB_HOST = os.environ.get('DB_HOST', 'localhost')
DB_NAME = os.environ.get('DB_NAME', 'ecommerce_db')
DB_USER = os.environ.get('DB_USER', 'postgres')
DB_PASS = os.environ.get('DB_PASS', '258036')
DB_PORT = os.environ.get('DB_PORT', '5432')

# ---------- DB helper ----------
def get_conn():
    return psycopg2.connect(
        host=DB_HOST,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASS,
        port=DB_PORT
    )

def query(sql, params=None, fetch=False, fetchone=False):
    conn = get_conn()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(sql, params or ())
        res = None
        if fetchone:
            res = cur.fetchone()
        elif fetch:
            res = cur.fetchall()
        conn.commit()
        return res
    finally:
        cur.close()
        conn.close()

def execute(sql, params=None):
    """For INSERT/UPDATE/DELETE without returning rows"""
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(sql, params or ())
        conn.commit()
    finally:
        cur.close()
        conn.close()

# ---------- auth helpers ----------
def current_user():
    uid = session.get('user_id')
    if not uid:
        return None
    return query("SELECT id, email, full_name FROM users WHERE id = %s", (uid,), fetchone=True)

def get_or_create_cart(user_id):
    cart = query("SELECT * FROM carts WHERE user_id = %s", (user_id,), fetchone=True)
    if cart:
        return cart
    cart_id = query("INSERT INTO carts (user_id) VALUES (%s) RETURNING id", (user_id,), fetchone=True)
    return query("SELECT * FROM carts WHERE id = %s", (cart_id['id'],), fetchone=True)

# ---------- routes ----------

@app.route('/')
def index():
    return redirect(url_for('home_category', category_slug='smartphones'))

@app.route('/login', methods=['GET','POST'])
def login_register():
    if request.method == 'POST':
        action = request.form.get('action')
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        if action == 'register':
            name = request.form.get('fullname', '').strip()
            if not email or not password or not name:
                flash('All fields required for register', 'error')
                return redirect(url_for('login_register'))

            pw_hash = generate_password_hash(password)
            try:
                res = query(
                    "INSERT INTO users (email, password_hash, full_name) VALUES (%s,%s,%s) RETURNING id",
                    (email, pw_hash, name),
                    fetchone=True
                )
                session['user_id'] = res['id']
                return redirect(url_for('index'))
            except Exception as e:
                flash('Email already exists or DB error', 'error')
                return redirect(url_for('login_register'))

        else:  # login
            user = query("SELECT * FROM users WHERE email = %s", (email,), fetchone=True)
            if user and check_password_hash(user['password_hash'], password):
                session['user_id'] = user['id']
                return redirect(url_for('index'))
            flash('Invalid credentials', 'error')
            return redirect(url_for('login_register'))

    return render_template('login_register.html', user=current_user())

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect(url_for('login_register'))

# ---------- category route ----------
@app.route('/category/<category_slug>')
def home_category(category_slug):
    cat = query("SELECT * FROM categories WHERE slug = %s", (category_slug,), fetchone=True)
    if not cat:
        return "Category not found", 404

    products = query("""
        SELECT p.*, COALESCE(p.image_path, '') AS image_path, COALESCE(inv.qty, 0) AS qty
        FROM products p
        LEFT JOIN inventory inv ON inv.product_id = p.id
        WHERE p.category_id = %s
        ORDER BY p.id DESC
        LIMIT 12
    """, (cat['id'],), fetch=True)

    return render_template(f"{category_slug}.html", user=current_user(), products=products, category=cat)

# ---------- admin page ----------
@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        price = float(request.form['price'])
        category_id = request.form['category_id']
        image_path = request.form['image_path']
        sku = request.form['sku']
        qty = int(request.form['qty'])

        # Basic validation
        if not (title and price and category_id and sku and qty >= 0):
            categories = query("SELECT id, name FROM categories", fetch=True)
            return render_template('admin.html', categories=categories, message="All fields required", success=False)

        existing = query("SELECT id FROM products WHERE sku=%s", (sku,), fetchone=True)
        if existing:
            categories = query("SELECT id, name FROM categories", fetch=True)
            return render_template('admin.html', categories=categories, message="SKU already exists!", success=False)

        # Insert into products
        product = query("""
            INSERT INTO products (sku, title, description, price, category_id)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
        """, (sku, title, description, price, category_id), fetchone=True)

        product_id = product['id']

        # Insert image
        query("""
            INSERT INTO product_images (product_id, image_path, is_primary)
            VALUES (%s, %s, true)
        """, (product_id, image_path))

        # Insert stock quantity
        query("""
            INSERT INTO inventory (product_id, qty)
            VALUES (%s, %s)
        """, (product_id, qty))

        categories = query("SELECT id, name FROM categories", fetch=True)
        return render_template('admin.html', categories=categories, message="✅ Product added successfully!", success=True)

    # For GET request
    categories = query("SELECT id, name FROM categories", fetch=True)
    return render_template('admin.html', categories=categories)



# ---------- cart ----------
@app.route('/api/cart/add', methods=['POST'])
def api_cart_add():
    if 'user_id' not in session:
        return jsonify({'ok': False, 'error': 'login_required'}), 401
    user_id = session['user_id']
    product_id = int(request.json.get('product_id'))
    qty = int(request.json.get('qty', 1))

    product = query("SELECT id, price FROM products WHERE id = %s", (product_id,), fetchone=True)
    if not product:
        return jsonify({'ok': False, 'error': 'product_not_found'}), 404

    cart = get_or_create_cart(user_id)
    existing = query("SELECT * FROM cart_items WHERE cart_id = %s AND product_id = %s", (cart['id'], product_id), fetchone=True)

    if existing:
        new_qty = existing['qty'] + qty
        query("UPDATE cart_items SET qty=%s WHERE id=%s", (new_qty, existing['id']))
    else:
        query(
            "INSERT INTO cart_items (cart_id, product_id, qty, unit_price) VALUES (%s,%s,%s,%s)",
            (cart['id'], product_id, qty, product['price'])
        )
    return jsonify({'ok': True})

@app.route('/cart')
def cart_view():
    if 'user_id' not in session:
        flash('Please log in to view cart', 'error')
        return redirect(url_for('login_register'))

    user_id = session['user_id']
    cart = get_or_create_cart(user_id)
    items = query("""
        SELECT ci.id as cart_item_id, p.id AS product_id, p.title, p.description, ci.qty, ci.unit_price,
               COALESCE(p.image_path,'') AS image_path
        FROM cart_items ci
        JOIN products p ON p.id = ci.product_id
        WHERE ci.cart_id = %s
    """, (cart['id'],), fetch=True)
    total = sum((Decimal(item['qty']) * item['unit_price']) for item in items) if items else Decimal('0.00')

    return render_template('cart.html', user=current_user(), items=items, total=total)

@app.route('/api/cart/update', methods=['POST'])
def api_cart_update():
    if 'user_id' not in session:
        return jsonify({'ok': False, 'error': 'login_required'}), 401
    data = request.json
    for item in data.get('items', []):
        cid = int(item['cart_item_id'])
        qty = int(item['qty'])
        if qty <= 0:
            query("DELETE FROM cart_items WHERE id = %s", (cid,))
        else:
            query("UPDATE cart_items SET qty = %s WHERE id = %s", (qty, cid))
    return jsonify({'ok': True})

# ---------- checkout ----------
@app.route('/checkout', methods=['GET', 'POST'])
def checkout():
    if 'user_id' not in session:
        flash('Please log in to checkout', 'error')
        return redirect(url_for('login_register'))

    user = current_user()
    cart = get_or_create_cart(user['id'])
    items = query("""
        SELECT ci.id as cart_item_id, p.id AS product_id, p.title, ci.qty, ci.unit_price
        FROM cart_items ci
        JOIN products p ON p.id = ci.product_id
        WHERE ci.cart_id = %s
    """, (cart['id'],), fetch=True)

    if request.method == 'POST':
        line1 = request.form.get('line1')
        city = request.form.get('city')
        state = request.form.get('state')
        postal = request.form.get('postal')

        if not (line1 and city and state and postal):
            flash('Complete address required', 'error')
            return redirect(url_for('checkout'))

        addr = query("""
            INSERT INTO addresses (user_id, line1, city, state, postal_code)
            VALUES (%s,%s,%s,%s,%s) RETURNING id
        """, (user['id'], line1, city, state, postal), fetchone=True)

        total = sum((Decimal(item['qty']) * item['unit_price']) for item in items) if items else Decimal('0.00')

        order = query("""
            INSERT INTO orders (user_id, address_id, total_amount, status)
            VALUES (%s,%s,%s,%s) RETURNING id
        """, (user['id'], addr['id'], total, 'processing'), fetchone=True)

        for it in items:
            query("INSERT INTO order_items (order_id, product_id, qty, unit_price) VALUES (%s,%s,%s,%s)",
                  (order['id'], it['product_id'], it['qty'], it['unit_price']))

        query("INSERT INTO payments (order_id, paid_amount, payment_method, status, paid_at) VALUES (%s,%s,%s,%s, now())",
              (order['id'], total, 'COD', 'paid'))

        query("DELETE FROM cart_items WHERE cart_id = %s", (cart['id'],))

        return render_template('checkout.html', user=user, order_id=order['id'], success=True)

    return render_template('checkout.html', user=user, items=items)

# ---------- delivery confirm ----------
@app.route('/order/<int:order_id>/confirm', methods=['POST'])
def confirm_delivery(order_id):
    if 'user_id' not in session:
        return jsonify({'ok': False, 'error': 'login_required'}), 401

    order = query("SELECT * FROM orders WHERE id = %s AND user_id = %s", (order_id, session['user_id']), fetchone=True)
    if not order:
        return jsonify({'ok': False, 'error': 'order_not_found'}), 404

    query("UPDATE orders SET status = 'delivered', delivered_at = now() WHERE id = %s", (order_id,))
    return jsonify({'ok': True})

# ---------- API: product details ----------
@app.route('/api/product/<int:product_id>')
def api_product(product_id):
    p = query("""
      SELECT p.*, COALESCE(p.image_path,'') AS image_path, COALESCE(inv.qty,0) AS qty
      FROM products p
      LEFT JOIN inventory inv ON inv.product_id = p.id
      WHERE p.id = %s
    """, (product_id,), fetchone=True)

    if not p:
        return jsonify({'ok': False, 'error': 'not_found'}), 404
    return jsonify({'ok': True, 'product': dict(p)})

if __name__ == '__main__':
    app.run(debug=True)
