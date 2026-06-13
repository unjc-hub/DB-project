from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory, jsonify, Response
import mysql.connector
from mysql.connector import Error
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
import os
import base64
from datetime import datetime, timedelta
import uuid
from apscheduler.schedulers.background import BackgroundScheduler

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'your-secret-key-change-in-production')

# ====================== 自定义过滤器 ======================
@app.template_filter('ntype')
def notification_type_filter(t):
    return {'reservation_confirmed':'预约确认','reservation_available':'到书通知',
            'overdue_reminder':'逾期提醒','fine_notice':'罚款通知',
            'reservation_expired':'预约过期','system_notice':'系统公告',
            'borrow':'借阅','renew':'续借'}.get(t, t)

@app.template_filter('cstatus')
def copy_status_filter(s):
    return {'available':'可借','borrowed':'借出','damaged':'损坏','lost':'丢失'}.get(s, s)

@app.template_filter('rstatus')
def reservation_status_filter(s):
    return {'pending':'排队中','notified':'已通知','expired':'已过期','cancelled':'已取消'}.get(s, s)

@app.template_filter('npayload')
def notification_payload_filter(p):
    try:
        import json
        d = json.loads(p) if isinstance(p, str) else p
        parts = []
        if 'title' in d: parts.append(f"《{d['title']}》")
        if 'barcode' in d: parts.append(f"条码{d['barcode']}")
        if 'due' in d: parts.append(f"应还{d['due']}")
        if 'amount' in d: parts.append(f"¥{d['amount']}")
        if 'days' in d: parts.append(f"逾期{d['days']}天")
        if 'position' in d: parts.append(f"排队第{d['position']}位")
        return '，'.join(parts) if parts else p
    except:
        return p

# 头像上传目录
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads', 'avatars')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024  # 最大2MB
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

db_config = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'user': os.getenv('DB_USER', 'root'),
    'password': os.getenv('DB_PASSWORD', ''),
    'database': os.getenv('DB_NAME', 'library_db')
}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_db_connection():
    try:
        conn = mysql.connector.connect(**db_config)
        return conn
    except Error as e:
        print(f"Database error: {e}")
        return None

def admin_required(f):
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'admin':
            flash('请以管理员身份登录')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

def superadmin_required(f):
    """仅超级管理员可访问（学生管理等）"""
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'admin':
            flash('请以管理员身份登录')
            return redirect(url_for('login'))
        if session.get('admin_role') != 'superadmin':
            flash('权限不足，仅管理员可操作')
            return redirect(url_for('admin_dashboard'))
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

def get_librarian_branch():
    """获取分馆长的分管馆，超管返回 None 表示全部"""
    if session.get('admin_role') == 'superadmin':
        return None
    return session.get('branch')

def branch_filter(table_alias='c'):
    """返回 SQL WHERE 条件，限制分馆长只能看分管馆的数据"""
    branch = get_librarian_branch()
    if branch:
        return f" AND {table_alias}.branch = %s", [branch]
    return "", []

# ====================== 公共路由 ======================
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        conn = get_db_connection()
        if not conn:
            flash('数据库连接失败')
            return redirect(url_for('login'))

        cursor = conn.cursor(dictionary=True)

        # 自动识别：先查管理员，再查学生
        cursor.execute("SELECT * FROM admins WHERE username = %s", (username,))
        user = cursor.fetchone()
        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = 'admin'
            session['admin_role'] = user['role']
            session['name'] = user['name']
            session['avatar'] = user.get('avatar')
            session['branch'] = user.get('branch')
            cursor.close()
            conn.close()
            return redirect(url_for('admin_dashboard'))

        cursor.execute("SELECT * FROM students WHERE student_no = %s", (username,))
        user = cursor.fetchone()
        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            session['username'] = user['student_no']
            session['role'] = 'student'
            session['name'] = user['name']
            session['avatar'] = user.get('avatar')
            cursor.close()
            conn.close()
            return redirect(url_for('dashboard'))

        flash('用户名或密码错误')
        cursor.close()
        conn.close()
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

# ====================== 头像服务 ======================
@app.route('/uploads/avatars/<filename>')
def uploaded_avatar(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/upload_avatar', methods=['POST'])
def upload_avatar():
    if 'user_id' not in session:
        return jsonify({'ok': False, 'error': '请先登录'}), 401

    try:
        # JSON base64 方式
        ct = request.content_type or ''
        if 'application/json' in ct or request.get_data(as_text=True).startswith('{'):
            data = request.get_json(force=True, silent=True) or {}
            image_b64 = data.get('image', '')
            if not image_b64:
                return jsonify({'ok': False, 'error': '无效的图片数据'}), 400

            # 解析 data:image/png;base64,xxxx 格式
            if ',' in image_b64:
                _, encoded = image_b64.split(',', 1)
            else:
                encoded = image_b64
            img_data = base64.b64decode(encoded)

            filename = f"{uuid.uuid4().hex}.png"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            with open(filepath, 'wb') as f:
                f.write(img_data)

            conn = get_db_connection()
            cursor = conn.cursor()
            avatar_url = f"/uploads/avatars/{filename}"
            if session.get('role') == 'student':
                cursor.execute("UPDATE students SET avatar = %s WHERE id = %s", (avatar_url, session['user_id']))
            else:
                cursor.execute("UPDATE admins SET avatar = %s WHERE id = %s", (avatar_url, session['user_id']))
            conn.commit()
            cursor.close()
            conn.close()
            session['avatar'] = avatar_url
            return jsonify({'ok': True, 'url': avatar_url})

        # 传统 file upload
        if 'avatar' not in request.files:
            return jsonify({'ok': False, 'error': '未选择文件'}), 400

        file = request.files['avatar']
        if not file or file.filename == '':
            return jsonify({'ok': False, 'error': '未选择文件'}), 400

        filename = f"{uuid.uuid4().hex}.png"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        conn = get_db_connection()
        cursor = conn.cursor()
        avatar_url = f"/uploads/avatars/{filename}"
        if session.get('role') == 'student':
            cursor.execute("UPDATE students SET avatar = %s WHERE id = %s", (avatar_url, session['user_id']))
        else:
            cursor.execute("UPDATE admins SET avatar = %s WHERE id = %s", (avatar_url, session['user_id']))
        conn.commit()
        cursor.close()
        conn.close()
        session['avatar'] = avatar_url
        return jsonify({'ok': True, 'url': avatar_url})

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'ok': False, 'error': str(e)}), 500

# ====================== 个人信息 ======================
@app.route('/profile', methods=['GET', 'POST'])
def profile():
    if 'user_id' not in session:
        flash('请先登录')
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    if request.method == 'POST':
        action = request.form.get('action', 'info')
        
        # 修改密码
        if action == 'password':
            old_pw = request.form.get('old_password', '')
            new_pw = request.form.get('new_password', '')
            confirm_pw = request.form.get('confirm_password', '')
            
            if not old_pw or not new_pw or not confirm_pw:
                flash('请填写所有密码字段')
                return redirect(url_for('profile'))
            if len(new_pw) < 6:
                flash('新密码至少6位')
                return redirect(url_for('profile'))
            if new_pw != confirm_pw:
                flash('两次新密码不一致')
                return redirect(url_for('profile'))
            
            try:
                if session.get('role') == 'student':
                    cursor.execute("SELECT password_hash FROM students WHERE id=%s", (session['user_id'],))
                else:
                    cursor.execute("SELECT password_hash FROM admins WHERE id=%s", (session['user_id'],))
                row = cursor.fetchone()
                if not row or not check_password_hash(row['password_hash'], old_pw):
                    flash('当前密码错误')
                    return redirect(url_for('profile'))
                
                new_hash = generate_password_hash(new_pw)
                if session.get('role') == 'student':
                    cursor.execute("UPDATE students SET password_hash=%s WHERE id=%s", (new_hash, session['user_id']))
                else:
                    cursor.execute("UPDATE admins SET password_hash=%s WHERE id=%s", (new_hash, session['user_id']))
                conn.commit()
                flash('密码修改成功')
            except Exception as e:
                conn.rollback()
                flash(f'修改失败: {str(e)}')
            finally:
                cursor.close()
                conn.close()
            return redirect(url_for('profile'))
        
        # 修改联系信息
        email = request.form.get('email', '').strip()
        phone = request.form.get('phone', '').strip()
        
        try:
            if session.get('role') == 'student':
                cursor.execute("UPDATE students SET email=%s, phone=%s WHERE id=%s",
                             (email, phone, session['user_id']))
            else:
                cursor.execute("UPDATE admins SET email=%s, phone=%s WHERE id=%s",
                             (email, phone, session['user_id']))
            conn.commit()
            flash('个人信息更新成功')
        except Exception as e:
            conn.rollback()
            flash(f'更新失败: {str(e)}')
        finally:
            cursor.close()
            conn.close()
        return redirect(url_for('profile'))
    
    if session.get('role') == 'student':
        cursor.execute("""
            SELECT s.*,
                   (SELECT COUNT(*) FROM borrows WHERE student_id = s.id) as total_borrows,
                   (SELECT COUNT(*) FROM borrows WHERE student_id = s.id AND return_date IS NULL) as current_borrows,
                   (SELECT COALESCE(SUM(amount), 0) FROM fines WHERE student_id = s.id AND paid = FALSE) as unpaid_fines
            FROM students s WHERE s.id = %s
        """, (session['user_id'],))
        user = cursor.fetchone()
        if user:
            max_limit = user.get('max_borrow_limit') or 30
            curr_borrows = user.get('current_borrows') or 0
            user['available_borrows'] = max(0, max_limit - curr_borrows)
            # 兼容数据库未迁移的情况
            user.setdefault('max_borrow_limit', 30)
            user.setdefault('enrollment_date', None)
            user.setdefault('graduation_date', None)
            user.setdefault('total_borrows', user.get('total_borrows') or 0)
            user.setdefault('unpaid_fines', user.get('unpaid_fines') or 0.0)
            user.setdefault('email', user.get('email') or '')
            user.setdefault('phone', user.get('phone') or '')
    else:
        cursor.execute("""
            SELECT a.*,
                   (SELECT COUNT(*) FROM audit_logs WHERE actor_id = a.id AND actor_type = 'admin') as total_actions
            FROM admins a WHERE a.id = %s
        """, (session['user_id'],))
        user = cursor.fetchone()
    
    cursor.close()
    conn.close()
    
    if not user:
        flash('用户不存在')
        return redirect(url_for('logout'))
    
    return render_template('profile.html', user=user)

# ====================== 学生路由 ======================
@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session or session.get('role') != 'student':
        flash('请先登录')
        return redirect(url_for('login'))
    return render_template('dashboard.html', name=session.get('name'))

@app.route('/my_borrows')
def my_borrows():
    if 'user_id' not in session or session.get('role') != 'student':
        flash('请先登录')
        return redirect(url_for('login'))
    
    student_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT bo.*, c.barcode, b.title, b.isbn 
        FROM borrows bo
        JOIN copies c ON bo.copy_id = c.id
        JOIN books b ON c.book_id = b.id
        WHERE bo.student_id = %s AND bo.return_date IS NULL
        ORDER BY bo.due_date
    """, (student_id,))
    borrows = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('my_borrows.html', borrows=borrows, now=datetime.now().date())

@app.route('/my_reservations')
def my_reservations():
    if 'user_id' not in session or session.get('role') != 'student':
        flash('请先登录')
        return redirect(url_for('login'))
    
    student_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT r.*, b.title, b.isbn 
        FROM reservations r
        JOIN books b ON r.book_id = b.id
        WHERE r.student_id = %s AND r.status = 'pending'
        ORDER BY r.queue_position
    """, (student_id,))
    reservations = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('my_reservations.html', reservations=reservations)

@app.route('/my_notifications')
def my_notifications():
    if 'user_id' not in session or session.get('role') != 'student':
        flash('请先登录')
        return redirect(url_for('login'))
    
    student_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT * FROM notifications 
        WHERE student_id = %s 
        ORDER BY created_at DESC
    """, (student_id,))
    notifications = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('my_notifications.html', notifications=notifications)

# ====================== 搜索与高级筛选 ======================
@app.route('/books', methods=['GET'])
def books():
    if 'user_id' not in session:
        flash('请先登录')
        return redirect(url_for('login'))
    
    query = request.args.get('q', '').strip()
    category_id = request.args.get('category_id')
    only_available = request.args.get('available') == '1'
    min_year = request.args.get('min_year')
    max_year = request.args.get('max_year')
    publisher = request.args.get('publisher')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    sql = """
        SELECT b.*, p.name as publisher_name,
               GROUP_CONCAT(DISTINCT a.name SEPARATOR ', ') as authors,
               (SELECT COUNT(*) FROM copies c WHERE c.book_id = b.id AND c.status = 'available') as available_count
        FROM books b 
        LEFT JOIN publishers p ON b.publisher_id = p.id
        LEFT JOIN book_authors ba ON b.id = ba.book_id
        LEFT JOIN authors a ON ba.author_id = a.id
        LEFT JOIN book_categories bc ON b.id = bc.book_id
    """
    where_clauses = []
    params = []

    if query:
        where_clauses.append("(b.title LIKE %s OR b.isbn LIKE %s OR a.name LIKE %s OR p.name LIKE %s)")
        params.extend([f'%{query}%'] * 4)
    
    if category_id:
        where_clauses.append("bc.category_id = %s")
        params.append(category_id)
    
    if only_available:
        where_clauses.append("EXISTS (SELECT 1 FROM copies c WHERE c.book_id = b.id AND c.status = 'available')")
    
    if min_year:
        where_clauses.append("b.publish_year >= %s")
        params.append(min_year)
    if max_year:
        where_clauses.append("b.publish_year <= %s")
        params.append(max_year)
    
    if publisher:
        where_clauses.append("p.name LIKE %s")
        params.append(f'%{publisher}%')
    
    if where_clauses:
        sql += " WHERE " + " AND ".join(where_clauses)
    
    sql += " GROUP BY b.id ORDER BY b.title LIMIT 50"
    
    if where_clauses:
        cursor.execute(sql, params)
        book_list = cursor.fetchall()
    else:
        book_list = []
    
    cursor.execute("SELECT * FROM categories ORDER BY name")
    categories = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    searched = bool(where_clauses)
    
    return render_template('books.html', 
                         books=book_list, 
                         search_query=query,
                         categories=categories,
                         selected_category=category_id,
                         only_available=only_available,
                         min_year=min_year,
                         max_year=max_year,
                         publisher=publisher,
                         searched=searched)

# ====================== 借阅功能（使用存储过程） ======================
@app.route('/borrow/<int:copy_id>', methods=['POST'])
def borrow(copy_id):
    if 'user_id' not in session or session.get('role') != 'student':
        flash('请先登录')
        return redirect(url_for('login'))
    
    student_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        conn.start_transaction()
        cursor.execute("SELECT status FROM students WHERE id=%s", (student_id,))
        if cursor.fetchone()['status'] == 'suspended':
            flash('账号已被暂停借阅'); raise Exception()
        cursor.execute("SELECT COUNT(*) as c FROM borrows WHERE student_id=%s AND return_date IS NULL", (student_id,))
        if cursor.fetchone()['c'] >= 30:
            flash('已达到借阅上限30册'); raise Exception()
        cursor.execute("SELECT COALESCE(SUM(amount),0) as t FROM fines WHERE student_id=%s AND paid=FALSE", (student_id,))
        if cursor.fetchone()['t'] >= 50:
            flash('有未缴罚款，请先缴纳'); raise Exception()
        cursor.execute("SELECT status, version FROM copies WHERE id=%s FOR UPDATE", (copy_id,))
        cp = cursor.fetchone()
        if not cp or cp['status'] != 'available':
            flash('该图书当前不可借阅'); raise Exception()
        
        # 检查该书是否有排队预约——有预约则优先留给队首
        cursor.execute("SELECT book_id FROM copies WHERE id=%s", (copy_id,))
        book_id = cursor.fetchone()['book_id']
        cursor.execute("""
            SELECT student_id FROM reservations 
            WHERE book_id=%s AND status IN ('pending','notified')
            ORDER BY queue_position LIMIT 1
        """, (book_id,))
        queue_first = cursor.fetchone()
        if queue_first and queue_first['student_id'] != student_id:
            flash('该图书已被他人预约排队，暂不可借阅'); raise Exception()
        due = datetime.now().date() + timedelta(days=30)
        cursor.execute("INSERT INTO borrows (copy_id,student_id,due_date) VALUES (%s,%s,%s)", (copy_id, student_id, due))
        cursor.execute("UPDATE copies SET status='borrowed',version=version+1 WHERE id=%s AND version=%s",
                      (copy_id, cp['version']))
        if cursor.rowcount == 0:
            flash('该图书已被他人借走，请重试'); raise Exception()
        cursor.execute("INSERT INTO audit_logs (actor_id,actor_type,action,details) VALUES (%s,'student','borrow',%s)",
                      (student_id, f'{{"copy_id":{copy_id}}}'))
        cursor.execute("SELECT b.title, c.barcode FROM copies c JOIN books b ON c.book_id=b.id WHERE c.id=%s", (copy_id,))
        info = cursor.fetchone()
        cursor.execute("INSERT INTO notifications (student_id,type,payload) VALUES (%s,'borrow',%s)",
                      (student_id, '{\"title\":\"' + info['title'] + '\",\"barcode\":\"' + info['barcode'] + '\",\"due\":\"' + str(due) + '\"}'))
        conn.commit()
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'ok': True})
        flash('_popup:借阅成功')
        return redirect(url_for('books'))
    except Exception:
        conn.rollback()
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'ok': False, 'error': '借阅失败'})
        flash('借阅失败')
    finally:
        cursor.close()
        conn.close()
    return redirect(url_for('books'))

# ====================== 续借功能 ======================
@app.route('/renew/<int:borrow_id>', methods=['POST'])
def renew(borrow_id):
    if 'user_id' not in session or session.get('role') != 'student':
        return jsonify({'ok': False, 'error': '请先登录'})
    
    student_id = session['user_id']
    conn = get_db_connection()
    if not conn:
        return jsonify({'ok': False, 'error': '数据库连接失败'})
    
    cursor = conn.cursor(dictionary=True)
    
    try:
        conn.start_transaction()
        
        # 1. 验证借阅记录
        cursor.execute("""
            SELECT bo.*, c.book_id
            FROM borrows bo JOIN copies c ON bo.copy_id = c.id
            WHERE bo.id = %s AND bo.student_id = %s AND bo.return_date IS NULL
            FOR UPDATE
        """, (borrow_id, student_id))
        borrow = cursor.fetchone()
        if not borrow:
            conn.rollback()
            return jsonify({'ok': False, 'error': '借阅记录不存在或已归还'})
        
        # 2. 统计已有续借次数
        cursor.execute("""
            SELECT COUNT(*) as cnt FROM audit_logs 
            WHERE actor_id = %s AND action = 'renew' 
            AND CAST(JSON_EXTRACT(details, '$.borrow_id') AS UNSIGNED) = %s
        """, (student_id, borrow_id))
        renew_count = cursor.fetchone()['cnt']
        if renew_count >= 2:
            conn.rollback()
            return jsonify({'ok': False, 'error': '已达到续借次数上限（2次）'})
        
        # 3. 检查预约冲突
        cursor.execute("SELECT COUNT(*) as cnt FROM reservations WHERE book_id = %s AND status = 'pending'", (borrow['book_id'],))
        if cursor.fetchone()['cnt'] > 0:
            conn.rollback()
            return jsonify({'ok': False, 'error': '该图书已有他人预约，无法续借'})
        
        # 4. 执行续借——基于当前到期日延长30天
        new_due = borrow['due_date'] + timedelta(days=30)
        cursor.execute("UPDATE borrows SET due_date = %s WHERE id = %s", (new_due, borrow_id))
        
        # 5. 记录日志
        cursor.execute("INSERT INTO audit_logs (actor_id, actor_type, action, details) VALUES (%s, 'student', 'renew', %s)",
                      (student_id, f'{{"borrow_id": {borrow_id}, "new_due": "{new_due}"}}'))
        
        cursor.execute("INSERT INTO notifications (student_id,type,payload) VALUES (%s,'renew',%s)",
                      (student_id, f'{{"borrow_id":{borrow_id}}}'))
        
        conn.commit()
        return jsonify({'ok': True, 'new_due': str(new_due)})
        
    except Exception as e:
        conn.rollback()
        return jsonify({'ok': False, 'error': '续借失败'})
    finally:
        cursor.close()
        conn.close()

# ====================== 借阅历史 ======================
@app.route('/my_history')
def my_history():
    if 'user_id' not in session or session.get('role') != 'student':
        flash('请先登录')
        return redirect(url_for('login'))
    
    student_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("""
        SELECT bo.*, c.barcode, b.title, b.isbn,
               (SELECT amount FROM fines WHERE borrow_id = bo.id LIMIT 1) as fine_amount
        FROM borrows bo
        JOIN copies c ON bo.copy_id = c.id
        JOIN books b ON c.book_id = b.id
        WHERE bo.student_id = %s AND bo.return_date IS NOT NULL
        ORDER BY bo.return_date DESC
        LIMIT 50
    """, (student_id,))
    history = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('my_history.html', history=history)

# ====================== 预约功能 ======================
@app.route('/reserve/<int:book_id>', methods=['POST'])
def reserve(book_id):
    if 'user_id' not in session or session.get('role') != 'student':
        flash('请先登录')
        return redirect(url_for('login'))
    
    student_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        conn.start_transaction()
        
        cursor.execute("SELECT MAX(queue_position) as max_pos FROM reservations WHERE book_id = %s AND status = 'pending'", (book_id,))
        result = cursor.fetchone()
        next_pos = (result['max_pos'] or 0) + 1
        
        cursor.execute("""
            INSERT INTO reservations (book_id, student_id, queue_position)
            VALUES (%s, %s, %s)
        """, (book_id, student_id, next_pos))
        
        cursor.execute("""
            INSERT INTO notifications (student_id, type, payload)
            VALUES (%s, 'reservation_confirmed', %s)
        """, (student_id, f'{{"book_id": {book_id}, "position": {next_pos}}}'))
        
        conn.commit()
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'ok': True, 'position': next_pos})
        flash('_popup:预约成功')
    except Exception:
        conn.rollback()
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'ok': False, 'error': '预约失败'})
    finally:
        cursor.close()
        conn.close()
    
    return redirect(url_for('my_reservations'))

@app.route('/cancel_reservation/<int:res_id>', methods=['POST'])
def cancel_reservation(res_id):
    if 'user_id' not in session or session.get('role') != 'student':
        flash('权限不足')
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE reservations SET status = 'cancelled' WHERE id = %s AND student_id = %s", 
                      (res_id, session['user_id']))
        conn.commit()
        flash('预约已取消')
    except Exception:
        conn.rollback()
    finally:
        cursor.close()
        conn.close()
    return redirect(url_for('my_reservations'))

# ====================== 管理员路由 ======================
@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # 图书总数
    cursor.execute("SELECT COUNT(*) as cnt FROM books")
    total_books = cursor.fetchone()['cnt']
    
    # 在馆册数
    cursor.execute("SELECT COUNT(*) as cnt FROM copies WHERE status = 'available'")
    available_count = cursor.fetchone()['cnt']
    
    # 借出中
    cursor.execute("SELECT COUNT(*) as cnt FROM borrows WHERE return_date IS NULL")
    borrowed_count = cursor.fetchone()['cnt']
    
    # 逾期数
    cursor.execute("SELECT COUNT(*) as cnt FROM borrows WHERE return_date IS NULL AND due_date < CURDATE()")
    overdue_count = cursor.fetchone()['cnt']
    
    # 待处理预约
    cursor.execute("SELECT COUNT(*) as cnt FROM reservations WHERE status = 'pending'")
    pending_reservations = cursor.fetchone()['cnt']
    
    # 未缴罚款总额
    cursor.execute("SELECT COALESCE(SUM(amount), 0) as total FROM fines WHERE paid = FALSE")
    total_fines = cursor.fetchone()['total']
    
    cursor.close()
    conn.close()
    
    return render_template('admin_dashboard.html', 
                         name=session.get('name'),
                         total_books=total_books,
                         available_count=available_count,
                         borrowed_count=borrowed_count,
                         overdue_count=overdue_count,
                         pending_reservations=pending_reservations,
                         total_fines=total_fines)

@app.route('/admin/return/<int:borrow_id>', methods=['POST'])
@admin_required
def return_book(borrow_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        conn.start_transaction()
        cursor.execute("""
            SELECT bo.*, c.id as copy_id, c.book_id, c.version as copy_version,
                   DATEDIFF(CURDATE(), bo.due_date) as overdue_days,
                   b.title as book_title
            FROM borrows bo JOIN copies c ON bo.copy_id = c.id
            JOIN books b ON c.book_id = b.id
            WHERE bo.id = %s AND bo.return_date IS NULL
        """, (borrow_id,))
        borrow = cursor.fetchone()
        
        if not borrow:
            flash('记录不存在或已归还')
            raise Exception()
        
        overdue_days = max(0, borrow.get('overdue_days', 0))
        fine_amount = float(overdue_days) * 0.01
        
        cursor.execute("UPDATE borrows SET return_date = CURDATE() WHERE id = %s", (borrow_id,))
        cursor.execute("UPDATE copies SET status = 'available', version = version + 1 WHERE id = %s AND version = %s",
                      (borrow['copy_id'], borrow['copy_version']))
        if cursor.rowcount == 0:
            flash('该副本状态已被修改，请重试'); raise Exception()
        
        if fine_amount > 0:
            cursor.execute("INSERT INTO fines (borrow_id, student_id, amount) VALUES (%s, %s, %s)",
                          (borrow_id, borrow['student_id'], fine_amount))
            cursor.execute("INSERT INTO notifications (student_id, type, payload) VALUES (%s, 'fine_notice', %s)",
                          (borrow['student_id'], '{"title":"' + borrow['book_title'] + '","amount":' + str(fine_amount) + '}'))
        
        # 自动分配预约
        cursor.execute("""
            SELECT r.*, s.name as student_name
            FROM reservations r JOIN students s ON r.student_id = s.id
            WHERE r.book_id = %s AND r.status = 'pending'
            ORDER BY r.queue_position ASC LIMIT 1
        """, (borrow['book_id'],))
        next_res = cursor.fetchone()
        
        if next_res:
            expire_at = datetime.now() + timedelta(days=3)
            cursor.execute("UPDATE reservations SET status = 'notified', notified_at = NOW(), expire_at = %s WHERE id = %s",
                          (expire_at, next_res['id']))
            cursor.execute("INSERT INTO notifications (student_id, type, payload) VALUES (%s, 'reservation_available', %s)",
                          (next_res['student_id'], '{"title":"' + borrow['book_title'] + '","expire_at":"' + str(expire_at)[:19] + '"}'))
        
        cursor.execute("INSERT INTO audit_logs (actor_id, actor_type, action, details) VALUES (%s, 'admin', 'return', %s)",
                      (session['user_id'], f'{{"borrow_id": {borrow_id}, "fine": {fine_amount}}}'))
        
        conn.commit()
        msg = '归还成功'
        if fine_amount > 0: msg += f'，逾期罚款 ¥{fine_amount:.2f}'
        if next_res: msg += f'，已通知预约者 {next_res["student_name"]}'
        flash(msg)
    except Exception:
        conn.rollback()
        flash('操作失败')
    finally:
        cursor.close()
        conn.close()
    return redirect(url_for('admin_borrows'))

@app.route('/admin/borrows')
@admin_required
def admin_borrows():
    filter_type = request.args.get('filter', '')
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    branch = get_librarian_branch()
    
    if filter_type == 'overdue':
        where_extra = "AND bo.due_date < CURDATE()"
        params = (branch,) if branch else None
    else:
        where_extra = ""
        params = (branch,) if branch else None
    
    if branch:
        cursor.execute(f"""
            SELECT bo.*, b.title, s.name as student_name, c.barcode
            FROM borrows bo
            JOIN copies c ON bo.copy_id = c.id
            JOIN books b ON c.book_id = b.id
            JOIN students s ON bo.student_id = s.id
            WHERE bo.return_date IS NULL AND c.branch = %s {where_extra}
            ORDER BY bo.due_date
        """, (branch,))
    else:
        cursor.execute(f"""
            SELECT bo.*, b.title, s.name as student_name, c.barcode
            FROM borrows bo
            JOIN copies c ON bo.copy_id = c.id
            JOIN books b ON c.book_id = b.id
            JOIN students s ON bo.student_id = s.id
            WHERE bo.return_date IS NULL {where_extra}
            ORDER BY bo.due_date
        """)
    borrows = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('admin_borrows.html', borrows=borrows, now=datetime.now().date())

# 预约管理后台
@app.route('/admin/reservations')
@admin_required
def admin_reservations():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    branch = get_librarian_branch()
    if branch:
        cursor.execute("""
            SELECT r.*, b.title, s.name as student_name 
            FROM reservations r
            JOIN books b ON r.book_id = b.id
            JOIN students s ON r.student_id = s.id
            WHERE EXISTS (SELECT 1 FROM copies c WHERE c.book_id = r.book_id AND c.branch = %s)
            ORDER BY r.created_at DESC
        """, (branch,))
    else:
        cursor.execute("""
            SELECT r.*, b.title, s.name as student_name 
            FROM reservations r
            JOIN books b ON r.book_id = b.id
            JOIN students s ON r.student_id = s.id
            ORDER BY r.created_at DESC
        """)
    reservations = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('admin_reservations.html', reservations=reservations)

# 通知中心（管理员查看）
@app.route('/admin/notifications')
@admin_required
def admin_notifications():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT n.*, s.name as student_name 
        FROM notifications n
        JOIN students s ON n.student_id = s.id
        ORDER BY n.created_at DESC
    """)
    notifications = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('admin_notifications.html', notifications=notifications)

# ====================== 图书管理 ======================
@app.route('/admin/books')
@admin_required
def admin_books():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT b.*, p.name as publisher_name,
               GROUP_CONCAT(DISTINCT a.name SEPARATOR ', ') as authors,
               (SELECT COUNT(*) FROM copies c WHERE c.book_id = b.id) as copy_count,
               (SELECT COUNT(*) FROM copies c WHERE c.book_id = b.id AND c.status = 'available') as avail_count
        FROM books b
        LEFT JOIN publishers p ON b.publisher_id = p.id
        LEFT JOIN book_authors ba ON b.id = ba.book_id
        LEFT JOIN authors a ON ba.author_id = a.id
        GROUP BY b.id
        ORDER BY b.id DESC
    """)
    books = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('admin_books.html', books=books)

@app.route('/admin/books/add', methods=['GET', 'POST'])
@superadmin_required
def admin_book_add():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    if request.method == 'POST':
        isbn = request.form.get('isbn', '').strip()
        title = request.form.get('title', '').strip()
        publisher_id = request.form.get('publisher_id') or None
        description = request.form.get('description', '').strip()
        publish_year = request.form.get('publish_year') or None
        authors_input = request.form.get('authors_input', '').strip()
        author_names = [a.strip() for a in authors_input.split(',') if a.strip()]
        category_ids = request.form.getlist('category_ids')
        
        try:
            conn.start_transaction()
            cursor.execute("""
                INSERT INTO books (isbn, title, publisher_id, description, publish_year)
                VALUES (%s, %s, %s, %s, %s)
            """, (isbn, title, publisher_id, description, publish_year))
            book_id = cursor.lastrowid
            
            for name in author_names:
                cursor.execute("SELECT id FROM authors WHERE name=%s", (name,))
                row = cursor.fetchone()
                if row:
                    author_id = row['id']
                else:
                    cursor.execute("INSERT INTO authors (name) VALUES (%s)", (name,))
                    author_id = cursor.lastrowid
                cursor.execute("INSERT INTO book_authors (book_id, author_id) VALUES (%s, %s)", (book_id, author_id))
            for cid in category_ids:
                cursor.execute("INSERT INTO book_categories (book_id, category_id) VALUES (%s, %s)", (book_id, cid))
            
            cursor.execute("""
                INSERT INTO audit_logs (actor_id, actor_type, action, details)
                VALUES (%s, 'admin', 'add_book', %s)
            """, (session['user_id'], f'{{"book_id": {book_id}, "title": "{title}"}}'))
            
            conn.commit()
            flash('图书添加成功')
            cursor.close()
            conn.close()
            return redirect(url_for('admin_books'))
        except Exception as e:
            conn.rollback()
            flash(f'添加失败: {str(e)}')
    
    cursor.execute("SELECT * FROM authors ORDER BY name")
    authors = cursor.fetchall()
    cursor.execute("SELECT * FROM categories ORDER BY name")
    categories = cursor.fetchall()
    cursor.execute("SELECT * FROM publishers ORDER BY name")
    publishers = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('admin_book_form.html', authors=authors, categories=categories, publishers=publishers, edit=False)

@app.route('/admin/books/edit/<int:book_id>', methods=['GET', 'POST'])
@superadmin_required
def admin_book_edit(book_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    if request.method == 'POST':
        isbn = request.form.get('isbn', '').strip()
        title = request.form.get('title', '').strip()
        publisher_id = request.form.get('publisher_id') or None
        description = request.form.get('description', '').strip()
        publish_year = request.form.get('publish_year') or None
        
        # 处理文本作者输入
        authors_input = request.form.get('authors_input', '').strip()
        author_names = [a.strip() for a in authors_input.split(',') if a.strip()]
        category_ids = request.form.getlist('category_ids')
        
        try:
            conn.start_transaction()
            cursor.execute("""
                UPDATE books SET isbn=%s, title=%s, publisher_id=%s, description=%s, publish_year=%s
                WHERE id=%s
            """, (isbn, title, publisher_id, description, publish_year, book_id))
            
            cursor.execute("DELETE FROM book_authors WHERE book_id=%s", (book_id,))
            cursor.execute("DELETE FROM book_categories WHERE book_id=%s", (book_id,))
            for name in author_names:
                cursor.execute("SELECT id FROM authors WHERE name=%s", (name,))
                row = cursor.fetchone()
                if row:
                    author_id = row['id']
                else:
                    cursor.execute("INSERT INTO authors (name) VALUES (%s)", (name,))
                    author_id = cursor.lastrowid
                cursor.execute("INSERT INTO book_authors (book_id, author_id) VALUES (%s, %s)", (book_id, author_id))
            for cid in category_ids:
                cursor.execute("INSERT INTO book_categories (book_id, category_id) VALUES (%s, %s)", (book_id, cid))
            
            conn.commit()
            flash('图书更新成功')
            cursor.close()
            conn.close()
            return redirect(url_for('admin_books'))
        except Exception as e:
            conn.rollback()
            flash(f'更新失败: {str(e)}')
    
    cursor.execute("SELECT * FROM books WHERE id=%s", (book_id,))
    book = cursor.fetchone()
    if not book:
        flash('图书不存在')
        return redirect(url_for('admin_books'))
    
    cursor.execute("SELECT author_id FROM book_authors WHERE book_id=%s", (book_id,))
    book['author_ids'] = [r['author_id'] for r in cursor.fetchall()]
    cursor.execute("SELECT name FROM authors WHERE id IN (SELECT author_id FROM book_authors WHERE book_id=%s)", (book_id,))
    book['authors_str'] = ', '.join([r['name'] for r in cursor.fetchall()])
    cursor.execute("SELECT category_id FROM book_categories WHERE book_id=%s", (book_id,))
    book['category_ids'] = [r['category_id'] for r in cursor.fetchall()]
    
    cursor.execute("SELECT * FROM authors ORDER BY name")
    authors = cursor.fetchall()
    cursor.execute("SELECT * FROM categories ORDER BY name")
    categories = cursor.fetchall()
    cursor.execute("SELECT * FROM publishers ORDER BY name")
    publishers = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('admin_book_form.html', book=book, authors=authors, categories=categories, publishers=publishers, edit=True)

@app.route('/admin/books/delete/<int:book_id>', methods=['POST'])
@superadmin_required
def admin_book_delete(book_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM books WHERE id=%s", (book_id,))
        conn.commit()
        flash('图书已删除')
    except Exception as e:
        conn.rollback()
        flash(f'删除失败: {str(e)}')
    finally:
        cursor.close()
        conn.close()
    return redirect(url_for('admin_books'))

# ====================== 学生管理 ======================
@app.route('/admin/students')
@superadmin_required
def admin_students():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT s.*,
               (SELECT COUNT(*) FROM borrows WHERE student_id = s.id AND return_date IS NULL) as current_borrows,
               (SELECT COALESCE(SUM(amount), 0) FROM fines WHERE student_id = s.id AND paid = FALSE) as unpaid_fines
        FROM students s
        ORDER BY s.id
    """)
    students = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('admin_students.html', students=students)

@app.route('/admin/students/edit/<int:student_id>', methods=['GET', 'POST'])
@superadmin_required
def admin_student_edit(student_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        student_no = request.form.get('student_no', '').strip()
        email = request.form.get('email', '').strip()
        phone = request.form.get('phone', '').strip()
        status = request.form.get('status', 'active')
        password = request.form.get('password', '').strip()
        enrollment_date = request.form.get('enrollment_date') or None
        graduation_date = request.form.get('graduation_date') or None
        
        if not enrollment_date and student_no.startswith('PB') and len(student_no) >= 4:
            enrollment_date = f"20{student_no[2:4]}-09-01"
        if not graduation_date and enrollment_date:
            graduation_date = f"{int(enrollment_date[:4])+4}-07-01"
        
        max_borrow_limit = request.form.get('max_borrow_limit', 30)
        
        try:
            if password:
                pw_hash = generate_password_hash(password)
                cursor.execute("""
                    UPDATE students SET name=%s, student_no=%s, email=%s, phone=%s, status=%s,
                    password_hash=%s, enrollment_date=%s, graduation_date=%s, max_borrow_limit=%s
                    WHERE id=%s
                """, (name, student_no, email, phone, status, pw_hash,
                      enrollment_date, graduation_date, max_borrow_limit, student_id))
            else:
                cursor.execute("""
                    UPDATE students SET name=%s, student_no=%s, email=%s, phone=%s, status=%s,
                    enrollment_date=%s, graduation_date=%s, max_borrow_limit=%s
                    WHERE id=%s
                """, (name, student_no, email, phone, status,
                      enrollment_date, graduation_date, max_borrow_limit, student_id))
            conn.commit()
            flash('学生信息更新成功')
            cursor.close()
            conn.close()
            return redirect(url_for('admin_students'))
        except Exception as e:
            conn.rollback()
            flash(f'更新失败: {str(e)}')
    
    cursor.execute("SELECT * FROM students WHERE id=%s", (student_id,))
    student = cursor.fetchone()
    cursor.close()
    conn.close()
    if not student:
        flash('学生不存在')
        return redirect(url_for('admin_students'))
    return render_template('admin_student_form.html', student=student)

@app.route('/admin/students/add', methods=['GET', 'POST'])
@superadmin_required
def admin_student_add():
    if request.method == 'POST':
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            name = request.form.get('name', '').strip()
            student_no = request.form.get('student_no', '').strip()
            email = request.form.get('email', '').strip()
            phone = request.form.get('phone', '').strip()
            password = request.form.get('password', '').strip()
            
            if not password:
                flash('密码不能为空')
                return redirect(url_for('admin_student_add'))
            
            if not name or not student_no:
                flash('姓名和学号不能为空')
                return redirect(url_for('admin_student_add'))
            
            enrollment_date = request.form.get('enrollment_date') or None
            graduation_date = request.form.get('graduation_date') or None
            
            # 未填写时根据学号自动推断：PB + YY + DD + NNNN
            if not enrollment_date and student_no.startswith('PB') and len(student_no) >= 4:
                enrollment_date = f"20{student_no[2:4]}-09-01"
            if not graduation_date and enrollment_date:
                graduation_date = f"{int(enrollment_date[:4])+4}-07-01"
            max_borrow_limit = request.form.get('max_borrow_limit', 30)
            pw_hash = generate_password_hash(password)
            
            cursor.execute("""
                INSERT INTO students (student_no, name, password_hash, email, phone,
                    enrollment_date, graduation_date, max_borrow_limit)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (student_no, name, pw_hash, email, phone,
                  enrollment_date, graduation_date, max_borrow_limit))
            conn.commit()
            flash('学生添加成功')
        except Exception as e:
            conn.rollback()
            flash(f'添加失败: {str(e)}')
        finally:
            cursor.close()
            conn.close()
        return redirect(url_for('admin_students'))
    return render_template('admin_student_form.html', student=None)

# ====================== 馆藏管理 ======================
@app.route('/admin/copies')
@admin_required
def admin_copies():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    branch = get_librarian_branch()
    if branch:
        cursor.execute("""
            SELECT c.*, b.title, b.isbn 
            FROM copies c JOIN books b ON c.book_id = b.id 
            WHERE c.branch = %s ORDER BY c.id DESC
        """, (branch,))
    else:
        cursor.execute("""
            SELECT c.*, b.title, b.isbn 
            FROM copies c JOIN books b ON c.book_id = b.id 
            ORDER BY c.id DESC
        """)
    copies = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('admin_copies.html', copies=copies)

@app.route('/admin/copies/add/<int:book_id>', methods=['GET', 'POST'])
@admin_required
def admin_copy_add(book_id):
    if request.method == 'POST':
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            count = int(request.form.get('count', 1))
            barcode_prefix = request.form.get('barcode_prefix', '').strip()
            location = request.form.get('location', '总馆').strip()
            
            conn.start_transaction()
            branch = request.form.get('branch', get_librarian_branch() or '总馆')
            for i in range(count):
                barcode = f"{barcode_prefix}{i+1:03d}" if barcode_prefix else f"B{book_id:03d}C{i+1:03d}"
                cursor.execute("""
                    INSERT INTO copies (book_id, barcode, location, branch) VALUES (%s, %s, %s, %s)
                """, (book_id, barcode, location, branch))
            
            cursor.execute("""
                INSERT INTO audit_logs (actor_id, actor_type, action, details)
                VALUES (%s, 'admin', 'add_copies', %s)
            """, (session['user_id'], f'{{"book_id": {book_id}, "count": {count}}}'))
            
            conn.commit()
            flash(f'成功添加 {count} 个馆藏副本')
        except Exception as e:
            conn.rollback()
            flash(f'添加失败: {str(e)}')
        finally:
            cursor.close()
            conn.close()
        return redirect(url_for('admin_copies'))
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM books WHERE id=%s", (book_id,))
    book = cursor.fetchone()
    cursor.close()
    conn.close()
    return render_template('admin_copy_form.html', book=book, copy=None, edit=False)

@app.route('/admin/copies/edit/<int:copy_id>', methods=['GET', 'POST'])
@admin_required
def admin_copy_edit(copy_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    if request.method == 'POST':
        location = request.form.get('location', '').strip()
        status = request.form.get('status', 'available')
        barcode = request.form.get('barcode', '').strip()
        branch = request.form.get('branch', '').strip()
        
        try:
            cursor.execute("""
                UPDATE copies SET location=%s, status=%s, barcode=%s, branch=%s WHERE id=%s
            """, (location, status, barcode, branch, copy_id))
            conn.commit()
            flash('馆藏副本更新成功')
        except Exception as e:
            conn.rollback()
            flash(f'更新失败: {str(e)}')
        finally:
            cursor.close()
            conn.close()
        return redirect(url_for('admin_copies'))
    
    cursor.execute("SELECT c.*, b.title FROM copies c JOIN books b ON c.book_id=b.id WHERE c.id=%s", (copy_id,))
    copy = cursor.fetchone()
    cursor.close()
    conn.close()
    if not copy:
        flash('副本不存在')
        return redirect(url_for('admin_copies'))
    return render_template('admin_copy_form.html', copy=copy, edit=True)

@app.route('/admin/copies/delete/<int:copy_id>', methods=['POST'])
@admin_required
def admin_copy_delete(copy_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM copies WHERE id=%s", (copy_id,))
        conn.commit()
        flash('馆藏副本已删除')
    except Exception as e:
        conn.rollback()
        flash(f'删除失败: {str(e)}')
    finally:
        cursor.close()
        conn.close()
    return redirect(url_for('admin_copies'))

# ====================== 通知处理 ======================
@app.route('/mark_notification/<int:notif_id>', methods=['POST'])
def mark_notification(notif_id):
    if 'user_id' not in session:
        flash('请先登录')
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE notifications SET sent=TRUE WHERE id=%s AND student_id=%s", 
                      (notif_id, session['user_id']))
        conn.commit()
    except Exception:
        conn.rollback()
    finally:
        cursor.close()
        conn.close()
    return redirect(url_for('my_notifications'))

@app.route('/admin/notify_reservation/<int:res_id>', methods=['POST'])
@admin_required
def notify_reservation(res_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        conn.start_transaction()
        
        cursor.execute("""
            SELECT r.*, b.title FROM reservations r 
            JOIN books b ON r.book_id = b.id 
            WHERE r.id = %s
        """, (res_id,))
        reservation = cursor.fetchone()
        
        if not reservation:
            flash('预约不存在')
            raise Exception()
        
        cursor.execute("UPDATE reservations SET status='notified', notified_at=NOW() WHERE id=%s", (res_id,))
        
        cursor.execute("""
            INSERT INTO notifications (student_id, type, payload)
            VALUES (%s, 'reservation_available', %s)
        """, (reservation['student_id'], 
              f'{{"book_id": {reservation["book_id"]}, "title": "{reservation["title"]}", "reservation_id": {res_id}}}'))
        
        cursor.execute("""
            INSERT INTO audit_logs (actor_id, actor_type, action, details)
            VALUES (%s, 'admin', 'notify_reservation', %s)
        """, (session['user_id'], f'{{"reservation_id": {res_id}}}'))
        
        conn.commit()
        flash('已通知学生取书')
    except Exception:
        conn.rollback()
    finally:
        cursor.close()
        conn.close()
    return redirect(url_for('admin_reservations'))

# ====================== 罚款管理 ======================
@app.route('/admin/fines')
@admin_required
def admin_fines():
    filter_type = request.args.get('filter', '')
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    branch = get_librarian_branch()
    
    paid_filter = "AND f.paid = FALSE" if filter_type == 'unpaid' else ""
    branch_filter = "AND c.branch = %s" if branch else ""
    
    params = []
    if branch:
        params.append(branch)
    
    cursor.execute(f"""
        SELECT f.*, s.name as student_name, s.student_no, b.title as book_title
        FROM fines f
        JOIN students s ON f.student_id = s.id
        JOIN borrows bo ON f.borrow_id = bo.id
        JOIN copies c ON bo.copy_id = c.id
        JOIN books b ON c.book_id = b.id
        WHERE 1=1 {paid_filter} {branch_filter}
        ORDER BY f.created_at DESC
    """, params)
    fines = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('admin_fines.html', fines=fines)

@app.route('/admin/fines/pay/<int:fine_id>', methods=['POST'])
@admin_required
def admin_fine_pay(fine_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE fines SET paid=TRUE WHERE id=%s", (fine_id,))
        conn.commit()
        flash('罚款已标记为已缴')
    except Exception:
        conn.rollback()
    finally:
        cursor.close()
        conn.close()
    return redirect(url_for('admin_fines'))

# ====================== 图书详情页 ======================
@app.route('/book/<int:book_id>')
def book_detail(book_id):
    if 'user_id' not in session:
        flash('请先登录')
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("""
        SELECT b.*, p.name as publisher_name
        FROM books b LEFT JOIN publishers p ON b.publisher_id = p.id
        WHERE b.id = %s
    """, (book_id,))
    book = cursor.fetchone()
    
    if not book:
        flash('图书不存在')
        return redirect(url_for('books'))
    
    cursor.execute("""
        SELECT a.name FROM authors a
        JOIN book_authors ba ON a.id = ba.author_id
        WHERE ba.book_id = %s
    """, (book_id,))
    book['authors'] = [r['name'] for r in cursor.fetchall()]
    
    cursor.execute("""
        SELECT c.name FROM categories c
        JOIN book_categories bc ON c.id = bc.category_id
        WHERE bc.book_id = %s
    """, (book_id,))
    book['categories'] = [r['name'] for r in cursor.fetchall()]
    
    cursor.execute("""
        SELECT * FROM copies WHERE book_id = %s AND status = 'available'
    """, (book_id,))
    available_copies = cursor.fetchall()
    
    cursor.execute("""
        SELECT COUNT(*) as cnt FROM reservations 
        WHERE book_id = %s AND status = 'pending'
    """, (book_id,))
    pending_reservations = cursor.fetchone()['cnt']
    
    cursor.execute("""
        SELECT r.status as res_status, s.name as res_name, r.student_id as res_student
        FROM reservations r JOIN students s ON r.student_id=s.id
        WHERE r.book_id = %s AND r.status IN ('pending','notified')
        ORDER BY r.queue_position LIMIT 1
    """, (book_id,))
    reservation = cursor.fetchone()
    has_reservation = reservation is not None
    res_info = reservation if has_reservation else None
    is_my_reservation = reservation and reservation['res_student'] == int(session.get('user_id', 0))
    
    cursor.close()
    conn.close()
    
    return render_template('book_detail.html', book=book, available_copies=available_copies, 
                         pending_reservations=pending_reservations,
                         has_reservation=has_reservation, res_info=res_info,
                         is_my_reservation=is_my_reservation)

# ====================== 报表 ======================
@app.route('/admin/reports')
@admin_required
def admin_reports():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # 借阅排行榜 (Top 10)
    cursor.execute("""
        SELECT b.title, COUNT(bo.id) as borrow_times
        FROM borrows bo
        JOIN copies c ON bo.copy_id = c.id
        JOIN books b ON c.book_id = b.id
        GROUP BY b.id
        ORDER BY borrow_times DESC
        LIMIT 10
    """)
    top_books = cursor.fetchall()
    
    # 活跃学生排行
    cursor.execute("""
        SELECT s.name, s.student_no, COUNT(bo.id) as borrow_times
        FROM borrows bo
        JOIN students s ON bo.student_id = s.id
        GROUP BY s.id
        ORDER BY borrow_times DESC
        LIMIT 10
    """)
    top_students = cursor.fetchall()
    
    # 各分类借阅统计
    cursor.execute("""
        SELECT c.name, COUNT(bo.id) as cnt
        FROM borrows bo
        JOIN copies cp ON bo.copy_id = cp.id
        JOIN book_categories bc ON cp.book_id = bc.book_id
        JOIN categories c ON bc.category_id = c.id
        GROUP BY c.id
        ORDER BY cnt DESC
    """)
    category_stats = cursor.fetchall()
    
    # 本月借阅/归还统计
    cursor.execute("""
        SELECT 
            (SELECT COUNT(*) FROM borrows WHERE MONTH(borrow_date) = MONTH(CURDATE()) AND YEAR(borrow_date) = YEAR(CURDATE())) as monthly_borrows,
            (SELECT COUNT(*) FROM borrows WHERE return_date IS NOT NULL AND MONTH(return_date) = MONTH(CURDATE()) AND YEAR(return_date) = YEAR(CURDATE())) as monthly_returns,
            (SELECT COALESCE(SUM(amount),0) FROM fines WHERE MONTH(created_at) = MONTH(CURDATE()) AND YEAR(created_at) = YEAR(CURDATE())) as monthly_fines
    """)
    monthly_stats = cursor.fetchone()
    
    # 逾期统计
    cursor.execute("""
        SELECT s.name, s.student_no, COUNT(bo.id) as overdue_count,
               COALESCE(SUM(f.amount), 0) as total_fines
        FROM borrows bo
        JOIN students s ON bo.student_id = s.id
        LEFT JOIN fines f ON bo.id = f.borrow_id
        WHERE bo.return_date IS NULL AND bo.due_date < CURDATE()
        GROUP BY s.id
        ORDER BY total_fines DESC
    """)
    overdue_students = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return render_template('admin_reports.html',
                         top_books=top_books,
                         top_students=top_students,
                         category_stats=category_stats,
                         monthly_stats=monthly_stats,
                         overdue_students=overdue_students)

# ====================== CSV 导出 ======================
@app.route('/admin/export/books')
@admin_required
def export_books():
    import csv
    import io
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT b.isbn, b.title, b.publish_year, p.name as publisher,
               GROUP_CONCAT(DISTINCT a.name SEPARATOR ', ') as authors
        FROM books b
        LEFT JOIN publishers p ON b.publisher_id = p.id
        LEFT JOIN book_authors ba ON b.id = ba.book_id
        LEFT JOIN authors a ON ba.author_id = a.id
        GROUP BY b.id
    """)
    books = cursor.fetchall()
    cursor.close()
    conn.close()
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ISBN', '书名', '作者', '出版社', '出版年'])
    for b in books:
        writer.writerow([b['isbn'], b['title'], b['authors'] or '', b['publisher'] or '', b['publish_year'] or ''])
    
    output.seek(0)
    return Response(
        output.getvalue().encode('utf-8-sig'),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment;filename=books_export.csv'}
    )

@app.route('/admin/export/students')
@admin_required
def export_students():
    import csv
    import io
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT student_no, name, email, phone, status FROM students")
    students = cursor.fetchall()
    cursor.close()
    conn.close()
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['学号', '姓名', '邮箱', '电话', '状态'])
    for s in students:
        writer.writerow([s['student_no'], s['name'], s['email'] or '', s['phone'] or '', s['status']])
    
    output.seek(0)
    return Response(
        output.getvalue().encode('utf-8-sig'),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment;filename=students_export.csv'}
    )

# ====================== CSV 批量导入 ======================
@app.route('/admin/import/books', methods=['GET', 'POST'])
@admin_required
def import_books():
    if request.method == 'POST':
        file = request.files.get('csv_file')
        if not file or not file.filename.endswith('.csv'):
            flash('请上传CSV文件')
            return redirect(url_for('import_books'))
        
        import csv
        import io
        
        conn = get_db_connection()
        cursor = conn.cursor()
        success = 0
        errors = []
        
        try:
            stream = io.StringIO(file.stream.read().decode('utf-8-sig'))
            reader = csv.DictReader(stream)
            
            for i, row in enumerate(reader, start=2):
                isbn = row.get('ISBN', '').strip()
                title = row.get('书名', '').strip()
                publish_year = row.get('出版年', '').strip()
                publisher_name = row.get('出版社', '').strip()
                author_name = row.get('作者', '').strip()
                
                if not isbn or not title:
                    errors.append(f'第{i}行: ISBN或书名为空')
                    continue
                
                try:
                    conn.start_transaction()
                    
                    # 处理出版社
                    publisher_id = None
                    if publisher_name:
                        cursor.execute("SELECT id FROM publishers WHERE name=%s", (publisher_name,))
                        pub = cursor.fetchone()
                        if pub:
                            publisher_id = pub[0]
                        else:
                            cursor.execute("INSERT INTO publishers (name) VALUES (%s)", (publisher_name,))
                            publisher_id = cursor.lastrowid
                    
                    year = int(publish_year) if publish_year else None
                    
                    cursor.execute("""
                        INSERT INTO books (isbn, title, publisher_id, publish_year)
                        VALUES (%s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE title=VALUES(title)
                    """, (isbn, title, publisher_id, year))
                    book_id = cursor.lastrowid or cursor.execute("SELECT id FROM books WHERE isbn=%s", (isbn,))
                    
                    # 处理作者
                    if author_name:
                        cursor.execute("SELECT id FROM authors WHERE name=%s", (author_name,))
                        author = cursor.fetchone()
                        if author:
                            author_id = author[0]
                        else:
                            cursor.execute("INSERT INTO authors (name) VALUES (%s)", (author_name,))
                            author_id = cursor.lastrowid
                        cursor.execute("INSERT IGNORE INTO book_authors (book_id, author_id) VALUES (%s, %s)", (book_id, author_id))
                    
                    conn.commit()
                    success += 1
                except Exception as e:
                    conn.rollback()
                    errors.append(f'第{i}行: {str(e)}')
            
            flash(f'导入完成：成功 {success} 条，失败 {len(errors)} 条')
            if errors:
                for err in errors[:5]:
                    flash(err)
        except Exception as e:
            flash(f'文件解析失败: {str(e)}')
        finally:
            cursor.close()
            conn.close()
        
        return redirect(url_for('admin_books'))
    
    return render_template('admin_import_books.html')

@app.route('/admin/import/students', methods=['GET', 'POST'])
@admin_required
def import_students():
    if request.method == 'POST':
        file = request.files.get('csv_file')
        if not file or not file.filename.endswith('.csv'):
            flash('请上传CSV文件')
            return redirect(url_for('import_students'))
        
        import csv
        import io
        
        conn = get_db_connection()
        cursor = conn.cursor()
        success = 0
        errors = []
        
        try:
            stream = io.StringIO(file.stream.read().decode('utf-8-sig'))
            reader = csv.DictReader(stream)
            
            for i, row in enumerate(reader, start=2):
                student_no = row.get('学号', '').strip()
                name = row.get('姓名', '').strip()
                email = row.get('邮箱', '').strip()
                phone = row.get('电话', '').strip()
                
                if not student_no or not name:
                    errors.append(f'第{i}行: 学号或姓名为空')
                    continue
                
                try:
                    pw_hash = generate_password_hash('123456')
                    cursor.execute("""
                        INSERT INTO students (student_no, name, password_hash, email, phone)
                        VALUES (%s, %s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE name=VALUES(name), email=VALUES(email), phone=VALUES(phone)
                    """, (student_no, name, pw_hash, email, phone))
                    conn.commit()
                    success += 1
                except Exception as e:
                    conn.rollback()
                    errors.append(f'第{i}行: {str(e)}')
            
            flash(f'导入完成：成功 {success} 条，失败 {len(errors)} 条')
            if errors:
                for err in errors[:5]:
                    flash(err)
        except Exception as e:
            flash(f'文件解析失败: {str(e)}')
        finally:
            cursor.close()
            conn.close()
        
        return redirect(url_for('admin_students'))
    
    return render_template('admin_import_students.html')

# ====================== 定时任务 ======================
def daily_overdue_job():
    """每天执行逾期检查"""
    conn = get_db_connection()
    if not conn:
        return
    try:
        cursor = conn.cursor()
        cursor.callproc('sp_daily_overdue_check')
        conn.commit()
        cursor.close()
        print(f'[{datetime.now()}] Daily overdue check completed')
    except Exception as e:
        conn.rollback()
        print(f'[{datetime.now()}] Daily overdue check error: {e}')
    finally:
        conn.close()

scheduler = BackgroundScheduler()
scheduler.add_job(daily_overdue_job, 'interval', hours=24, id='daily_check')
scheduler.add_job(lambda: None, 'interval', hours=24, id='reservation_check',
                  next_run_time=datetime.now())
# 在 lambda 中无法传参，改用函数
def reservation_expire_job():
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.callproc('sp_reservation_expire_check')
            conn.commit()
            cursor.close()
            print(f'[{datetime.now()}] Reservation expire check completed')
        except Exception as e:
            print(f'[{datetime.now()}] Reservation expire error: {e}')
        finally:
            conn.close()

scheduler.remove_job('reservation_check')
scheduler.add_job(reservation_expire_job, 'interval', hours=24, id='reservation_check')

scheduler.start()

if __name__ == '__main__':
    app.run(debug=True, port=5000)