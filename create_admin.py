from app.db import get_engine
from app.models import User
from app.auth import get_password_hash
from sqlmodel import Session, select

def create_admin_if_not_exists():
    engine = get_engine()
    with Session(engine) as session:
        # Check if admin user exists
        admin_user = session.exec(
            select(User).where(User.username == "admin")
        ).first()

        if not admin_user:
            print("Creating admin user...")
            admin_user = User(
                username="admin",
                email="admin@example.com",
                hashed_password=get_password_hash("admin"),
                role="admin",
                display_name="Admin User",
                is_active=True
            )
            session.add(admin_user)
            session.commit()
            session.refresh(admin_user)
            print(f"Admin user created with ID: {admin_user.id}")
        else:
            print(f"Admin user already exists with ID: {admin_user.id}")

        # List all users
        users = session.exec(select(User)).all()
        print(f"Total users: {len(users)}")
        for user in users:
            print(f"- {user.username} ({user.role}) - active: {user.is_active}")

if __name__ == "__main__":
    create_admin_if_not_exists()
