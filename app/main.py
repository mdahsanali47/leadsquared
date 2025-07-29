# app/main.py
from fastapi import FastAPI, File, UploadFile, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
import io
from datetime import datetime
from .processing import run_processing_pipeline

app = FastAPI(title="CRM Report Processor")
templates = Jinja2Templates(directory="app/templates")

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    """Serve the main HTML page."""
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/process-reports/")
async def process_reports_endpoint(
    filter_date: str = Form(...),
    planned_visit_file: UploadFile = File(...),
    unplanned_visit_file: UploadFile = File(...),
    counters_file: UploadFile = File(...),
    users_file: UploadFile = File(...)
):
    """
    Endpoint to upload all 4 CSVs and a date, run the full pipeline, and return the result.
    """
    for f in [planned_visit_file, unplanned_visit_file, counters_file, users_file]:
        if not f.filename.endswith('.csv'):
            raise HTTPException(status_code=400, detail=f"Invalid file type: {f.filename}. All files must be CSVs.")

    try:
        result_df = run_processing_pipeline(
            planned_visit_file.file,
            unplanned_visit_file.file,
            counters_file.file,
            users_file.file,
            filter_date_str=filter_date
        )

        output_filename = f"final_report_{filter_date}.csv"

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