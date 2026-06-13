import mysql.connector

c = mysql.connector.connect(host='localhost', user='root', password='123456', database='library_db')
cur = c.cursor(dictionary=True)

print('=== 副本状态 vs 借阅记录 ===')
cur.execute("""SELECT c.id, c.barcode, b.title, c.status,
    (SELECT COUNT(*) FROM borrows WHERE copy_id=c.id AND return_date IS NULL) as active
    FROM copies c JOIN books b ON c.book_id=b.id
    WHERE c.status IN ('borrowed','damaged','lost') ORDER BY c.id""")
for r in cur.fetchall():
    ok = 'OK' if (r['status'] in ('damaged','lost') or r['active'] > 0) else 'BAD'
    print(f"  [{ok}] {r['barcode']} ({r['title']}) s={r['status']} active={r['active']}")

print()
print('=== 预约 vs 可借副本 ===')
cur.execute("""SELECT r.id, b.title, r.student_id, r.status,
    (SELECT COUNT(*) FROM copies WHERE book_id=r.book_id AND status='available') as avail
    FROM reservations r JOIN books b ON r.book_id=b.id WHERE r.status='pending'""")
for r in cur.fetchall():
    ok = 'OK' if r['avail'] == 0 else 'BAD'
    print(f"  [{ok}] 预约《{r['title']}》(s{r['student_id']}) avail={r['avail']}")

print()
print('=== 归还后未更新的副本 ===')
cur.execute("""SELECT c.id, c.barcode, b.title, c.status, bo.return_date
    FROM copies c JOIN books b ON c.book_id=b.id
    JOIN borrows bo ON bo.copy_id=c.id
    WHERE c.status='borrowed' AND bo.return_date IS NOT NULL""")
for r in cur.fetchall():
    print(f"  BAD: {r['barcode']} ({r['title']}) borrowed but returned {r['return_date']}")

c.close()
