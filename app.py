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
@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_id', None)
    session.pop('admin_name', None)
    session.pop('admin_email', None)
    flash('You have logged out successfully.', 'info')
    return redirect(url_for('admin_login'))



@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        connection = get_db_connection()
        cursor = connection.cursor()

        # Kiểm tra email và mật khẩu của admin
        cursor.execute("SELECT maadmin, tenadmin, email, matkhau FROM admin WHERE email = ? AND matkhau = ? AND isdelete = 0", (email, password))
        admin = cursor.fetchone()
        connection.close()

        if admin:
            # Lưu thông tin admin vào session
            session['admin_id'] = admin[0]
            session['admin_name'] = admin[1]
            session['admin_email'] = admin[2]
            flash('Login successful!', 'success')
            return redirect(url_for('admin_dashboard'))  # Redirect to admin dashboard
        else:
            flash('Invalid credentials or account deleted.', 'danger')

    return render_template('admin_login.html')
@app.route('/admin/add-category', methods=['GET', 'POST'])
def add_category():
    if request.method == 'POST':
        category_name = request.form['category_name']
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute("INSERT INTO loaidienthoai (tenloai) VALUES (?)", category_name)
        connection.commit()
        connection.close()
        flash('Category added successfully!', 'success')
        return redirect(url_for('manage_categories'))
    return render_template('add_category.html')
@app.route('/admin/view-order/<int:order_id>', methods=['GET'])
def view_order(order_id):
    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute("SELECT * FROM donhang WHERE madonhang = ?", order_id)
    order = cursor.fetchone()

    cursor.execute("""
        SELECT c.soluong, c.dongia, p.tendienthoai
        FROM chitietdonhang c
        JOIN dienthoai p ON c.madt = p.madt
        WHERE c.madonhang = ?
    """, order_id)
    order_details = cursor.fetchall()

    connection.close()

    return render_template('view_order.html', order=order, order_details=order_details)
@app.route('/admin/dashboard')
def admin_dashboard():
    connection = get_db_connection()
    cursor = connection.cursor()
    
    # Fix: Store each total in separate variables
    cursor.execute("SELECT COUNT(*) FROM nguoidung WHERE isdelete = 0")
    total_users = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM dienthoai WHERE isdelete = 0")
    total_products = cursor.fetchone()[0]  # Fixed variable name
    
    cursor.execute("SELECT COUNT(*) FROM donhang WHERE isdelete = 0")
    total_orders = cursor.fetchone()[0]  # Fixed variable name
    
    cursor.execute("SELECT SUM(tongtien) FROM donhang WHERE isdelete = 0")
    total_revenue = cursor.fetchone()[0] or 0  # Fixed variable name and added null check
    
    # Updated query to match your schema
    cursor.execute("""
        SELECT d.madonhang, n.tennguoidung, d.tongtien, tg.tentrangthai,
        CASE 
            WHEN tg.tentrangthai = N'Chưa Giao' THEN 'warning'
            WHEN tg.tentrangthai = N'Đã Giao' THEN 'success'
            ELSE 'primary'
        END as status_color
        FROM donhang d
        JOIN nguoidung n ON d.mand = n.mand
        JOIN trangthai_giaohang tg ON d.matrangthai_giaohang = tg.matrangthai
        WHERE d.isdelete = 0
        ORDER BY d.ngaydat DESC
    """)
    recent_orders = cursor.fetchall()
    
    # Updated query to match your schema
    cursor.execute("""
        SELECT TOP 5 dt.tendienthoai, l.tenloai, 
               COUNT(ct.madt) as total_sales,
               SUM(ct.soluong * ct.dongia) as revenue
        FROM chitietdonhang ct
        JOIN dienthoai dt ON ct.madt = dt.madt
        JOIN loaidienthoai l ON dt.maloai = l.maloai
        WHERE dt.isdelete = 0
        GROUP BY dt.madt, dt.tendienthoai, l.tenloai
        ORDER BY total_sales DESC
    """)
    top_products = cursor.fetchall()
    
    # Updated query to match your schema
    cursor.execute("""
        SELECT CAST(ngaydat AS DATE) as date, COUNT(*) as count
        FROM donhang
        WHERE isdelete = 0
        GROUP BY CAST(ngaydat AS DATE)
        ORDER BY date DESC
        OFFSET 0 ROWS FETCH NEXT 7 ROWS ONLY
    """)
    orders_data = cursor.fetchall()
    
    # Updated to handle SQL Server date format
    orders_chart_data = {
        'labels': [str(row[0]) for row in orders_data],  # Convert date to string
        'datasets': [{
            'label': 'Orders',
            'data': [row[1] for row in orders_data],
            'fill': False,
            'borderColor': 'rgb(75, 192, 192)',
            'tension': 0.1
        }]
    }
    
    # Updated query to match your schema
    cursor.execute("""
        SELECT l.tenloai, COUNT(dt.madt) as count
        FROM loaidienthoai l
        LEFT JOIN dienthoai dt ON l.maloai = dt.maloai AND dt.isdelete = 0
        WHERE l.isdelete = 0
        GROUP BY l.maloai, l.tenloai
    """)
    categories_data = cursor.fetchall()
    
    categories_chart_data = {
        'labels': [row[0] for row in categories_data],
        'datasets': [{
            'data': [row[1] for row in categories_data],
            'backgroundColor': [
                '#4e73df', '#1cc88a', '#36b9cc', '#f6c23e', '#e74a3b'
            ]
        }]
    }
    
    connection.close()
    
    return render_template('admin_dashboard.html',
                         total_users=total_users,
                         total_products=total_products,
                         total_orders=total_orders,
                         total_revenue=total_revenue,
                         recent_orders=recent_orders,
                         top_products=top_products,
                         orders_chart_data=orders_chart_data,
                         categories_chart_data=categories_chart_data)
@app.route('/admin/delete-order/<int:order_id>', methods=['POST'])
def delete_order(order_id):
    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute("UPDATE donhang SET isdelete = 1 WHERE madonhang = ?", order_id)
    connection.commit()
    connection.close()
    
    flash('Order deleted successfully!', 'success')
    return redirect(url_for('manage_orders'))

@app.route('/admin/edit-category/<int:category_id>', methods=['GET', 'POST'])
def edit_category(category_id):
    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute("SELECT tenloai FROM loaidienthoai WHERE maloai = ?", category_id)
    category = cursor.fetchone()
    if request.method == 'POST':
        category_name = request.form['category_name']
        cursor.execute("UPDATE loaidienthoai SET tenloai = ? WHERE maloai = ?", category_name, category_id)
        connection.commit()
        connection.close()
        flash('Category updated successfully!', 'success')
        return redirect(url_for('manage_categories'))
    return render_template('edit_category.html', category=category)
@app.route('/admin/manage-orders', methods=['GET'])
def manage_orders():
    # Lấy danh sách các đơn hàng từ cơ sở dữ liệu
    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute("SELECT madonhang, ngaydat, tongtien, phuongthucthanhtoan, matrangthai FROM donhang WHERE isdelete = 0")
    orders = cursor.fetchall()
    connection.close()
    
    return render_template('manage_orders.html', orders=orders)

@app.route('/admin/delete-category/<int:category_id>', methods=['POST'])
def delete_category(category_id):
    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute("UPDATE loaidienthoai SET isdelete = 1 WHERE maloai = ?", category_id)
    connection.commit()
    connection.close()
    flash('Category deleted successfully!', 'success')
    return redirect(url_for('manage_categories'))

@app.route('/admin/manage-categories', methods=['GET', 'POST'])
def manage_categories():
    # Lấy danh sách các loại sản phẩm từ cơ sở dữ liệu
    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute("SELECT maloai, tenloai FROM loaidienthoai WHERE isdelete = 0")
    categories = cursor.fetchall()
    connection.close()
    
    return render_template('manage_categories.html', categories=categories)

@app.route('/admin/manage-products', methods=['GET', 'POST'])
def manage_products():
    # Kết nối cơ sở dữ liệu và lấy danh sách sản phẩm
    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute("SELECT madt, tendienthoai, gia, hinhanh FROM dienthoai WHERE isdelete = 0")
    products = cursor.fetchall()
    connection.close()
    
    return render_template('manage_products.html', products=products)

@app.route('/admin/manage_users')
def manage_users():
    # Kiểm tra nếu người dùng là admin
    if not session.get('user_id') or session.get('role') != 'admin':
        flash('You are not authorized to view this page', 'danger')
        return redirect(url_for('index'))

    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute("SELECT mand, tennguoidung, email FROM nguoidung WHERE isdelete = 0")
    users = cursor.fetchall()
    connection.close()

    return render_template('manage_users.html', users=users)

@app.route('/profile', methods=['GET', 'POST'])

def profile():
    user_id = session.get('user_id')
    if not user_id:
        flash('You need to be logged in to view your profile!', 'danger')
        return redirect(url_for('login'))  # Redirect to login if user is not logged in

    # Kết nối cơ sở dữ liệu và lấy thông tin người dùng
    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute("SELECT mand, tennguoidung, email FROM nguoidung WHERE mand = ?", user_id)
    user = cursor.fetchone()

    # Xử lý khi thay đổi mật khẩu
    if request.method == 'POST':
        old_password = request.form['old_password']
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']
        
        if not old_password or not new_password or not confirm_password:
            flash('Please fill all fields', 'danger')
        elif new_password != confirm_password:
            flash('New password and confirm password do not match', 'danger')
        else:
            cursor.execute("SELECT matkhau FROM nguoidung WHERE mand = ?", user_id)
            current_password = cursor.fetchone()[0]

            if old_password != current_password:
                flash('Old password is incorrect', 'danger')
            else:
                # Update the password
                cursor.execute("UPDATE nguoidung SET matkhau = ? WHERE mand = ?", new_password, user_id)
                connection.commit()
                flash('Password updated successfully!', 'success')

    connection.close()

    if not user:
        flash('User not found!', 'danger')
        return redirect(url_for('index'))  # Redirect to the homepage if user data is not found

    return render_template('profile.html', user=user)
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
