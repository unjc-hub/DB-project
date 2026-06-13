# 图书馆管理系统

基于 Flask + MySQL 的图书管理系统，支持学生借阅、管理员管理、预约排队、逾期罚款等完整功能。

## 技术栈

- **后端**: Python 3.11 + Flask
- **数据库**: MySQL 8.0+
- **前端**: Bootstrap 5.3 + Cropper.js

## 快速启动

### 1. 配置环境
```bash
pip install -r requirements.txt
```

### 2. 创建数据库
```bash
mysql -u root -p < schema.sql
```

### 3. 配置 .env
```
DB_HOST=localhost
DB_USER=root
DB_PASSWORD=123456
DB_NAME=library_db
SECRET_KEY=your-secret-key
```

### 4. 导入示例数据
```bash
python reload_data.py
```

### 5. 启动服务
```bash
python app.py
```

访问 http://localhost:5000

## 测试账号

| 角色 | 用户名 | 密码 |
|------|--------|------|
| 超管 | admin | admin123 |
| A馆分馆长 | lib_a | admin123 |
| B馆分馆长 | lib_b | admin123 |
| C馆分馆长 | lib_c | admin123 |
| 学生 | PB23111679 | 123456 |

## 项目结构

```
├── app.py              # Flask 主应用
├── schema.sql          # 数据库架构
├── sample_data.sql     # 示例数据
├── reload_data.py      # 数据重载脚本
├── audit.py            # 数据一致性审计
├── requirements.txt    # 依赖
├── .env                # 环境变量
└── templates/          # 前端模板
    ├── _nav_admin.html
    ├── _nav_student.html
    ├── index.html
    ├── login.html
    ├── dashboard.html
    ├── books.html
    ├── book_detail.html
    ├── my_borrows.html
    ├── my_reservations.html
    ├── my_notifications.html
    ├── my_history.html
    ├── profile.html
    ├── admin_dashboard.html
    ├── admin_books.html
    ├── admin_book_form.html
    ├── admin_students.html
    ├── admin_student_form.html
    ├── admin_copies.html
    ├── admin_copy_form.html
    ├── admin_borrows.html
    ├── admin_reservations.html
    ├── admin_notifications.html
    ├── admin_fines.html
    ├── admin_reports.html
    ├── admin_import_books.html
    └── admin_import_students.html
```

## 核心功能

### 学生端
- 图书搜索与筛选（ISBN/书名/作者/出版社/分类）
- 借阅 / 续借（30天借期，最多续借2次）
- 预约排队（到书通知，3天取书期限）
- 个人中心（头像上传、信息编辑、密码修改）
- 借阅历史 / 罚款查询 / 通知中心

### 管理员端
- 图书 CRUD（多作者/分类）
- 馆藏管理（批量添加副本、状态维护）
- 学生管理（仅超管）
- 借阅管理 / 归还处理（自动罚款+预约分配）
- 预约管理 / 罚款管理
- 数据报表 / CSV导入导出

### 高级特性
- **事务一致性**: SELECT FOR UPDATE 行锁 + 乐观锁 version 字段
- **定时任务**: APScheduler 每日逾期检查 + 预约过期处理
- **分馆长权限**: 三馆独立管理，最小权限原则
- **存储过程/函数/触发器**: 4个SP + 3个Function + 4个Trigger
- **AJAX交互**: 借阅/续借/预约均通过 Modal 弹窗确认

## 业务规则

| 项目 | 值 |
|------|-----|
| 借阅期限 | 30天 |
| 续借期限 | 30天（最多2次） |
| 借阅上限 | 30册 |
| 逾期罚款 | ¥0.01/天 |
| 欠款暂停 | ≥ ¥50 |
| 预约取书 | 3天内 |

## 维护命令

```bash
python reload_data.py    # 重置数据
python audit.py          # 审计数据一致性
```
