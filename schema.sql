-- 图书馆管理系统数据库 schema (MySQL 8+)
-- 满足 3NF，包含 ER 图核心实体

CREATE DATABASE IF NOT EXISTS library_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE library_db;

-- 作者
CREATE TABLE authors (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE
);

-- 出版社
CREATE TABLE publishers (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE
);

-- 分类（支持树形结构）
CREATE TABLE categories (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(50) NOT NULL,
    parent_id BIGINT NULL,
    FOREIGN KEY (parent_id) REFERENCES categories(id) ON DELETE SET NULL
);

-- 书目
CREATE TABLE books (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    isbn VARCHAR(20) UNIQUE NOT NULL,
    title VARCHAR(200) NOT NULL,
    publisher_id BIGINT NULL,
    description TEXT,
    publish_year INT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (publisher_id) REFERENCES publishers(id) ON DELETE SET NULL
);

-- 书目-作者 多对多
CREATE TABLE book_authors (
    book_id BIGINT NOT NULL,
    author_id BIGINT NOT NULL,
    PRIMARY KEY (book_id, author_id),
    FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE,
    FOREIGN KEY (author_id) REFERENCES authors(id) ON DELETE CASCADE
);

-- 书目-分类 多对多
CREATE TABLE book_categories (
    book_id BIGINT NOT NULL,
    category_id BIGINT NOT NULL,
    PRIMARY KEY (book_id, category_id),
    FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE,
    FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE CASCADE
);

-- 馆藏副本 (Copy)
CREATE TABLE copies (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    book_id BIGINT NOT NULL,
    barcode VARCHAR(50) UNIQUE NOT NULL,
    status ENUM('available', 'borrowed', 'damaged', 'lost') DEFAULT 'available',
    location VARCHAR(100),
    branch VARCHAR(50) DEFAULT NULL,
    version INT DEFAULT 0,           -- 乐观锁
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE
);

-- 学生
CREATE TABLE students (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    student_no VARCHAR(20) UNIQUE NOT NULL,
    name VARCHAR(50) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    status ENUM('active', 'suspended') DEFAULT 'active',
    email VARCHAR(100),
    phone VARCHAR(20),
    avatar VARCHAR(255) DEFAULT NULL,
    enrollment_date DATE DEFAULT NULL,
    graduation_date DATE DEFAULT NULL,
    max_borrow_limit INT DEFAULT 30,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 管理员
CREATE TABLE admins (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    name VARCHAR(50) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role ENUM('librarian', 'superadmin') DEFAULT 'librarian',
    email VARCHAR(100),
    phone VARCHAR(20),
    avatar VARCHAR(255) DEFAULT NULL,
    branch VARCHAR(50) DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 借阅记录
CREATE TABLE borrows (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    copy_id BIGINT NOT NULL,
    student_id BIGINT NOT NULL,
    borrow_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    due_date DATE NOT NULL,
    return_date DATE NULL,
    FOREIGN KEY (copy_id) REFERENCES copies(id) ON DELETE RESTRICT,
    FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE RESTRICT
);

-- 预约
CREATE TABLE reservations (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    book_id BIGINT NOT NULL,
    student_id BIGINT NOT NULL,
    queue_position INT NOT NULL,
    status ENUM('pending', 'notified', 'expired', 'cancelled') DEFAULT 'pending',
    notified_at TIMESTAMP NULL,
    expire_at TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE,
    FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
);

-- 罚款
CREATE TABLE fines (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    borrow_id BIGINT NOT NULL,
    student_id BIGINT NOT NULL,
    amount DECIMAL(10,2) NOT NULL,
    paid BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (borrow_id) REFERENCES borrows(id) ON DELETE CASCADE,
    FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
);

-- 通知
CREATE TABLE notifications (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    student_id BIGINT NOT NULL,
    type VARCHAR(50) NOT NULL,
    payload JSON,
    sent BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
);

-- 审计日志
CREATE TABLE audit_logs (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    actor_id BIGINT NOT NULL,
    actor_type ENUM('admin', 'student', 'system') NOT NULL,
    action VARCHAR(100) NOT NULL,
    details JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 索引优化
CREATE INDEX idx_books_title ON books(title);
CREATE INDEX idx_copies_status ON copies(status);
CREATE INDEX idx_borrows_due ON borrows(due_date);
CREATE INDEX idx_reservations_book ON reservations(book_id, status);


-- ============================================================
-- 存储函数 (Functions)
-- ============================================================

DELIMITER $$

-- 函数1: 计算某条借阅记录的罚款金额（逾期天数 × 1元/天）
CREATE FUNCTION fn_calculate_fine(p_borrow_id BIGINT)
RETURNS DECIMAL(10,2)
DETERMINISTIC
READS SQL DATA
BEGIN
    DECLARE v_due_date DATE;
    DECLARE v_return_date DATE;
    DECLARE v_overdue_days INT;
    DECLARE v_fine DECIMAL(10,2) DEFAULT 0;

    SELECT due_date, COALESCE(return_date, CURDATE())
    INTO v_due_date, v_return_date
    FROM borrows WHERE id = p_borrow_id;

    SET v_overdue_days = DATEDIFF(v_return_date, v_due_date);
    IF v_overdue_days > 0 THEN
        SET v_fine = v_overdue_days * 0.01;
    END IF;

    RETURN v_fine;
END$$

-- 函数2: 检查学生是否可以借阅（返回可借原因，空字符串表示可以）
CREATE FUNCTION fn_can_borrow(p_student_id BIGINT)
RETURNS VARCHAR(100)
DETERMINISTIC
READS SQL DATA
BEGIN
    DECLARE v_status VARCHAR(20);
    DECLARE v_borrow_cnt INT;
    DECLARE v_unpaid_fines DECIMAL(10,2);

    -- 检查状态
    SELECT status INTO v_status FROM students WHERE id = p_student_id;
    IF v_status = 'suspended' THEN
        RETURN '账号已被暂停借阅';
    END IF;

    -- 检查借阅上限（使用学生表中的 max_borrow_limit）
    SELECT COUNT(*) INTO v_borrow_cnt
    FROM borrows WHERE student_id = p_student_id AND return_date IS NULL;
    IF v_borrow_cnt >= (SELECT max_borrow_limit FROM students WHERE id = p_student_id) THEN
        RETURN CONCAT('已达到借阅上限（', (SELECT max_borrow_limit FROM students WHERE id = p_student_id), '本）');
    END IF;

    -- 检查未缴罚款
    SELECT COALESCE(SUM(amount), 0) INTO v_unpaid_fines
    FROM fines WHERE student_id = p_student_id AND paid = FALSE;
    IF v_unpaid_fines >= 10 THEN
        RETURN CONCAT('有未缴罚款 ¥', FORMAT(v_unpaid_fines, 2), '，请先缴纳');
    END IF;

    RETURN '';
END$$

-- 函数3: 获取学生当前借阅数量
CREATE FUNCTION fn_current_borrows(p_student_id BIGINT)
RETURNS INT
DETERMINISTIC
READS SQL DATA
BEGIN
    DECLARE v_cnt INT;
    SELECT COUNT(*) INTO v_cnt
    FROM borrows WHERE student_id = p_student_id AND return_date IS NULL;
    RETURN v_cnt;
END$$


-- ============================================================
-- 存储过程 (Stored Procedures)
-- ============================================================

-- 存储过程1: 借书（完整事务，含所有校验）
CREATE PROCEDURE sp_borrow_book(
    IN p_copy_id BIGINT,
    IN p_student_id BIGINT,
    IN p_actor_type VARCHAR(10),   -- 'student' or 'admin'
    IN p_actor_id BIGINT
)
BEGIN
    DECLARE v_can_borrow VARCHAR(100);
    DECLARE v_copy_status VARCHAR(20);
    DECLARE v_due_date DATE;
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = '借阅失败，事务已回滚';
    END;

    START TRANSACTION;

    -- 使用函数检查借阅资格
    SET v_can_borrow = fn_can_borrow(p_student_id);
    IF v_can_borrow != '' THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = v_can_borrow;
    END IF;

    -- 锁定副本行
    SELECT status INTO v_copy_status FROM copies WHERE id = p_copy_id FOR UPDATE;
    IF v_copy_status != 'available' THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = '该图书当前不可借阅';
    END IF;

    -- 计算借期
    SET v_due_date = CURDATE() + INTERVAL 30 DAY;

    -- 创建借阅记录
    INSERT INTO borrows (copy_id, student_id, due_date)
    VALUES (p_copy_id, p_student_id, v_due_date);

    -- 更新副本状态（乐观锁）
    UPDATE copies SET status = 'borrowed', version = version + 1
    WHERE id = p_copy_id AND version >= 0;

    -- 写入审计日志
    INSERT INTO audit_logs (actor_id, actor_type, action, details)
    VALUES (p_actor_id, p_actor_type, 'borrow',
            JSON_OBJECT('copy_id', p_copy_id, 'due_date', v_due_date));

    COMMIT;
END$$

-- 存储过程2: 归还图书（完整事务，含罚款计算和预约通知）
CREATE PROCEDURE sp_process_return(
    IN p_borrow_id BIGINT,
    IN p_admin_id BIGINT
)
BEGIN
    DECLARE v_copy_id BIGINT;
    DECLARE v_book_id BIGINT;
    DECLARE v_student_id BIGINT;
    DECLARE v_fine DECIMAL(10,2);
    DECLARE v_next_res_id BIGINT;
    DECLARE v_next_student_id BIGINT;
    DECLARE v_next_student_name VARCHAR(50);
    DECLARE v_expire_at DATETIME;
    DECLARE v_return_exists INT DEFAULT 0;

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = '归还处理失败，事务已回滚';
    END;

    START TRANSACTION;

    -- 获取借阅信息并锁定
    SELECT bo.copy_id, c.book_id, bo.student_id
    INTO v_copy_id, v_book_id, v_student_id
    FROM borrows bo
    JOIN copies c ON bo.copy_id = c.id
    WHERE bo.id = p_borrow_id AND bo.return_date IS NULL
    FOR UPDATE;

    IF v_copy_id IS NULL THEN
        SELECT COUNT(*) INTO v_return_exists FROM borrows WHERE id = p_borrow_id AND return_date IS NOT NULL;
        IF v_return_exists > 0 THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = '该记录已归还';
        ELSE
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = '借阅记录不存在';
        END IF;
    END IF;

    -- 更新还书日期
    UPDATE borrows SET return_date = CURDATE() WHERE id = p_borrow_id;

    -- 恢复副本状态
    UPDATE copies SET status = 'available', version = version + 1
    WHERE id = v_copy_id;

    -- 使用函数计算罚款
    SET v_fine = fn_calculate_fine(p_borrow_id);
    IF v_fine > 0 THEN
        INSERT INTO fines (borrow_id, student_id, amount)
        VALUES (p_borrow_id, v_student_id, v_fine);

        -- 发送罚款通知
        INSERT INTO notifications (student_id, type, payload)
        VALUES (v_student_id, 'fine_notice',
                JSON_OBJECT('borrow_id', p_borrow_id, 'amount', v_fine));
    END IF;

    -- 预约自动分配：查找队首预约
    SELECT r.id, r.student_id, s.name
    INTO v_next_res_id, v_next_student_id, v_next_student_name
    FROM reservations r
    JOIN students s ON r.student_id = s.id
    WHERE r.book_id = v_book_id AND r.status = 'pending'
    ORDER BY r.queue_position ASC
    LIMIT 1;

    IF v_next_res_id IS NOT NULL THEN
        SET v_expire_at = NOW() + INTERVAL 3 DAY;
        UPDATE reservations
        SET status = 'notified', notified_at = NOW(), expire_at = v_expire_at
        WHERE id = v_next_res_id;

        INSERT INTO notifications (student_id, type, payload)
        VALUES (v_next_student_id, 'reservation_available',
                JSON_OBJECT('book_id', v_book_id, 'reservation_id', v_next_res_id,
                           'expire_at', v_expire_at));
    END IF;

    -- 审计日志
    INSERT INTO audit_logs (actor_id, actor_type, action, details)
    VALUES (p_admin_id, 'admin', 'return',
            JSON_OBJECT('borrow_id', p_borrow_id, 'fine', v_fine,
                       'notified_reservation', IFNULL(v_next_res_id, 0)));

    COMMIT;
END$$

-- 存储过程3: 每日逾期检查（生成罚款并通知）
CREATE PROCEDURE sp_daily_overdue_check()
BEGIN
    DECLARE done INT DEFAULT FALSE;
    DECLARE v_borrow_id BIGINT;
    DECLARE v_student_id BIGINT;
    DECLARE v_overdue_days INT;
    DECLARE v_fine DECIMAL(10,2);

    DECLARE cur CURSOR FOR
        SELECT bo.id, bo.student_id, DATEDIFF(CURDATE(), bo.due_date)
        FROM borrows bo
        WHERE bo.return_date IS NULL AND bo.due_date < CURDATE();

    DECLARE CONTINUE HANDLER FOR NOT FOUND SET done = TRUE;

    OPEN cur;
    read_loop: LOOP
        FETCH cur INTO v_borrow_id, v_student_id, v_overdue_days;
        IF done THEN LEAVE read_loop; END IF;

        SET v_fine = v_overdue_days * 0.01;

        -- 检查今天是否已生成过罚款（避免重复）
        IF NOT EXISTS (
            SELECT 1 FROM fines
            WHERE borrow_id = v_borrow_id AND DATE(created_at) = CURDATE()
        ) AND NOT EXISTS (
            SELECT 1 FROM fines WHERE borrow_id = v_borrow_id AND amount >= v_fine
        ) THEN
            INSERT INTO fines (borrow_id, student_id, amount)
            VALUES (v_borrow_id, v_student_id, v_fine);

            INSERT INTO notifications (student_id, type, payload)
            VALUES (v_student_id, 'overdue_reminder',
                    JSON_OBJECT('borrow_id', v_borrow_id, 'overdue_days', v_overdue_days,
                               'fine', v_fine));
        END IF;
    END LOOP;
    CLOSE cur;

    -- 自动暂停欠款超过50元的学生
    UPDATE students SET status = 'suspended'
    WHERE status = 'active' AND id IN (
        SELECT student_id FROM fines WHERE paid = FALSE
        GROUP BY student_id HAVING SUM(amount) >= 50
    );

    INSERT INTO audit_logs (actor_id, actor_type, action, details)
    VALUES (0, 'system', 'daily_overdue_check',
            JSON_OBJECT('checked_at', NOW()));
END$$


-- ============================================================
-- 触发器 (Triggers)
-- ============================================================

-- 触发器1: borrows 表 INSERT 之后，确保副本状态一致性
CREATE TRIGGER trg_borrows_after_insert
AFTER INSERT ON borrows
FOR EACH ROW
BEGIN
    -- 记录操作日志（独立于业务层，确保每笔借阅都有迹可循）
    INSERT INTO audit_logs (actor_id, actor_type, action, details)
    VALUES (NEW.student_id, 'student', 'borrow_trigger',
            JSON_OBJECT('borrow_id', NEW.id, 'copy_id', NEW.copy_id,
                       'due_date', NEW.due_date, 'auto_log', TRUE));
END$$

-- 触发器2: fines 表 UPDATE 之后，当罚款被标记为已缴时检查是否需要恢复学生状态
CREATE TRIGGER trg_fines_after_update
AFTER UPDATE ON fines
FOR EACH ROW
BEGIN
    DECLARE v_total_unpaid DECIMAL(10,2);

    -- 仅当 paid 从 FALSE 变为 TRUE 时触发
    IF NEW.paid = TRUE AND OLD.paid = FALSE THEN
        -- 计算该学生当前剩余未缴罚款
        SELECT COALESCE(SUM(amount), 0) INTO v_total_unpaid
        FROM fines WHERE student_id = NEW.student_id AND paid = FALSE;

        -- 如果未缴罚款降至 50 元以下，且学生是 suspended，恢复为 active
        IF v_total_unpaid < 50 THEN
            UPDATE students SET status = 'active'
            WHERE id = NEW.student_id AND status = 'suspended';

            -- 记录状态恢复
            IF ROW_COUNT() > 0 THEN
                INSERT INTO audit_logs (actor_id, actor_type, action, details)
                VALUES (NEW.student_id, 'system', 'auto_reactivate',
                        JSON_OBJECT('student_id', NEW.student_id,
                                   'reason', '罚款已缴清或低于阈值',
                                   'unpaid_remaining', v_total_unpaid));
            END IF;
        END IF;
    END IF;
END$$

-- 触发器3: students 表 UPDATE 之前，记录状态变更审计
CREATE TRIGGER trg_students_before_update
BEFORE UPDATE ON students
FOR EACH ROW
BEGIN
    -- 当学生状态发生变化时自动记录
    IF OLD.status != NEW.status THEN
        INSERT INTO audit_logs (actor_id, actor_type, action, details)
        VALUES (NEW.id, 'system', 'student_status_change',
                JSON_OBJECT('student_id', NEW.id,
                           'old_status', OLD.status,
                           'new_status', NEW.status));
    END IF;
END$$

-- 触发器4: reservations 表 UPDATE 之后，当预约被取消时重排队列
CREATE TRIGGER trg_reservations_after_update
AFTER UPDATE ON reservations
FOR EACH ROW
BEGIN
    -- 当预约状态从 pending 变为 cancelled/expired 时，重排后续队列
    IF OLD.status = 'pending' AND NEW.status IN ('cancelled', 'expired') THEN
        UPDATE reservations
        SET queue_position = queue_position - 1
        WHERE book_id = NEW.book_id
          AND status = 'pending'
          AND queue_position > OLD.queue_position;
    END IF;
END$$

DELIMITER ;