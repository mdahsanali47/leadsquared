# app/main.py
import io
from datetime import timedelta
from typing import Optional
from jose import JWTError, jwt

from fastapi import (APIRouter, Cookie, Depends, FastAPI, File, Form, HTTPException,
                     Request, Response, UploadFile, status)
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.templating import Jinja2Templates

from . import auth
from .processing import run_processing_pipeline

# Create the main FastAPI app instance
app = FastAPI(title="CRM Report Processor")

# Create an APIRouter for all our application routes
router = APIRouter()

templates = Jinja2Templates(directory="app/templates")

# --- Authentication Dependency ---
async def get_token_from_cookie(access_token: Optional[str] = Cookie(None)) -> Optional[str]:
    return access_token

# --- Login and Logout Endpoints (with URL Generation Fixes) ---

@router.get("/login", response_class=HTMLResponse, name="login_form")
async def login_form(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@router.post("/token")
async def login_for_access_token(
    request: Request,
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends()
):
    if form_data.username == auth.TEST_USERNAME and auth.verify_password(form_data.password, auth.TEST_PASSWORD_HASH):
        access_token_expires = timedelta(minutes=auth.ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = auth.create_access_token(data={"sub": form_data.username}, expires_delta=access_token_expires)
        response.set_cookie(key="access_token", value=access_token, httponly=True, samesite="strict")
        response.status_code = status.HTTP_303_SEE_OTHER
        response.headers["Location"] = request.url_for('read_root') 
        return response
    
    return templates.TemplateResponse("login.html", {"request": request, "error_message": "Incorrect username or password"}, status_code=400)

@router.post("/logout")
async def logout(request: Request, response: Response):
    response.delete_cookie(key="access_token")
    return RedirectResponse(url=request.url_for('login_form'), status_code=status.HTTP_303_SEE_OTHER)

# --- Protected Application Endpoints (with URL Generation Fixes) ---

# Step 1: Give the main page endpoint a unique name
@router.get("/", response_class=HTMLResponse, name="read_root")
async def read_root(request: Request, access_token: Optional[str] = Depends(get_token_from_cookie)):
    if access_token is None:
        return RedirectResponse(url=request.url_for('login_form'), status_code=status.HTTP_303_SEE_OTHER)
    try:
        payload = jwt.decode(access_token, auth.SECRET_KEY, algorithms=[auth.ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            return RedirectResponse(url=request.url_for('login_form'), status_code=status.HTTP_303_SEE_OTHER)
    except JWTError:
        return RedirectResponse(url=request.url_for('login_form'), status_code=status.HTTP_303_SEE_OTHER)
    
    return templates.TemplateResponse("index.html", {"request": request, "username": username})

@router.post("/process-reports/")
async def process_reports_endpoint(

    start_date: str = Form(...), end_date: str = Form(...), planned_visit_file: UploadFile = File(...), unplanned_visit_file: UploadFile = File(...), counters_file: UploadFile = File(...), users_file: UploadFile = File(...), access_token: Optional[str] = Depends(get_token_from_cookie)
):
    credentials_exception = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    if access_token is None: raise credentials_exception
    try:
        payload = jwt.decode(access_token, auth.SECRET_KEY, algorithms=[auth.ALGORITHM])
        if payload.get("sub") is None: raise credentials_exception
    except JWTError: raise credentials_exception
    
    try:
        result_df = run_processing_pipeline(planned_visit_file.file, unplanned_visit_file.file, counters_file.file, users_file.file, start_date_str=start_date, end_date_str=end_date)
        output_filename = f"final_report_{start_date}_to_{end_date}.csv"
        output_stream = io.StringIO()
        result_df.to_csv(output_stream, index=False)
        output_stream.seek(0)
        return StreamingResponse(iter([output_stream.read()]), media_type="text/csv", headers={"Content-Disposition": f"attachment; filename={output_filename}"})
    except Exception as e:
        print(f"Error during processing: {e}") 
        raise HTTPException(status_code=500, detail=f"An error occurred during processing: {e}")

# Mount the router with all its routes onto the main app at the desired prefix.
app.include_router(router, prefix="/leadsquared")