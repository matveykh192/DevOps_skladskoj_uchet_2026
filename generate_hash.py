from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
password = "admin123"
hashed = pwd_context.hash(password)
print(f"Хэш для пароля '{password}':")
print(hashed)