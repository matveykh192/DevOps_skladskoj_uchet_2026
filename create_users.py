import bcrypt
import asyncio
import asyncpg

async def create_users():
    # подключаемся к базе
    conn = await asyncpg.connect('postgresql://warehouse_user:secure_password_123@db:5432/warehouse_db')
    
    # генерируем хэши паролей
    admin_hash = bcrypt.hashpw(b'admin123', bcrypt.gensalt()).decode('utf-8')
    worker_hash = bcrypt.hashpw(b'worker123', bcrypt.gensalt()).decode('utf-8')
    
    # создаём или обновляем админа (role_id=1)
    await conn.execute(
        """INSERT INTO users (username, password_hash, role_id, is_active) 
           VALUES ('admin', $1, 1, true)
           ON CONFLICT (username) DO UPDATE SET password_hash = $1""",
        admin_hash
    )
    
    # создаём или обновляем кладовщика (role_id=2, warehouse_worker)
    await conn.execute(
        """INSERT INTO users (username, password_hash, role_id, is_active) 
           VALUES ('storekeeper', $1, 2, true)
           ON CONFLICT (username) DO UPDATE SET password_hash = $1""",
        worker_hash
    )
    
    print("пользователи созданы:")
    print("  admin / admin123 (роль: admin)")
    print("  storekeeper / worker123 (роль: warehouse_worker)")
    
    await conn.close()

asyncio.run(create_users())