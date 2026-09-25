import bcrypt
import asyncio
import asyncpg

async def fix_admin_password():
    # подключаемся к базе внутри докера
    conn = await asyncpg.connect('postgresql://warehouse_user:secure_password_123@db:5432/warehouse_db')
    
    password = "admin123"
    # генерируем нормальный хэш
    hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    # обновляем админа
    await conn.execute("UPDATE users SET password_hash = $1 WHERE username = 'admin'", hashed)
    print("пароль для admin успешно обновлен!")
    
    await conn.close()

asyncio.run(fix_admin_password())
