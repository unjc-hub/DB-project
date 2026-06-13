import mysql.connector, re

c = mysql.connector.connect(host='localhost', user='root', password='123456', database='library_db')
cur = c.cursor()

# 清空所有表
cur.execute('SET FOREIGN_KEY_CHECKS=0')
tables = ['fines','notifications','audit_logs','reservations','borrows','copies','book_categories','book_authors','books','categories','publishers','authors','students','admins']
for t in tables:
    cur.execute('DELETE FROM ' + t)
    cur.execute('ALTER TABLE ' + t + ' AUTO_INCREMENT = 1')
cur.execute('SET FOREIGN_KEY_CHECKS=1')
c.commit()

# 逐行执行 SQL，遇到分号视为一条完整语句
with open('sample_data.sql', 'r', encoding='utf-8') as f:
    lines = f.readlines()

stmt = ''
errors = 0
for line in lines:
    stripped = line.strip()
    # 跳过注释和空行
    if not stripped or stripped.startswith('--'):
        continue
    stmt += ' ' + stripped
    if stripped.endswith(';'):
        try:
            cur.execute(stmt.strip())
            c.commit()
        except Exception as e:
            errors += 1
            if errors <= 2:
                print(f'ERR {errors}: {str(e)[:100]}')
                print(f'  SQL: {stmt.strip()[:120]}')
        stmt = ''

cur.close()
c.close()
print(f'Done! Errors: {errors}')
