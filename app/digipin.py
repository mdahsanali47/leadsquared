import math

# Constants translated from the JavaScript source
DIGIPIN_GRID = [
    ['F', 'C', '9', '8'],
    ['J', '3', '2', '7'],
    ['K', '4', '5', '6'],
    ['L', 'M', 'P', 'T']
]

BOUNDS = {
    'minLat': 2.5,
    'maxLat': 38.5,
    'minLon': 63.5,
    'maxLon': 99.5
}

# For faster decoding, create a lookup map from character to its (row, col) index
# This is more efficient than searching the grid every time.
CHAR_TO_INDEX = {
    char: (r, c)
    for r, row_list in enumerate(DIGIPIN_GRID)
    for c, char in enumerate(row_list)
}

def get_digipin(lat: float, lon: float) -> str:
    """
    Encodes a latitude and longitude into a 10-digit alphanumeric DIGIPIN.

    Args:
        lat: The latitude coordinate.
        lon: The longitude coordinate.

    Returns:
        The formatted 10-character DIGIPIN string (e.g., "4P3-JK8-52C9").

    Raises:
        ValueError: If the latitude or longitude is out of the defined bounds.
    """
    if not (BOUNDS['minLat'] <= lat <= BOUNDS['maxLat']):
        raise ValueError('Latitude is out of the valid range for DIGIPIN.')
    if not (BOUNDS['minLon'] <= lon <= BOUNDS['maxLon']):
        raise ValueError('Longitude is out of the valid range for DIGIPIN.')

    min_lat, max_lat = BOUNDS['minLat'], BOUNDS['maxLat']
    min_lon, max_lon = BOUNDS['minLon'], BOUNDS['maxLon']

    digipin_chars = []

    for _ in range(10):
        lat_div = (max_lat - min_lat) / 4
        lon_div = (max_lon - min_lon) / 4

        # Calculate column index (standard)
        col = math.floor((lon - min_lon) / lon_div)
        # Calculate row index (reversed logic as per original source)
        row = 3 - math.floor((lat - min_lat) / lat_div)

        # Clamp values to ensure they are within the 0-3 range, handling edge cases
        row = max(0, min(row, 3))
        col = max(0, min(col, 3))

        digipin_chars.append(DIGIPIN_GRID[row][col])

        # Update (zoom into) the bounding box for the next iteration
        # Latitude update uses reversed logic
        new_max_lat = min_lat + lat_div * (4 - row)
        new_min_lat = min_lat + lat_div * (3 - row)
        
        # Longitude update is standard
        new_min_lon = min_lon + lon_div * col
        new_max_lon = new_min_lon + lon_div
        
        min_lat, max_lat = new_min_lat, new_max_lat
        min_lon, max_lon = new_min_lon, new_max_lon

    # Add hyphens for readability, matching the standard format
    return f"{''.join(digipin_chars[:3])}-{''.join(digipin_chars[3:6])}-{''.join(digipin_chars[6:])}"


def get_lat_lng_from_digipin(digipin: str) -> dict:
    """
    Decodes a DIGIPIN back into its central latitude and longitude.

    Args:
        digipin: The 10-character DIGIPIN string (hyphens are optional).

    Returns:
        A dictionary containing the 'latitude' and 'longitude' as strings
        formatted to 6 decimal places.

    Raises:
        ValueError: If the DIGIPIN is invalid (wrong length or characters).
    """
    pin = digipin.replace('-', '')
    if len(pin) != 10:
        raise ValueError('Invalid DIGIPIN: Must contain 10 alphanumeric characters.')

    min_lat, max_lat = BOUNDS['minLat'], BOUNDS['maxLat']
    min_lon, max_lon = BOUNDS['minLon'], BOUNDS['maxLon']

    for char in pin:
        if char not in CHAR_TO_INDEX:
            raise ValueError(f"Invalid character '{char}' in DIGIPIN.")
        
        ri, ci = CHAR_TO_INDEX[char]

        lat_div = (max_lat - min_lat) / 4
        lon_div = (max_lon - min_lon) / 4

        # Update bounding box based on the character's grid position
        # Latitude uses reversed logic (subtracting from max_lat)
        new_min_lat = max_lat - lat_div * (ri + 1)
        new_max_lat = max_lat - lat_div * ri

        # Longitude is standard
        new_min_lon = min_lon + lon_div * ci
        new_max_lon = min_lon + lon_div * (ci + 1)
        
        min_lat, max_lat = new_min_lat, new_max_lat
        min_lon, max_lon = new_min_lon, new_max_lon

    # Calculate the center of the final, small bounding box
    center_lat = (min_lat + max_lat) / 2
    center_lon = (min_lon + max_lon) / 2

    return {
        'latitude': f"{center_lat:.6f}",
        'longitude': f"{center_lon:.6f}"
    }