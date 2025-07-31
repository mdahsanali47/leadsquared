# app/main.py
import io
from datetime import timedelta
from typing import Optional
from jose import JWTError, jwt

from fastapi import (Cookie, Depends, FastAPI, File, Form, HTTPException,
                     Request, Response, UploadFile, status)
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.templating import Jinja2Templates

# Import our new auth functions and configuration
from . import auth
from .processing import run_processing_pipeline

app = FastAPI(title="CRM Report Processor")
templates = Jinja2Templates(directory="app/templates")

# --- New Authentication Dependency ---
async def get_current_user_from_cookie(access_token: Optional[str] = Cookie(None)):
    """
    Reads the cookie, verifies the JWT, and returns the username.
    Raises HTTPException if the token is invalid or missing.
    """
    if access_token is None:
        return None # No cookie found

    try:
        payload = jwt.decode(access_token, auth.SECRET_KEY, algorithms=[auth.ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            return None
        return {"username": username}
    except JWTError:
        return None # Token is invalid

async def get_token_from_cookie(access_token: Optional[str] = Cookie(None)) -> Optional[str]:
    return access_token

# --- Login and Logout Endpoints ---

@app.get("/login", response_class=HTMLResponse)
async def login_form(request: Request):
    """Serves the login page HTML."""
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/token")
async def login_for_access_token(
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends()
):
    """
    Processes the login form, verifies credentials, and sets the session cookie.
    """
    if form_data.username == auth.TEST_USERNAME and auth.verify_password(form_data.password, auth.TEST_PASSWORD_HASH):
        access_token_expires = timedelta(minutes=auth.ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = auth.create_access_token(
            data={"sub": form_data.username}, expires_delta=access_token_expires
        )

        # --- THIS IS THE FIX ---
        # 1. Set the cookie on the response object.
        response.set_cookie(
            key="access_token",
            value=access_token,
            httponly=True,
            samesite="strict",
            # Add secure=True and domain if you are using HTTPS in production
            # secure=True, 
            # domain="your-domain.com"
        )
        
        # 2. Manually set the redirect headers on the SAME response object.
        # Do NOT return a new RedirectResponse object.
        response.status_code = status.HTTP_303_SEE_OTHER
        response.headers["Location"] = "/"
        return response
        # --- END OF FIX ---
    
    # If login fails, re-render the login page with an error message
    return templates.TemplateResponse(
        "login.html",
        {"request": {}, "error_message": "Incorrect username or password"},
        status_code=400
    )

@app.post("/logout")
async def logout(response: Response):
    """Clears the session cookie and redirects to the login page."""
    response.delete_cookie(key="access_token")
    return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)


# --- Protected Application Endpoints ---

@app.get("/", response_class=HTMLResponse)
async def read_root(
    request: Request,
    # Use the new, simpler dependency
    access_token: Optional[str] = Depends(get_token_from_cookie)
):
    """
    Serves the main application page IF the user is logged in.
    Otherwise, redirects to the login page.
    """
    if access_token is None:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    try:
        # Perform the validation logic here
        payload = jwt.decode(access_token, auth.SECRET_KEY, algorithms=[auth.ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            # Token is invalid or doesn't contain a username
            return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    except JWTError:
        # Token is malformed or expired
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    
    # If we reach here, the user is authenticated
    return templates.TemplateResponse("index.html", {"request": request, "username": username})


@app.post("/process-reports/")
async def process_reports_endpoint(
    start_date: str = Form(...),
    end_date: str = Form(...),
    planned_visit_file: UploadFile = File(...),
    unplanned_visit_file: UploadFile = File(...),
    counters_file: UploadFile = File(...),
    users_file: UploadFile = File(...),
    # This dependency protects the endpoint.
    access_token: Optional[str] = Depends(get_token_from_cookie)
):
    """
    Processes the uploaded files. Only accessible to authenticated users.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if access_token is None:
        raise credentials_exception

    try:
        # Perform the same validation logic here
        payload = jwt.decode(access_token, auth.SECRET_KEY, algorithms=[auth.ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    # --- If we reach here, the user is authenticated. The rest of the function proceeds. ---
    
    try:
        # ... (your existing run_processing_pipeline call and response generation)
        result_df = run_processing_pipeline(
            planned_visit_file.file,
            unplanned_visit_file.file,
            counters_file.file,
            users_file.file,
            start_date_str=start_date,
            end_date_str=end_date
        )

        output_filename = f"final_report_{start_date}_to_{end_date}.csv"
        output_stream = io.StringIO()
        result_df.to_csv(output_stream, index=False)
        output_stream.seek(0)
        
        return StreamingResponse(
            iter([output_stream.read()]),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={output_filename}"}
        )
    except Exception as e:
        print(f"Error during processing: {e}") 
        raise HTTPException(status_code=500, detail=f"An error occurred during processing: {e}")