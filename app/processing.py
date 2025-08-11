# app/processing.py
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
from tqdm import tqdm
from datetime import time, datetime
import io
import yaml
from app.digipin import get_digipin

tqdm.pandas()

# --- Configuration ---
SHAPEFILE_PATH = "data/India_Districts.shp"
MAPPING_FILE_PATH = "data/district_mapping.yml"
SHP_DISTRICT_COL = "Dist_Name"
SHP_STATE_COL = "State_Name" 

# It will be loaded lazily on the first request.
shapefile_for_join_cache = None 

def load_and_prepare_shapefile():
    """
    Loads the shapefile and applies the custom business name mapping from a YAML file.
    This is run once on application startup.
    """
    print("Loading shapefile...")
    try:
        india_gdf = gpd.read_file(SHAPEFILE_PATH)
        india_gdf = india_gdf.to_crs(epsg=4326)
    except Exception as e:
        print(f"CRITICAL ERROR: Could not load shapefile. Error: {e}")
        return None

    print("Loading and parsing district mapping YAML file...")
    try:
        with open(MAPPING_FILE_PATH, 'r') as f:
            mapping_data = yaml.safe_load(f)
        if not mapping_data:
            mapping_data = {}
    except FileNotFoundError:
        print(f"WARNING: Mapping file not found at {MAPPING_FILE_PATH}. Using raw shapefile names.")
        mapping_data = {}
    except Exception as e:
        print(f"CRITICAL ERROR: Could not read or parse mapping YAML file. Error: {e}")
        return None

    def get_mapped_district(row):
        state_name = row[SHP_STATE_COL]
        district_name = row[SHP_DISTRICT_COL]

        district_map_for_state = mapping_data.get(state_name)

        if district_map_for_state:
            return district_map_for_state.get(district_name, district_name)
        
        return district_name

    india_gdf['master_district'] = india_gdf.apply(get_mapped_district, axis=1)
    india_gdf['master_state'] = india_gdf[SHP_STATE_COL].str.title()
    print("Mapping applied successfully from YAML.")

    shapefile_for_join = india_gdf[['master_state', 'master_district', 'geometry']].copy()
    shapefile_for_join.rename(columns={
        'master_district': 'found_district',
        'master_state': 'found_state'
    }, inplace=True)
    
    return shapefile_for_join

def parse_mixed_formats(series, formats):
    """
    Tries to parse a pandas Series with a list of different date formats.
    """
    # Start with an empty series to hold the results
    parsed_series = pd.Series(pd.NaT, index=series.index)
    to_parse = series.copy()

    for fmt in formats:
        converted = pd.to_datetime(to_parse, format=fmt, errors='coerce')
        parsed_series = parsed_series.fillna(converted)    
        to_parse = to_parse[converted.isna()]

    # If any strings are left over after trying all formats, try one last time automatically
    if not to_parse.empty:
        last_try = pd.to_datetime(to_parse, errors='coerce')
        parsed_series = parsed_series.fillna(last_try)

    return parsed_series

def run_processing_pipeline(planned_visit_file, unplanned_visit_file, counters_file, users_file, start_date_str: str, end_date_str: str):
    """
    Main function to execute the entire data processing logic.
    This version IGNORES operational city/state columns and relies 100% on the shapefile for geocoding.
    """

    # --- Using global cache for shapefile_for_join ---
    global shapefile_for_join_cache 

    if shapefile_for_join_cache is None:
        print("Shapefile data not yet loaded. Loading now...")
        shapefile_for_join_cache = load_and_prepare_shapefile()
        if shapefile_for_join_cache is None:
            raise RuntimeError("Shapefile could not be loaded on demand. Cannot process data.")
    else:
        print("Shapefile data already loaded in memory. Reusing cache.")

    # Using cached data for processing
    shapefile_for_join = shapefile_for_join_cache

    # Step 1: Read all uploaded files into DataFrames
    counters = pd.read_csv(counters_file)
    pv = pd.read_csv(planned_visit_file)
    uv = pd.read_csv(unplanned_visit_file, encoding='cp1252', low_memory=False, dtype={1: str, 6: str})
    users = pd.read_csv(users_file)

    # Step 2: Pre-processing logic
    pv = pv[pv['Task Completed'].notna()].copy()
    counters_unique = counters.drop_duplicates('Counter Code', keep='first').set_index('Counter Code')
    pv['Latitude']  = pv['Counter Code'].map(counters_unique['Latitude'])
    pv['Longitude'] = pv['Counter Code'].map(counters_unique['Longitude'])
    pv.rename(columns={'Task Completed':'CompletedOn'}, inplace=True)
    pv['visit_type'] = 'Planned'
    
    uv.rename(columns={'Activity Date':'CompletedOn', 'Activity Created By':'Task Owner', 'Activity Created By Email':'Task Owner Email'}, inplace=True)
    uv['visit_type'] = 'Unplanned'

    common_cols = [
        'Counter Name','Counter Number','Counter Type','Counter Stage',
        'Counter Code','New or Existing','CompletedOn',
        'Task Owner','Task Owner Email','Latitude', 'Longitude',
        'Operational Cities','Operational States','Taluka or District',
        'visit_type'
    ]
    
    df = pd.concat([pv[common_cols], uv[common_cols]], ignore_index=True)
    df['Latitude'] = pd.to_numeric(df['Latitude'], errors='coerce')
    df['Longitude'] = pd.to_numeric(df['Longitude'], errors='coerce')

    # Step 3: Concatenate visit data
    print(f"Original record count: {len(df)}")
    known_formats = [
        '%d-%m-%Y %H:%M',        
        '%d-%b-%Y %H:%M:%S',
    ]
    
    print(f"Attempting to parse 'CompletedOn' with formats: {known_formats}")
    df['CompletedOn'] = parse_mixed_formats(df['CompletedOn'], formats=known_formats)

    # Now, check for any rows that *still* failed after trying all formats
    failed_count = df['CompletedOn'].isna().sum()
    if failed_count > 0:
        print(f"WARNING: Dropping {failed_count} rows where 'CompletedOn' could not be parsed with any known format.")
        df.dropna(subset=['CompletedOn'], inplace=True)

    start_date = pd.to_datetime(start_date_str).date()
    end_date = pd.to_datetime(end_date_str).date()
    
    # Create a boolean mask to filter rows within the date range (inclusive)
    date_range_mask = (df['CompletedOn'].dt.date >= start_date) & (df['CompletedOn'].dt.date <= end_date)
    df = df[date_range_mask].copy()
    
    print(f"Record count after filtering for date range {start_date} to {end_date}: {len(df)}")

    if df.empty:
        print("No data found for the selected date. Returning an empty report.")
        all_cols = list(df.columns) + ['District', 'State', 'digipin', 'Employee Id', 'first_counter_visit_datetime', 'last_counter_visit_datetime', 'late_start', 'worked_late']
        return pd.DataFrame(columns=all_cols)

    # --- Step 4: NEW TIME-BASED COLUMNS (Corrected Logic) ---
    print("Calculating daily first/last visit times and flags...")

    # Create a 'date' column to group by user AND day
    df['visit_date'] = df['CompletedOn'].dt.date

    # a) Group by user AND day to get the first/last visit for each day in the range
    df['first_counter_visit_datetime'] = df.groupby(['Task Owner Email', 'visit_date'])['CompletedOn'].transform('min')
    df['last_counter_visit_datetime'] = df.groupby(['Task Owner Email', 'visit_date'])['CompletedOn'].transform('max')

    # b) Identify the unique row index for the first and last visit of each user FOR EACH DAY
    first_visit_indices = df.loc[df.groupby(['Task Owner Email', 'visit_date'])['CompletedOn'].idxmin()].index
    last_visit_indices = df.loc[df.groupby(['Task Owner Email', 'visit_date'])['CompletedOn'].idxmax()].index
    
    # c) Define thresholds and initialize columns
    late_start_threshold = time(9, 15)
    late_finish_threshold = time(16, 0)
    df['late_start'] = pd.NA
    df['worked_late'] = pd.NA
    
    # d) Calculate flags based on the daily first/last visits
    df.loc[first_visit_indices, 'late_start'] = (df.loc[first_visit_indices, 'first_counter_visit_datetime'].dt.time > late_start_threshold).astype(int)
    df.loc[last_visit_indices, 'worked_late'] = (df.loc[last_visit_indices, 'last_counter_visit_datetime'].dt.time > late_finish_threshold).astype(int)

    df.drop(columns=['visit_date'], inplace=True) # dropping the helper 'visit_date' column
    
    # --- Step 5: SIMPLIFIED & DIRECT GEOCODING LOGIC ---
    print("Starting geocoding process with shapefile for all valid lat/long pairs...")

    # Create new columns for our results, initialized as empty
    df['District'] = pd.NA
    df['State'] = pd.NA

     # --- Part A: Process rows WITH lat/lon using the shapefile ---
    has_lat_lon_mask = df['Latitude'].notna() & df['Longitude'].notna()
    if has_lat_lon_mask.any():
        print(f"Found {has_lat_lon_mask.sum()} rows with coordinates to geocode.")
        points_to_process_gdf = gpd.GeoDataFrame(
            df[has_lat_lon_mask], 
            geometry=gpd.points_from_xy(df.loc[has_lat_lon_mask, 'Longitude'], df.loc[has_lat_lon_mask, 'Latitude']),
            crs="EPSG:4326"
        )
        merged_gdf = gpd.sjoin(
            points_to_process_gdf, 
            shapefile_for_join, 
            how="left", 
            predicate="within"
        )
        # Assign results back to the main DataFrame
        df.loc[has_lat_lon_mask, 'District'] = merged_gdf['found_district'].values
        df.loc[has_lat_lon_mask, 'State'] = merged_gdf['found_state'].values

    # --- Part B: Process rows WITHOUT lat/lon using operational columns ---
    no_lat_lon_mask = ~has_lat_lon_mask
    if no_lat_lon_mask.any():
        print(f"Found {no_lat_lon_mask.sum()} rows without coordinates. Falling back to operational columns.")
        # Use operational columns as a fallback
        df.loc[no_lat_lon_mask, 'District'] = df.loc[no_lat_lon_mask, 'Operational Cities'].str.strip().str.title()
        df.loc[no_lat_lon_mask, 'State'] = df.loc[no_lat_lon_mask, 'Operational States'].str.strip().str.title()
        
        # Further fallback: if 'Operational Cities' is also empty, try 'Taluka or District'
        fallback_mask = no_lat_lon_mask & df['District'].isna()
        df.loc[fallback_mask, 'District'] = df.loc[fallback_mask, 'Taluka or District'].str.strip().str.title()

    print("Conditional geocoding complete.")

    # Step 6: Process for 'digipin'
    print("Processing for digipin...")
    def safe_digipin(row):
        if pd.isna(row['Latitude']) or pd.isna(row['Longitude']):
            return None
        try:
            return get_digipin(row['Latitude'], row['Longitude'])
        except Exception:
            return None

    df['digipin'] = df.progress_apply(safe_digipin, axis=1)
    
    user_grouped = users.groupby("Email Address", as_index=False).agg({"Employee Id": "first"})
    df_final = pd.merge(left=df, right=user_grouped, left_on="Task Owner Email", right_on="Email Address", how="left")
    
    df_final['late_start'] = df_final['late_start'].astype('Int64').astype(str).replace('<NA>', '')
    df_final['worked_late'] = df_final['worked_late'].astype('Int64').astype(str).replace('<NA>', '')

    df_final.drop(columns=['geometry', 'index_right'], errors='ignore', inplace=True)
    print("Processing finished.")
    return df_final