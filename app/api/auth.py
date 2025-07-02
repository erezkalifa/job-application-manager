from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import timedelta
import logging
import uuid

from app.db.session import get_db
from app.models.user import User
from app.schemas.user import UserCreate, UserResponse, Token, UserLogin
from app.services.auth_service import (
    create_user,
    authenticate_user,
    create_access_token,
    ACCESS_TOKEN_EXPIRE_MINUTES
)

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login")

@router.post("/signup", response_model=UserResponse)
async def signup(user_data: UserCreate, db: Session = Depends(get_db)):
    """Create a new user"""
    logger.info(f"Received signup request for email: {user_data.email}")
    try:
        user = create_user(db, user_data)
        logger.info(f"Successfully created user with email: {user_data.email}")
        return UserResponse.from_orm(user)
    except HTTPException as e:
        logger.error(f"Failed to create user: {str(e.detail)}")
        raise e
    except Exception as e:
        logger.error(f"Unexpected error creating user: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.post("/login", response_model=Token)
def login(user_data: UserLogin, db: Session = Depends(get_db)):
    """Login and get access token"""
    user = authenticate_user(db, user_data.email, user_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.email}, expires_delta=access_token_expires
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": UserResponse.from_orm(user)
    }

@router.post("/guest-login")
async def guest_login():
    """Create a temporary guest access token without database storage"""
    try:
        # Generate a unique guest ID
        guest_id = str(uuid.uuid4())
        guest_username = f"Guest_{guest_id[:8]}"
        
        # Create guest token with 20 minute expiry
        access_token_expires = timedelta(minutes=20)
        access_token = create_access_token(
            data={
                "sub": f"guest_{guest_id}@trackit.temp",
                "is_guest": True,
                "guest_id": guest_id,
                "username": guest_username
            },
            expires_delta=access_token_expires
        )
        
        # Create a guest user response without database
        guest_user = {
            "id": 0,  # Dummy ID for guest
            "email": f"guest_{guest_id}@trackit.temp",
            "username": guest_username,
            "is_guest": True
        }
        
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user": guest_user
        }
        
    except Exception as e:
        logger.error(f"Error in guest login: {str(e)}")
        logger.exception("Full traceback:")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create guest access: {str(e)}"
        ) 