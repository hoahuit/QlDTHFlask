from flask import Flask, render_template, request, redirect, url_for, flash, session
import pyodbc

app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Thay 'your_secret_key' bằng chuỗi bất kỳ
# Kết nối cơ sở dữ liệu
def get_db_connection():
    connection = pyodbc.connect('DRIVER={SQL Server};SERVER=minhhoa;DATABASE=quanlybandienthoai;UID=sa;PWD=123')
    return connection


@app.route('/checkout', methods=['GET', 'POST'])
def checkout():
    if 'cart' not in session or not session['cart']:
        return redirect(url_for('cart'))

    cart = session['cart']
    total = sum(item['price'] * item['quantity'] for item in cart)

    # Kiểm tra nếu người dùng đã đăng nhập
    user_id = session.get('user_id')
    if not user_id:
        flash('You need to be logged in to checkout!', 'danger')
        return redirect(url_for('login'))  # Redirect đến trang đăng nhập nếu chưa đăng nhập

    # Xử lý form thanh toán
    if request.method == 'POST':
        # Lấy phương thức thanh toán từ form
        payment_method = request.form.get('payment_method')  # Tiền mặt hoặc Online Banking
        address = request.form.get('shipping_address')  # Địa chỉ giao hàng

        # Kết nối cơ sở dữ liệu và thêm thông tin vào bảng donhang
        connection = get_db_connection()
        cursor = connection.cursor()

        # Giả sử người dùng đã đăng nhập và có ID
        user_id = session.get('user_id')  # Lấy ID người dùng từ session

        # Lấy ID trạng thái giao hàng "Chưa giao"
        cursor.execute("SELECT matrangthai FROM trangthai_giaohang WHERE tentrangthai = 'Chưa giao'")
        shipping_status = cursor.fetchone()
        if shipping_status is None:
            flash('Shipping status "Chưa giao" not found in database.', 'danger')
            return redirect(url_for('cart'))
        shipping_status_id = shipping_status[0]

        # Lấy ID trạng thái thanh toán (Tiền mặt hoặc Online Banking)
        cursor.execute("SELECT matrangthai FROM trangthai_thanhtoan WHERE tentrangthai = ?", payment_method)
        payment_status = cursor.fetchone()
        if payment_status is None:
            flash(f'Payment method "{payment_method}" not found in database.', 'danger')
            return redirect(url_for('cart'))
        payment_status_id = payment_status[0]

        # Tạo hóa đơn mới
        cursor.execute("""
            INSERT INTO donhang (mand, tongtien, diachigiaohang, matrangthai_giaohang, matrangthai_thanhtoan, phuongthucthanhtoan)
            VALUES (?, ?, ?, ?, ?, ?)
        """, user_id, total, address, shipping_status_id, payment_status_id, payment_method)
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

        # Thông báo cho người dùng
        flash('Your order has been successfully placed!', 'success')
        return redirect(url_for('order_summary', order_id=order_id))

    # Nếu là GET request, hiển thị trang thanh toán
    return render_template('checkout.html', total=total)

# Trang tóm tắt đơn hàng
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
        SELECT c.soluong, c.dongia, p.tendienthoai
        FROM chitietdonhang c
        JOIN dienthoai p ON c.madt = p.madt
        WHERE c.madonhang = ?
    """, order_id)
    order_details = cursor.fetchall()

    connection.close()

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
