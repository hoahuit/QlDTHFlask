from flask import Flask, render_template, request, redirect, url_for, flash, session
import pyodbc

app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Thay 'your_secret_key' bằng chuỗi bất kỳ
# Kết nối cơ sở dữ liệu
def get_db_connection():
    connection = pyodbc.connect('DRIVER={SQL Server};SERVER=THLONE\SQLEXPRESS;DATABASE=quanlybandienthoai;Trusted_Connection=yes')
    return connection
@app.route('/checkout', methods=['GET', 'POST'])
def checkout():
    if 'cart' not in session or not session['cart']:
        return redirect(url_for('cart'))  # Redirect to cart if no items

    cart = session['cart']
    total = sum(item['price'] * item['quantity'] for item in cart)

    # Kiểm tra nếu người dùng đã đăng nhập
    user_id = session.get('user_id')
    if not user_id:
        flash('You need to be logged in to checkout!', 'danger')
        return redirect(url_for('login'))  # Redirect to login if not logged in

    if request.method == 'POST':
        # Lấy phương thức thanh toán và địa chỉ giao hàng từ form
        payment_method = request.form.get('payment_method')
        shipping_address = request.form.get('shipping_address')

        if not payment_method or not shipping_address:
            flash('Please fill in all the required fields.', 'danger')
            return redirect(url_for('checkout'))  # Redirect back to checkout if any field is missing

        # Xử lý dữ liệu thanh toán và lưu vào cơ sở dữ liệu (donhang, chitietdonhang)
        try:
            connection = get_db_connection()
            cursor = connection.cursor()

            # Thêm dữ liệu vào bảng donhang
            cursor.execute("""
                INSERT INTO donhang (mand, tongtien, diachigiaohang, matrangthai_giaohang, matrangthai_thanhtoan, phuongthucthanhtoan)
                VALUES (?, ?, ?, ?, ?, ?)
            """, user_id, total, shipping_address, 1, 1, payment_method)  # Giả sử trạng thái giao hàng và thanh toán mặc định là 1
            connection.commit()

            # Lấy ID của đơn hàng vừa thêm
            cursor.execute("SELECT @@IDENTITY AS madonhang")
            order_id = cursor.fetchone()[0]

            # Thêm các chi tiết đơn hàng vào bảng chitietdonhang
            for item in cart:
                cursor.execute("""
                    INSERT INTO chitietdonhang (madt, madonhang, soluong, dongia)
                    VALUES (?, ?, ?, ?)
                """, item['id'], order_id, item['quantity'], item['price'])
            
            connection.commit()

            # Xóa giỏ hàng sau khi thanh toán
            session.pop('cart', None)

            # Thông báo thành công
            flash('Your order has been successfully placed!', 'success')
            return redirect(url_for('order_summary', order_id=order_id))  # Chuyển hướng đến trang tóm tắt đơn hàng

        except Exception as e:
            # Xử lý lỗi nếu có
            connection.rollback()
            flash(f'An error occurred: {str(e)}', 'danger')
            return redirect(url_for('cart'))  # Nếu có lỗi, quay lại trang giỏ hàng

    return render_template('checkout.html', total=total)
@app.route('/track_order', methods=['GET'])
def track_order():
    # Lấy user_id từ session (giả sử người dùng đã đăng nhập)
    user_id = session.get('user_id')

    if not user_id:
        flash('You need to be logged in to track your orders.', 'danger')
        return redirect(url_for('login'))  # Redirect to login page if not logged in

    # Kết nối đến cơ sở dữ liệu và lấy tất cả đơn hàng của user_id
    connection = get_db_connection()
    cursor = connection.cursor()

    # Truy vấn tất cả các đơn hàng của người dùng
    cursor.execute("""
        SELECT d.madonhang, d.ngaydat, d.tongtien, dt.tentrangthai AS trangthai_thanhtoan, sg.tentrangthai AS trangthai_giaohang
        FROM donhang d
        JOIN trangthai_thanhtoan dt ON d.matrangthai_thanhtoan = dt.matrangthai
        JOIN trangthai_giaohang sg ON d.matrangthai_giaohang = sg.matrangthai
        WHERE d.mand = ?  -- Chỉ lấy các đơn hàng của người dùng hiện tại
    """, (user_id,))
    orders = cursor.fetchall()
    connection.close()

    # Nếu không có đơn hàng nào
    if not orders:
        flash('You don\'t have any orders yet.', 'info')

    # Render lại trang theo dõi đơn hàng với danh sách các đơn hàng
    return render_template('tracking.html', orders=orders)

@app.route('/order_summary/<int:order_id>')
def order_summary(order_id):
    # Lấy thông tin đơn hàng từ cơ sở dữ liệu
    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT d.madonhang, d.ngaydat, d.tongtien, d.phuongthucthanhtoan, dt.tentrangthai AS trangthai_thanhtoan
        FROM donhang d
        JOIN trangthai_thanhtoan dt ON d.matrangthai_thanhtoan = dt.matrangthai
        WHERE madonhang = ?
    """, order_id)
    order = cursor.fetchone()

    cursor.execute("""
        SELECT c.soluong, c.dongia, p.tendienthoai, p.hinhanh
        FROM chitietdonhang c
        JOIN dienthoai p ON c.madt = p.madt
        WHERE c.madonhang = ?
    """, order_id)
    order_details = cursor.fetchall()

    connection.close()

    # Kiểm tra nếu đơn hàng không tồn tại
    if order is None:
        flash('Order not found!', 'danger')
        return redirect(url_for('index'))  # Redirect về trang chính nếu đơn hàng không tồn tại

    return render_template('order_summary.html', order=order, order_details=order_details)


@app.route('/add-to-cart/<int:product_id>', methods=['POST'])
def add_to_cart(product_id):
    quantity = int(request.form.get('quantity', 1))  # Chuyển đổi số lượng sang kiểu int
    
    # Kết nối database để lấy thông tin sản phẩm
    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute("SELECT madt, tendienthoai, gia, hinhanh FROM dienthoai WHERE madt = ? AND isdelete = 0", product_id)
    product = cursor.fetchone()
    connection.close()

    if not product:
        flash('Product not found!', 'danger')
        return redirect(url_for('index'))

    if 'cart' not in session:
        session['cart'] = []

    cart = session['cart']
    for item in cart:
        if item['id'] == product_id:
            item['quantity'] += quantity
            break
    else:
        image_path = product.hinhanh if product.hinhanh else 'images/placeholder.jpg'
        if not image_path.startswith('/static/'):
            image_path = f'/static/{image_path}'
            
        cart.append({
            'id': product.madt,
            'name': product.tendienthoai,
            'price': float(product.gia),
            'quantity': quantity,
            'image': image_path
        })

    session['cart'] = cart  # Lưu lại giỏ hàng vào session
    flash('Product added to cart!', 'success')
    return redirect(url_for('cart'))

@app.route('/update-cart/<int:product_id>', methods=['POST'])
def update_cart(product_id):
    quantity = int(request.form.get('quantity', 1))
    
    if 'cart' in session:
        cart = session['cart']
        for item in cart:
            if item['id'] == product_id:
                item['quantity'] = quantity
                break
        session['cart'] = cart  # Lưu lại giỏ hàng vào session
        flash('Cart updated successfully!', 'success')
    else:
        flash('Cart is empty!', 'danger')
    
    return redirect(url_for('cart'))

# Đăng ký
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute("INSERT INTO nguoidung (tennguoidung, email, matkhau) VALUES (?, ?, ?)", username, email, password)
        connection.commit()
        connection.close()
        
        flash('Đăng ký thành công! Vui lòng đăng nhập.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

# Đăng nhập
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute("SELECT mand, tennguoidung FROM nguoidung WHERE email = ? AND matkhau = ?", email, password)
        user = cursor.fetchone()
        connection.close()
        
        if user:
            session['user_id'] = user.mand
            session['username'] = user.tennguoidung
            flash('Đăng nhập thành công!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Email hoặc mật khẩu không đúng.', 'danger')
    return render_template('login.html')

# Đăng xuất
@app.route('/logout')
def logout():
    session.pop('user_id', None)
    session.pop('username', None)
    flash('Bạn đã đăng xuất.', 'info')
    return redirect(url_for('index'))

# Route chính
@app.route('/')
def index():
    # Kết nối database và lấy danh sách loại điện thoại
    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute("SELECT maloai, tenloai FROM loaidienthoai WHERE isdelete = 0")
    categories = [{'maloai': row.maloai, 'tenloai': row.tenloai} for row in cursor.fetchall()]
    
    # Lấy toàn bộ danh sách sản phẩm
    cursor.execute("SELECT madt, tendienthoai, gia, hinhanh FROM dienthoai WHERE isdelete = 0")
    products = [{'madt': row.madt, 'tendienthoai': row.tendienthoai, 'gia': row.gia, 'hinhanh': row.hinhanh} for row in cursor.fetchall()]
    connection.close()
    
    return render_template('index.html', categories=categories, products=products)

@app.route('/category/<int:category_id>')
def category_products(category_id):
    connection = get_db_connection()
    cursor = connection.cursor()
    
    # Lấy danh sách loại sản phẩm
    cursor.execute("SELECT maloai, tenloai FROM loaidienthoai WHERE isdelete = 0")
    categories = [{'maloai': row.maloai, 'tenloai': row.tenloai} for row in cursor.fetchall()]
    
    # Lọc sản phẩm theo loại
    cursor.execute("""
        SELECT madt, tendienthoai, gia, hinhanh 
        FROM dienthoai 
        WHERE maloai = ? AND isdelete = 0
    """, category_id)
    products = [{'madt': row.madt, 'tendienthoai': row.tendienthoai, 'gia': row.gia, 'hinhanh': row.hinhanh} for row in cursor.fetchall()]
    connection.close()
    
    return render_template('category_products.html', categories=categories, products=products)

@app.route('/product/<int:id>')
def product_detail(id):
    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute("SELECT * FROM dienthoai WHERE madt = ? AND isdelete = 0", id)
    product = cursor.fetchone()
    connection.close()
    return render_template('product_detail.html', product=product)
@app.route('/remove-from-cart/<int:product_id>', methods=['POST'])
def remove_from_cart(product_id):
    cart = session.get('cart', [])
    cart = [item for item in cart if item['id'] != product_id]
    session['cart'] = cart
    flash('Product removed from cart!', 'info')
    return redirect(url_for('cart'))

@app.route('/cart')
def cart():
    cart = session.get('cart', [])
    # Đảm bảo dữ liệu đúng kiểu và tính tổng
    total = sum(float(item['price']) * int(item['quantity']) for item in cart)
    return render_template('cart.html', cart=cart, total=total)


@app.route('/order', methods=['POST'])
def order():
    # Logic xử lý đặt hàng
    return redirect('/')

if __name__ == '__main__':
    app.run(debug=True)
