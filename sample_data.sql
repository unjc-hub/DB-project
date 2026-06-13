USE library_db;

INSERT INTO authors (name) VALUES
('鲁迅'), ('莫言'), ('余华'), ('钱钟书'), ('王小波'),
('陈忠实'), ('刘慈欣'), ('金庸'), ('老舍'), ('巴金'),
('J.K. Rowling'), ('George Orwell'), ('Yuval Noah Harari');

-- ===================== 出版社 =====================
INSERT INTO publishers (name) VALUES
('人民文学出版社'), ('作家出版社'), ('上海文艺出版社'),
('三联书店'), ('中信出版社'), ('Bloomsbury');

-- ===================== 分类 =====================
INSERT INTO categories (id, name, parent_id) VALUES
(1, '文学', NULL),
(2, '小说', 1),
(3, '中国文学', 1),
(4, '科幻', NULL),
(5, '历史', NULL),
(6, '哲学', NULL),
(7, '计算机科学', NULL),
(8, '外国文学', 1);

-- ===================== 图书 =====================
INSERT INTO books (id, isbn, title, publisher_id, description, publish_year) VALUES
(1,  '9787020002207', '呐喊',        1, '鲁迅短篇小说集，收录《狂人日记》《阿Q正传》等名篇', 1923),
(2,  '9787020002214', '活着',        2, '余华代表作，讲述人在极端环境下的生存意志', 1993),
(3,  '9787535436887', '红高粱家族',  3, '莫言长篇小说，展现高密东北乡的血性与生命力', 1986),
(4,  '9787020024752', '围城',        1, '钱钟书代表作，中国现代文学经典讽刺小说', 1947),
(5,  '9787535432735', '黄金时代',    2, '王小波代表作，自由与压抑的时代叙事', 1994),
(6,  '9787020104529', '白鹿原',      1, '陈忠实长篇小说，获茅盾文学奖', 1993),
(7,  '9787536692930', '三体',        4, '刘慈欣科幻巨著，雨果奖获奖作品', 2008),
(8,  '9787536693968', '三体II：黑暗森林', 4, '三体系列第二部，宇宙社会学经典', 2008),
(9,  '9787536696006', '三体III：死神永生', 4, '三体系列终章', 2010),
(10, '9787020008735', '骆驼祥子',    1, '老舍代表作，旧社会北京人力车夫的悲剧', 1936),
(11, '9787020008742', '家',          1, '巴金激流三部曲第一部', 1933),
(12, '9787020026076', '射雕英雄传',  3, '金庸武侠经典', 1957),
(13, '9780747532743', 'Harry Potter and the Philosopher''s Stone', 6, 'J.K. Rowling''s magical world begins', 1997),
(14, '9780451524935', '1984',        5, 'George Orwell''s dystopian masterpiece', 1949),
(15, '9780062316097', 'Sapiens',     5, 'Yuval Noah Harari''s bestselling history', 2014),
(16, '9787020145560', '平凡的世界',  1, '路遥长篇小说，获茅盾文学奖', 1986),
(17, '9787544253994', '百年孤独',    3, '加西亚·马尔克斯魔幻现实主义巨著', 1967),
(18, '9787208061644', '红楼梦',      1, '曹雪芹中国古典四大名著之首', 1791),
(19, '9787532768370', '许三观卖血记', 3, '余华长篇小说', 1995),
(20, '9787020070671', '茶馆',        1, '老舍话剧代表作', 1957);

-- ===================== 图书-作者关联 =====================
INSERT INTO book_authors (book_id, author_id) VALUES
(1,1), (2,3), (3,2), (4,4), (5,5), (6,6), (7,7), (8,7), (9,7),
(10,9), (11,10), (12,8), (13,11), (14,12), (15,13),
(16,3), (17,2), (19,3), (20,9);

-- ===================== 图书-分类关联 =====================
INSERT INTO book_categories (book_id, category_id) VALUES
(1,3),(2,3),(3,3),(4,3),(5,3),(6,3),(10,3),(11,3),(12,3),(16,3),(18,3),(19,3),(20,3),
(7,4),(8,4),(9,4),
(13,8),(14,8),(15,5),(17,8),
(1,2),(2,2),(4,2),(5,2),(6,2),(12,2),(13,2),(16,2),(17,2),(19,2),
(15,6);

-- ===================== 馆藏副本 =====================
INSERT INTO copies (id, book_id, barcode, status, location, branch) VALUES
(1,  1,  'B001001', 'available',   'A区-01架', 'A馆'),
(2,  1,  'B001002', 'borrowed',    'A区-01架', 'A馆'),
(3,  2,  'B002001', 'borrowed',    'A区-02架', 'A馆'),
(4,  2,  'B002002', 'available',   'A区-02架', 'A馆'),
(5,  2,  'B002003', 'borrowed',    'A区-02架', 'A馆'),
(6,  3,  'B003001', 'available',   'A区-03架', 'A馆'),
(7,  4,  'B004001', 'available',   'B区-01架', 'B馆'),
(8,  4,  'B004002', 'damaged',     'B区-01架', 'B馆'),
(9,  5,  'B005001', 'available',   'B区-02架', 'B馆'),
(10, 6,  'B006001', 'borrowed',    'B区-03架', 'B馆'),
(11, 7,  'B007001', 'borrowed',    'C区-01架', 'C馆'),
(12, 7,  'B007002', 'borrowed',    'C区-01架', 'C馆'),
(13, 7,  'B007003', 'borrowed',    'C区-01架', 'C馆'),
(14, 8,  'B008001', 'available',   'C区-02架', 'C馆'),
(15, 9,  'B009001', 'borrowed',    'C区-02架', 'C馆'),
(16, 10, 'B010001', 'lost',        'A区-04架', 'A馆'),
(17, 10, 'B010002', 'available',   'A区-04架', 'A馆'),
(18, 11, 'B011001', 'available',   'B区-04架', 'B馆'),
(19, 12, 'B012001', 'available',   'B区-05架', 'B馆'),
(20, 12, 'B012002', 'borrowed',    'B区-05架', 'B馆'),
(21, 13, 'B013001', 'available',   'C区-03架', 'C馆'),
(22, 13, 'B013002', 'available',   'C区-03架', 'C馆'),
(23, 14, 'B014001', 'available',   'C区-04架', 'C馆'),
(24, 15, 'B015001', 'available',   'C区-04架', 'C馆'),
(25, 16, 'B016001', 'available',   'A区-05架', 'A馆'),
(26, 16, 'B016002', 'available',   'A区-05架', 'A馆'),
(27, 17, 'B017001', 'available',   'B区-06架', 'B馆'),
(28, 18, 'B018001', 'available',   'A区-06架', 'A馆'),
(29, 18, 'B018002', 'available',   'A区-06架', 'A馆'),
(30, 19, 'B019001', 'borrowed',    'A区-07架', 'A馆'),
(31, 20, 'B020001', 'available',   'B区-07架', 'B馆');

-- ===================== 学生（密码: 123456） =====================
-- 格式: PB + 入学年(22-26) + 系编号(00-30) + 唯一码(0000-2500)
INSERT INTO students (student_no, name, password_hash, email, phone, enrollment_date, graduation_date, max_borrow_limit) VALUES
('PB22110001', '张伟', 'scrypt:32768:8:1$OKIXv2Q2RnSZX1IK$9c360abb19aeb65a98b3ce905e480236b6f984e100eaaba68d8ed705adde3cfd3e987b144e333715e551459d0253b33d645979c1f71ab7a938ab0d7841fe778e', 'zhangwei@mail.com', '13800001001', '2022-09-01', '2026-07-01', 30),
('PB22050123', '李娜', 'scrypt:32768:8:1$OKIXv2Q2RnSZX1IK$9c360abb19aeb65a98b3ce905e480236b6f984e100eaaba68d8ed705adde3cfd3e987b144e333715e551459d0253b33d645979c1f71ab7a938ab0d7841fe778e', 'lina@mail.com',    '13800001002', '2022-09-01', '2026-07-01', 30),
('PB23111679', '徐俊成', 'scrypt:32768:8:1$OKIXv2Q2RnSZX1IK$9c360abb19aeb65a98b3ce905e480236b6f984e100eaaba68d8ed705adde3cfd3e987b144e333715e551459d0253b33d645979c1f71ab7a938ab0d7841fe778e', 'xujuncheng@mail.com','13900001234', '2023-09-01', '2027-07-01', 30),
('PB23031234', '赵强', 'scrypt:32768:8:1$OKIXv2Q2RnSZX1IK$9c360abb19aeb65a98b3ce905e480236b6f984e100eaaba68d8ed705adde3cfd3e987b144e333715e551459d0253b33d645979c1f71ab7a938ab0d7841fe778e', 'zhaoqiang@mail.com','13800001004', '2023-09-01', '2027-07-01', 30),
('PB24150456', '刘洋', 'scrypt:32768:8:1$OKIXv2Q2RnSZX1IK$9c360abb19aeb65a98b3ce905e480236b6f984e100eaaba68d8ed705adde3cfd3e987b144e333715e551459d0253b33d645979c1f71ab7a938ab0d7841fe778e', 'liuyang@mail.com', '13800001005', '2024-09-01', '2028-07-01', 30),
('PB24200890', '陈静', 'scrypt:32768:8:1$OKIXv2Q2RnSZX1IK$9c360abb19aeb65a98b3ce905e480236b6f984e100eaaba68d8ed705adde3cfd3e987b144e333715e551459d0253b33d645979c1f71ab7a938ab0d7841fe778e', 'chenjing@mail.com','13800001006', '2024-09-01', '2028-07-01', 30),
('PB25102111', '孙鹏', 'scrypt:32768:8:1$OKIXv2Q2RnSZX1IK$9c360abb19aeb65a98b3ce905e480236b6f984e100eaaba68d8ed705adde3cfd3e987b144e333715e551459d0253b33d645979c1f71ab7a938ab0d7841fe778e', 'sunpeng@mail.com', '13800001007', '2025-09-01', '2029-07-01', 30),
('PB25221500', '周敏', 'scrypt:32768:8:1$OKIXv2Q2RnSZX1IK$9c360abb19aeb65a98b3ce905e480236b6f984e100eaaba68d8ed705adde3cfd3e987b144e333715e551459d0253b33d645979c1f71ab7a938ab0d7841fe778e', 'zhoumin@mail.com', '13800001008', '2025-09-01', '2029-07-01', 30),
('PB26071888', '吴昊', 'scrypt:32768:8:1$OKIXv2Q2RnSZX1IK$9c360abb19aeb65a98b3ce905e480236b6f984e100eaaba68d8ed705adde3cfd3e987b144e333715e551459d0253b33d645979c1f71ab7a938ab0d7841fe778e', 'wuhao@mail.com',   '13800001009', '2026-03-01', '2030-07-01', 30),
('PB26132001', '郑丽', 'scrypt:32768:8:1$OKIXv2Q2RnSZX1IK$9c360abb19aeb65a98b3ce905e480236b6f984e100eaaba68d8ed705adde3cfd3e987b144e333715e551459d0253b33d645979c1f71ab7a938ab0d7841fe778e', 'zhengli@mail.com', '13800001010', '2026-03-01', '2030-07-01', 30);

-- ===================== 管理员（密码: admin123） =====================
INSERT INTO admins (username, name, password_hash, role, branch) VALUES
('admin', '管理员',   'scrypt:32768:8:1$9BnqbFwFagdkwkHX$8b8195ad78f7181012b76fe75f69ae88af51dba6a35812a0a9a480cec4b49ab09eb19b0b3e0aead46e88ddc8ed1838dd927f40a01f6c643c4f272e4a1a7caf0c', 'superadmin', NULL),
('lib_a', '张馆员',   'scrypt:32768:8:1$9BnqbFwFagdkwkHX$8b8195ad78f7181012b76fe75f69ae88af51dba6a35812a0a9a480cec4b49ab09eb19b0b3e0aead46e88ddc8ed1838dd927f40a01f6c643c4f272e4a1a7caf0c', 'librarian', 'A馆'),
('lib_b', '李馆员',   'scrypt:32768:8:1$9BnqbFwFagdkwkHX$8b8195ad78f7181012b76fe75f69ae88af51dba6a35812a0a9a480cec4b49ab09eb19b0b3e0aead46e88ddc8ed1838dd927f40a01f6c643c4f272e4a1a7caf0c', 'librarian', 'B馆'),
('lib_c', '王馆员',   'scrypt:32768:8:1$9BnqbFwFagdkwkHX$8b8195ad78f7181012b76fe75f69ae88af51dba6a35812a0a9a480cec4b49ab09eb19b0b3e0aead46e88ddc8ed1838dd927f40a01f6c643c4f272e4a1a7caf0c', 'librarian', 'C馆');

-- ===================== 借阅记录 =====================
INSERT INTO borrows (id, copy_id, student_id, borrow_date, due_date, return_date) VALUES
(1, 2,  1, '2026-05-10', '2026-06-09', NULL),
(2, 5,  3, '2026-05-15', '2026-06-14', NULL),
(3, 10, 4, '2026-05-01', '2026-05-31', NULL),
(4, 13, 2, '2026-05-20', '2026-06-19', NULL),
(5, 15, 10, '2026-03-20', '2026-04-19', NULL),
(6, 12, 10, '2026-04-01', '2026-05-01', NULL);

-- ===================== 罚款 =====================
INSERT INTO fines (borrow_id, student_id, amount, paid) VALUES
(2, 3, 0.00, FALSE);

-- ===================== 通知 =====================
INSERT INTO notifications (student_id, type, payload, sent) VALUES
(1, 'overdue_reminder', '{"title":"呐喊","days":0}', TRUE);

-- ===================== 演示实例：徐俊成 (PB23111679, student_id=3) =====================
-- 当前借阅 4 本
INSERT INTO borrows (id, copy_id, student_id, borrow_date, due_date, return_date) VALUES
(9,  3,  3, '2026-05-20', '2026-06-19', NULL),
(10, 11, 3, '2026-05-25', '2026-06-24', NULL),
(11, 20, 3, '2026-06-01', '2026-07-01', NULL),
(12, 30, 3, '2026-06-05', '2026-07-05', NULL),
-- 借阅历史 2 本
(13, 7,  3, '2026-02-15', '2026-03-17', '2026-03-20'),
(14, 28, 3, '2026-03-01', '2026-03-31', '2026-04-02');

-- 更新对应副本状态
UPDATE copies SET status='borrowed' WHERE id IN (3, 11, 20, 30);

-- 预约
INSERT INTO reservations (book_id, student_id, queue_position, status) VALUES
(9, 3, 1, 'pending');

-- 罚款
INSERT INTO fines (borrow_id, student_id, amount, paid) VALUES
(14, 3, 0.02, TRUE);

-- 通知（徐俊成）
INSERT INTO notifications (student_id, type, payload, sent) VALUES
(3, 'reservation_confirmed', '{"title":"三体III：死神永生","position":1}', FALSE),
(3, 'borrow', '{"title":"活着","barcode":"B002001","due":"2026-06-19"}', TRUE),
(3, 'borrow', '{"title":"三体","barcode":"B007001","due":"2026-06-24"}', TRUE),
(3, 'borrow', '{"title":"射雕英雄传","barcode":"B012002","due":"2026-07-01"}', TRUE);