from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware

from .routes import s3, chat_routes  # Updated import name

app = FastAPI(
    title="Wildfire Knowledge Graph API",
    description="API for interacting with the Wildfire Knowledge Graph",
    version="0.1.0",  # Updated version
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Authentication setup (commented out for now)
# security = HTTPBearer()

# class AuthMiddleware:
#     async def __call__(self, request: Request, credentials: HTTPAuthorizationCredentials = Depends(security)):
#         try:
#             # TODO: Implement token validation logic
#             # Example:
#             # - Verify JWT token
#             # - Check token expiration
#             # - Validate against user database
#             # token = credentials.credentials
#             # user = await validate_token(token)
#             # request.state.user = user
#             pass
#         except Exception as e:
#             raise HTTPException(
#                 status_code=401,
#                 detail="Invalid authentication credentials",
#                 headers={"WWW-Authenticate": "Bearer"},
#             )

# Include routers
app.include_router(s3.router, prefix="/api")
app.include_router(chat_routes.router, prefix="/api")  # Updated router name

# Example protected route template (commented out)
# @app.get("/protected-route")
# async def protected_route(auth: AuthMiddleware = Depends()):
#     """
#     This is a template for a protected route that requires authentication
#     """
#     return {"message": "This is a protected route"}
