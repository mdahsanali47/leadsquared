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
        
        # Safely get the dictionary of districts for the given state.
        # This returns None if the state isn't in the mapping file OR if its value is null.
        district_map_for_state = mapping_data.get(state_name)

        # Now, check if we got a valid dictionary back (i.e., it's not None).
        if district_map_for_state:
            # If we did, then try to get the mapped district name.
            # If the district isn't in this sub-dictionary, return its original name.
            return district_map_for_state.get(district_name, district_name)
        
        # If the state wasn't found or its value was None, return the original district name.
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

# --- Load and Prepare Shapefile ONCE on Application Startup ---
shapefile_for_join = load_and_prepare_shapefile()

def parse_mixed_formats(series, formats):
    """
    Tries to parse a pandas Series with a list of different date formats.
    """
    # Start with an empty series to hold the results
    parsed_series = pd.Series(pd.NaT, index=series.index)
    to_parse = series.copy()

    for fmt in formats:
        converted = pd.to_datetime(to_parse, format=fmt, errors='coerce')
        # Update our results with the successfully converted dates
        parsed_series = parsed_series.fillna(converted)
        
        # Update the list of strings that still need parsing
        # (i.e., remove the ones we just successfully converted)
        to_parse = to_parse[converted.isna()]

    # If any strings are left over after trying all formats, try one last time automatically
    if not to_parse.empty:
        last_try = pd.to_datetime(to_parse, errors='coerce')
        parsed_series = parsed_series.fillna(last_try)

    return parsed_series

def run_processing_pipeline(planned_visit_file, unplanned_visit_file, counters_file, users_file, filter_date_str: str):
    """
    Main function to execute the entire data processing logic.
    This version IGNORES operational city/state columns and relies 100% on the shapefile for geocoding.
    """
    if shapefile_for_join is None:
        raise RuntimeError("Shapefile is not loaded or prepared correctly. Cannot process data.")

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

    # Filter the DataFrame to keep only records for the selected date
    target_date = pd.to_datetime(filter_date_str).date()
    df = df[df['CompletedOn'].dt.date == target_date].copy()
    print(f"Record count after filtering for date {target_date}: {len(df)}")

    if df.empty:
        print("No data found for the selected date. Returning an empty report.")
        return pd.DataFrame(columns=common_cols + ['District', 'State', 'digipin', 'Employee Id', 'first_counter_visit_datetime', 'late'])

    # --- Step 4: NEW TIME-BASED COLUMNS (Corrected Logic) ---
    print("Calculating first visit time and late flag...")

    # a) Create the 'first_counter_visit_datetime' column. This correctly shows the first visit time for all rows of a user.
    df['first_counter_visit_datetime'] = df.groupby('Task Owner Email')['CompletedOn'].transform('min')

    # b) Identify the specific ROW that corresponds to the first visit.
    # A row is a "first visit" if its 'CompletedOn' time equals the 'first_counter_visit_datetime'.
    # We use drop_duplicates because a user could have two visits at the exact same first time. We only mark one.
    first_visit_indices = df[df['CompletedOn'] == df['first_counter_visit_datetime']].drop_duplicates(subset=['Task Owner Email']).index

    # c) Calculate the 'late' flag ONLY for these first-visit rows.
    late_threshold = time(9, 30)
    
    # Initialize the 'late' column with NA (which becomes blank in CSV) to handle empty values.
    # We use a float type to accommodate NA.
    df['late'] = pd.NA
    
    # For the identified first visit rows, calculate 1 if late, 0 if not.
    df.loc[first_visit_indices, 'late'] = (df.loc[first_visit_indices, 'first_counter_visit_datetime'].dt.time > late_threshold).astype(int)
    
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
    
    # Convert 'late' column to a string to control the output format if desired, e.g., '1.0' -> '1'
    # This also handles the NA values gracefully, turning them into empty strings in the CSV.
    df_final['late'] = df_final['late'].astype('Int64').astype(str).replace('<NA>', '')

    df_final.drop(columns=['geometry', 'index_right'], errors='ignore', inplace=True)
    print("Processing finished.")
    return df_final