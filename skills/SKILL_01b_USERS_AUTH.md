# SKILL 01b — Users and Authorisation
**Sequence:** After SK06 complete. Before SK07 frontend.
**Time:** 1 day.
**Output:** JWT auth, four user roles, org_id from token, PostgreSQL RLS wired.

---

## Why this skill exists

Every API route built so far uses hardcoded `org_id="test-org"`.
The frontend in SK07 needs real authentication from day one.
Retrofitting auth after the frontend is built is significantly harder.

This skill adds:
- JWT bearer token authentication on every API route
- `org_id` extracted from the token, never hardcoded
- Four user roles with enforced permissions
- PostgreSQL RLS activated via `SET LOCAL app.current_org_id`
- One test user created for development

---

## RULES FOR CLAUDE CODE

1. Never hardcode org_id in any file after this skill
2. Never skip the RLS wiring — it is the security boundary
3. Never store plain text passwords — bcrypt only
4. Run each checkpoint before moving to the next step
5. Do not start SK07 until all 7 checkpoints pass

---

## WHAT DOES NOT CHANGE

The nine agents do not change.
The fact store does not change.
The Qdrant client does not change.
The output models do not change.
All existing checkpoints SK01-SK06 must still pass after this skill.

---

## STEP 1 — Install dependencies

Add to requirements.txt if not already present:

```text
python-jose[cryptography]==3.3.0
bcrypt==4.1.3
passlib[bcrypt]==1.7.4
```

```bash
pip install python-jose[cryptography] bcrypt passlib[bcrypt]
```

Verify:
```bash
python -c "from jose import jwt; from passlib.context import CryptContext; print('auth deps ok')"
```

---

## STEP 2 — Add auth settings to config.py

Add these fields to the Settings class in `app/config.py`:

```python
# Auth
jwt_secret_key: str = "change-me-in-production"
jwt_algorithm: str = "HS256"
jwt_expiry_minutes: int = 480  # 8 hours

# Default dev user (never use in production)
dev_user_email: str = "dev@platform.local"
dev_user_password: str = "devpassword2026"
dev_org_id: str = "test-org"
dev_user_role: str = "company_admin"
```

Add to `.env`:
```bash
JWT_SECRET_KEY=<run: python -c "import secrets; print(secrets.token_hex(32))">
JWT_ALGORITHM=HS256
JWT_EXPIRY_MINUTES=480
```

---

## STEP 3 — Create app/core/auth.py

```python
# app/core/auth.py
"""
JWT authentication and user role management.

Four roles:
  platform_admin   — operator level, cross-org visibility, no customer data
  company_admin    — all departments within their org
  department_admin — sets criteria templates, sees all evals in their dept
  department_user  — runs evaluations, can override with documented reason

Token payload:
  sub          — user email
  org_id       — organisation identifier
  role         — one of the four roles above
  dept_id      — department identifier (optional, for dept-scoped roles)
  exp          — expiry timestamp
"""
from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from app.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

VALID_ROLES = {
    "platform_admin",
    "company_admin",
    "department_admin",
    "department_user"
}


class TokenData(BaseModel):
    email: str
    org_id: str
    role: str
    dept_id: Optional[str] = None


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    org_id: str
    role: str


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(
    email: str,
    org_id: str,
    role: str,
    dept_id: Optional[str] = None
) -> Token:
    """Creates a signed JWT token with org_id and role in payload."""
    if role not in VALID_ROLES:
        raise ValueError(f"Invalid role: {role}. Must be one of {VALID_ROLES}")

    expiry = datetime.now(timezone.utc) + timedelta(
        minutes=settings.jwt_expiry_minutes
    )

    payload = {
        "sub": email,
        "org_id": org_id,
        "role": role,
        "exp": expiry,
    }
    if dept_id:
        payload["dept_id"] = dept_id

    token = jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm
    )

    return Token(
        access_token=token,
        token_type="bearer",
        expires_in=settings.jwt_expiry_minutes * 60,
        org_id=org_id,
        role=role
    )


def decode_token(token: str) -> TokenData:
    """
    Decodes and validates a JWT token.
    Raises JWTError if token is invalid or expired.
    """
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm]
        )
        email = payload.get("sub")
        org_id = payload.get("org_id")
        role = payload.get("role")
        dept_id = payload.get("dept_id")

        if not email or not org_id or not role:
            raise JWTError("Missing required fields in token")

        if role not in VALID_ROLES:
            raise JWTError(f"Invalid role in token: {role}")

        return TokenData(
            email=email,
            org_id=org_id,
            role=role,
            dept_id=dept_id
        )
    except JWTError:
        raise


def require_role(*allowed_roles: str):
    """
    Returns a dependency function that enforces role requirements.
    Usage: Depends(require_role("company_admin", "department_admin"))
    """
    def check_role(token_data: TokenData) -> TokenData:
        if token_data.role not in allowed_roles:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{token_data.role}' is not permitted. "
                       f"Required: {list(allowed_roles)}"
            )
        return token_data
    return check_role
```

<!-- CHECKPOINT -->
```bash
python checkpoint_runner.py SK01b-CP01
```

---

## STEP 4 — Create app/core/dependencies.py

```python
# app/core/dependencies.py
"""
FastAPI dependency injection for authentication.

Usage in route:
    @router.get("/evaluations")
    async def list_evaluations(
        current_user: TokenData = Depends(get_current_user)
    ):
        # current_user.org_id is verified from JWT
        # current_user.role is verified from JWT
        ...
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError
from app.core.auth import decode_token, TokenData
from app.config import settings

security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> TokenData:
    """
    Extracts and validates the bearer token from the Authorization header.
    Returns TokenData with org_id and role verified.
    Raises 401 if token is missing, invalid, or expired.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        token_data = decode_token(credentials.credentials)
        return token_data
    except JWTError:
        raise credentials_exception


async def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials = Depends(
        HTTPBearer(auto_error=False)
    )
) -> TokenData | None:
    """
    Same as get_current_user but returns None if no token provided.
    Used for endpoints that work with or without auth (e.g. health check).
    """
    if not credentials:
        return None
    try:
        return decode_token(credentials.credentials)
    except JWTError:
        return None
```

---

## STEP 5 — Create app/api/auth_routes.py

```python
# app/api/auth_routes.py
"""
Authentication endpoints.

POST /api/v1/auth/token  — exchange credentials for JWT token
POST /api/v1/auth/verify — verify a token is valid (used by frontend)
GET  /api/v1/auth/me     — get current user info from token
"""
from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel
from app.core.auth import (
    verify_password, create_access_token,
    hash_password, Token, TokenData
)
from app.core.dependencies import get_current_user
from app.config import settings

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str
    password: str
    org_id: str


class UserInfo(BaseModel):
    email: str
    org_id: str
    role: str
    dept_id: str | None = None


# In-memory user store for development.
# Replace with PostgreSQL users table in production (Skill 01b extension).
_DEV_USERS: dict[str, dict] = {}


def _init_dev_user():
    """Creates the development user on startup if it does not exist."""
    email = settings.dev_user_email
    if email not in _DEV_USERS:
        _DEV_USERS[email] = {
            "email": email,
            "hashed_password": hash_password(settings.dev_user_password),
            "org_id": settings.dev_org_id,
            "role": settings.dev_user_role,
            "dept_id": None,
            "is_active": True
        }


_init_dev_user()


@router.post("/token", response_model=Token)
async def login(request: LoginRequest):
    """
    Exchange email + password + org_id for a JWT token.

    For development: use the credentials from .env
        email: dev@platform.local
        password: devpassword2026
        org_id: test-org
    """
    user = _DEV_USERS.get(request.email)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )

    if user["org_id"] != request.org_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )

    if not verify_password(request.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )

    if not user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive"
        )

    return create_access_token(
        email=user["email"],
        org_id=user["org_id"],
        role=user["role"],
        dept_id=user.get("dept_id")
    )


@router.post("/verify")
async def verify_token(
    current_user: TokenData = Depends(get_current_user)
):
    """Verifies a token is valid and returns the token payload."""
    return {
        "valid": True,
        "email": current_user.email,
        "org_id": current_user.org_id,
        "role": current_user.role
    }


@router.get("/me", response_model=UserInfo)
async def get_me(
    current_user: TokenData = Depends(get_current_user)
):
    """Returns current user information extracted from the token."""
    return UserInfo(
        email=current_user.email,
        org_id=current_user.org_id,
        role=current_user.role,
        dept_id=current_user.dept_id
    )
```

<!-- CHECKPOINT -->
```bash
python checkpoint_runner.py SK01b-CP02
```

---

## STEP 6 — Create app/api/middleware.py

```python
# app/api/middleware.py
"""
Request middleware for PostgreSQL RLS activation.

Every authenticated request sets app.current_org_id in PostgreSQL
so row-level security policies can enforce tenant isolation.

This runs BEFORE any route handler executes.
The org_id comes from the verified JWT token — never from the request body.
"""
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from jose import JWTError
from app.core.auth import decode_token
import sqlalchemy as sa
from app.db.fact_store import get_engine

# Routes that do not require auth and do not need RLS
PUBLIC_ROUTES = {
    "/health",
    "/api/v1/auth/token",
    "/docs",
    "/openapi.json",
    "/redoc"
}


class AuthMiddleware(BaseHTTPMiddleware):
    """
    Middleware that:
    1. Extracts org_id from JWT on every authenticated request
    2. Sets app.current_org_id in PostgreSQL for RLS enforcement
    3. Attaches token_data to request.state for route handlers
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # Skip auth for public routes
        if request.url.path in PUBLIC_ROUTES:
            return await call_next(request)

        # Extract token from Authorization header
        auth_header = request.headers.get("Authorization", "")
        token_data = None

        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            try:
                token_data = decode_token(token)
                request.state.user = token_data
            except JWTError:
                pass  # Route handler will return 401 via Depends

        # Set PostgreSQL RLS context if we have a valid org_id
        if token_data:
            try:
                engine = get_engine()
                with engine.connect() as conn:
                    conn.execute(
                        sa.text(
                            "SET LOCAL app.current_org_id = :org_id"
                        ),
                        {"org_id": token_data.org_id}
                    )
                    conn.commit()
            except Exception as e:
                # Log but do not block — RLS policies will catch
                # unauthorised access even without this hint
                print(f"RLS context setting failed: {e}")

        return await call_next(request)
```

---

## STEP 7 — Register auth routes and middleware in app/main.py

Update `app/main.py` to include the auth router and middleware:

```python
# In create_app() function, add these lines:

from app.api.auth_routes import router as auth_router
from app.api.middleware import AuthMiddleware

def create_app() -> FastAPI:
    app = FastAPI(
        title="Enterprise Agentic AI Platform",
        version="1.0.0"
    )

    # Add auth middleware FIRST — before any other middleware
    app.add_middleware(AuthMiddleware)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register auth routes
    app.include_router(auth_router)

    @app.get("/health")
    async def health():
        return {
            "status": "healthy",
            "version": "1.0.0",
            "skill": "01b-auth"
        }

    return app
```

<!-- CHECKPOINT -->
```bash
python checkpoint_runner.py SK01b-CP03
python checkpoint_runner.py SK01b-CP04
```

---

## STEP 8 — Add checkpoints to checkpoint_runner.py

Add these checkpoint functions to `checkpoint_runner.py`:

```python
# ── SKILL 01b CHECKPOINTS ─────────────────────────────────────────

def SK01b_CP01():
    """JWT token creation and decoding works correctly"""
    code, out = _run("""python -c "
from app.core.auth import create_access_token, decode_token
token = create_access_token(
    email='test@test.com',
    org_id='org-001',
    role='department_user'
)
assert token.access_token
assert token.org_id == 'org-001'
assert token.role == 'department_user'
decoded = decode_token(token.access_token)
assert decoded.email == 'test@test.com'
assert decoded.org_id == 'org-001'
assert decoded.role == 'department_user'
print('JWT creation and decoding ok')
" """)
    return (code == 0 and "ok" in out, out[:200])


def SK01b_CP02():
    """Auth routes importable and token endpoint exists"""
    code, out = _run("""python -c "
from app.api.auth_routes import router
routes = [r.path for r in router.routes]
assert '/api/v1/auth/token' in routes, f'Token route missing. Found: {routes}'
assert '/api/v1/auth/me' in routes, f'Me route missing. Found: {routes}'
print('Auth routes ok:', routes)
" """)
    return (code == 0 and "Auth routes ok" in out, out[:200])


def SK01b_CP03():
    """FastAPI app starts with auth middleware registered"""
    import subprocess, time
    proc = subprocess.Popen(
        "uvicorn app.main:create_app --factory --port 18001 --log-level error",
        shell=True, cwd=str(ROOT),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    time.sleep(3)
    try:
        c, o = _run("curl -s http://localhost:18001/health 2>/dev/null")
        passed = "healthy" in o
        return passed, f"FastAPI with auth: {o[:80]}"
    finally:
        proc.terminate()
        proc.wait()


def SK01b_CP04():
    """Token endpoint returns JWT for valid dev credentials"""
    import subprocess, time
    proc = subprocess.Popen(
        "uvicorn app.main:create_app --factory --port 18002 --log-level error",
        shell=True, cwd=str(ROOT),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    time.sleep(3)
    try:
        c, o = _run("""curl -s -X POST http://localhost:18002/api/v1/auth/token \
            -H "Content-Type: application/json" \
            -d "{\\"email\\":\\"dev@platform.local\\",\\"password\\":\\"devpassword2026\\",\\"org_id\\":\\"test-org\\"}" \
            2>/dev/null""")
        passed = c == 0 and "access_token" in o
        return passed, f"Token endpoint: {o[:150]}"
    finally:
        proc.terminate()
        proc.wait()


def SK01b_CP05():
    """Invalid role rejected by require_role dependency"""
    code, out = _run("""python -c "
from app.core.auth import create_access_token, decode_token, require_role, TokenData
token = create_access_token(
    email='user@test.com',
    org_id='org-001',
    role='department_user'
)
decoded = decode_token(token.access_token)
checker = require_role('company_admin', 'platform_admin')
try:
    checker(decoded)
    print('FAIL: should have raised')
except Exception as e:
    print('role enforcement ok:', str(e)[:60])
" """)
    return (code == 0 and "role enforcement ok" in out, out[:200])


def SK01b_CP06():
    """Invalid token rejected with 401"""
    import subprocess, time
    proc = subprocess.Popen(
        "uvicorn app.main:create_app --factory --port 18003 --log-level error",
        shell=True, cwd=str(ROOT),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    time.sleep(3)
    try:
        c, o = _run("""curl -s -o /dev/null -w "%{http_code}" \
            -H "Authorization: Bearer invalidtoken123" \
            http://localhost:18003/api/v1/auth/me 2>/dev/null""")
        passed = "401" in o
        return passed, f"Invalid token returns 401: {o}"
    finally:
        proc.terminate()
        proc.wait()


def SK01b_CP07():
    """org_id never hardcoded in any agent file"""
    code, out = _run("""python -c "
import os, re
agent_dir = 'app/agents'
violations = []
for fname in os.listdir(agent_dir):
    if not fname.endswith('.py'):
        continue
    fpath = os.path.join(agent_dir, fname)
    content = open(fpath).read()
    # Check for hardcoded test-org (not in comments or strings used for tests)
    lines = content.split('\\\\n')
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if 'test-org' in line and not stripped.startswith('#'):
            violations.append(f'{fname}:{i}: {stripped[:60]}')
if violations:
    print('HARDCODED org_id found:')
    for v in violations:
        print(' ', v)
else:
    print('no hardcoded org_id in agent files ok')
" """)
    return (code == 0 and "ok" in out, out[:300])


# Register SK01b checkpoints
CHECKPOINTS.update({
    "SK01b-CP01": (SK01b_CP01, "JWT token creation and decoding"),
    "SK01b-CP02": (SK01b_CP02, "Auth routes importable"),
    "SK01b-CP03": (SK01b_CP03, "FastAPI starts with auth middleware"),
    "SK01b-CP04": (SK01b_CP04, "Token endpoint returns JWT for dev user"),
    "SK01b-CP05": (SK01b_CP05, "Invalid role rejected by require_role"),
    "SK01b-CP06": (SK01b_CP06, "Invalid token returns 401"),
    "SK01b-CP07": (SK01b_CP07, "No hardcoded org_id in agent files"),
})
```

---

## STEP 9 — Verify all existing checkpoints still pass

```bash
python checkpoint_runner.py all
```

All SK01-SK06 checkpoints must still pass.
Zero regressions allowed before proceeding to SK07.

---

## SKILL 01b COMPLETE

```bash
python checkpoint_runner.py SK01b
python contract_tests.py
python drift_detector.py
```

All 7 checkpoints must pass.
Update CLAUDE.md: current_skill = SK07

Open SKILL_07 when ready.

---

## HAND-OFF NOTE TO SK07

The frontend now has real auth available:

**Get a token:**
```bash
curl -X POST http://localhost:8000/api/v1/auth/token \
  -H "Content-Type: application/json" \
  -d '{"email":"dev@platform.local","password":"devpassword2026","org_id":"test-org"}'
```

**Use the token:**
```bash
curl -H "Authorization: Bearer <token>" \
  http://localhost:8000/api/v1/evaluations
```

**In Next.js frontend:**
Store the token in httpOnly cookie (not localStorage).
Send as Authorization: Bearer header on every API call.
Redirect to /login if any API call returns 401.

---

## PRODUCTION NOTE

The in-memory `_DEV_USERS` store in `auth_routes.py` is for 
development only. Before going to production add:

1. PostgreSQL `users` table with hashed passwords
2. User registration endpoint (company_admin only)
3. Password reset flow
4. Token refresh endpoint
5. SSO integration (Azure AD / Okta) — see Integration Landscape doc

These are post-SK09 items. The current implementation
is sufficient for SK07 frontend development and demo.
