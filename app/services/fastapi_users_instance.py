from app.db.models import User
from app.services.fastapi_users_custom import FastAPIUsersCustomRegister
from app.services.users import auth_backend, get_user_manager

fastapi_users = FastAPIUsersCustomRegister[User, type(User.id)](
    get_user_manager,
    [auth_backend],
)