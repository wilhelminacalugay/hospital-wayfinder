import ezdxf
import networkx as nx
import math
import re
import itertools
from datetime import datetime, timedelta, timezone
from shapely.geometry import LineString
from shapely.ops import unary_union
from itertools import islice

# ==========================================
# LITERATURE & ASSUMPTION VALUES 
# ==========================================
SPEED_FLAT = 1.4 
SPEED_STAIR_UP = 0.5 
SPEED_STAIR_DOWN = 0.7 

ELEV_WAIT_TIME = 45.0 
ELEV_DOOR_CYCLE = 12.0
ELEV_TIME_PER_FLOOR = 2.5 

PEAK_HOURS = [(8, 11), (16, 19)] 
CONGESTION_PENALTY = 1.35

# ==========================================
# FLOOR ELEVATION MAP
# ==========================================
FLOOR_ELEVATION = {
    "LG": 0,
    "UG": 1,
    "2F": 2,
    "3F": 3,
    "4F": 4,
    "5F": 5,
    "6F": 6
}

# ==========================================
# FLOOR DETECTION MATH (BACKEND)
# ==========================================
DETECTION_Y_BOUNDS = {
    "LG": [-170844.5250, -159463.4517],
    "UG": [-157112.6036, -145093.5759],
    "2F": [-141687.9535, -128588.0201],
    "3F": [-123925.8665, -112552.7519],
    "4F": [-110017.8566, -98644.7420],
    "5F": [-98097.2445, -84121.1446],
    "6F": [-80271.6670, -76308.3462],
}

def get_floor_from_y(y):
    """Magnetically snaps Y-coordinates to the closest floor to prevent fake bounces."""
    best_floor = "UG"
    min_dist = float('inf')
    
    for floor, (ymin, ymax) in DETECTION_Y_BOUNDS.items():
        # If perfectly inside the bounds
        if ymin <= y <= ymax:
            return floor
            
        # If outside, snap to the closest floor edge
        dist = min(abs(y - ymin), abs(y - ymax))
        if dist < min_dist:
            min_dist = dist
            best_floor = floor
            
    return best_floor

def calculate_distance(p1, p2):
    return math.sqrt((p2[0] - p1[0])**2 + (p2[1] - p1[1])**2)

def format_time(seconds):
    mins = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{mins}m {secs}s"

def count_turns(path):
    turns = 0
    for i in range(1, len(path) - 1):
        p1, p2, p3 = path[i-1], path[i], path[i+1]
        u = (p2[0]-p1[0], p2[1]-p1[1])
        v = (p3[0]-p2[0], p3[1]-p2[1])
        
        if (u[0]**2 + u[1]**2) == 0 or (v[0]**2 + v[1]**2) == 0: continue
        
        dot = u[0]*v[0] + u[1]*v[1]
        mag_u = math.sqrt(u[0]**2 + u[1]**2)
        mag_v = math.sqrt(v[0]**2 + v[1]**2)
        
        cos_theta = max(-1.0, min(1.0, dot / (mag_u * mag_v)))
        angle = math.degrees(math.acos(cos_theta))
        if angle > 45: turns += 1
    return turns

def apply_congestion(G):
    ph_time = datetime.now(timezone(timedelta(hours=8)))
    hour = ph_time.hour
    is_peak = any(start <= hour < end for start, end in PEAK_HOURS)
    
    if is_peak:
        for u, v, data in G.edges(data=True):
            labels = [G.nodes[u].get('label', ''), G.nodes[v].get('label', '')]
            if any(k in "".join(labels) for k in ["LOBBY", "WAITING", "MAIN ROAD", "ENTRY"]):
                data['weight'] *= CONGESTION_PENALTY
    return G

def build_hospital_graph(dxf_file_path):
    try:
        doc = ezdxf.readfile(dxf_file_path)
        msp = doc.modelspace()
    except Exception as e:
        return None, None

    G = nx.Graph()
    destinations = {}
    all_endpoints = set()

    # ==========================================
    # TRANSLATION DICTIONARY
    # ==========================================
    translations = {
        # ---------------- LOWER GROUND (LG) ----------------
        "DARK ROOM": "", "DRY GARBAGE STORAGE": "", "ELECTRICAL ROOM": "",
        "ELEVATOR 1 LG": "ELEVATOR_1_LG", "ELEVATOR 2 LG": "ELEVATOR_2_LG", "ELEVATOR 3 LG": "ELEVATOR_3_LG",
        "ELEVATOR LOBBY LG": "ELEVATOR_LOBBY_LG", "FILM FILE & STORAGE AREA": "", "GENSET": "", "MORGUE": "",
        "OXYGEN MANIFOLD ROOM": "", "PARKING": "", "PARKING PWD RAMP": "",
        "PARKING SLOT 1": "", "PARKING SLOT 2": "", "PARKING SLOT 3": "", "PARKING SLOT 4": "",
        "PARKING SLOT 5": "", "PARKING SLOT 6": "", "PARKING SLOT 7": "", "PARKING SLOT 8": "",
        "PARKING SLOT 9": "", "PARKING SLOT 10": "", "PARKING SLOT 11": "", "PARKING SLOT 12": "",
        "PARKING SLOT 13": "", "PARKING SLOT 14": "", "PARKING SLOT 15": "", "PARKING SLOT 16": "",
        "PARKING SLOT 17": "", "PARKING SLOT 18": "", "PARKING SLOT 19": "", "PARKING SLOT 20": "",
        "PARKING SLOT 21": "", "PARKING SLOT 22": "", "PARKING SLOT 23": "", "PARKING SLOT 24": "",
        "PARKING SLOT 25": "", "PARKING SLOT 26": "", "PARKING SLOT 27": "", "PARKING SLOT 28": "",
        "PARKING SLOT 29": "", "PARKING SLOT 30": "", "PARKING SLOT 31": "", "PARKING SLOT 32": "",
        "PARKING SLOT 33": "", "PARKING SLOT 34": "", "PARKING SLOT 35": "", "PARKING SLOT 36": "",
        "PUMP ROOM": "", "RADIOLOGIST": "", "SERVICE ELEVATOR LG": "SERVICE_ELEVATOR_LG",
        "STAIRS BACK LG": "STAIR_BACK_LG", "STAIRS FRONT LG": "STAIR_FRONT_LG", "STAIRS MIDDLE LG": "STAIR_MIDDLE_LG",
        "WET GARBAGE STORAGE": "", "X-RAY": "",

        # ---------------- UPPER GROUND (UG) ----------------
        "ADMITTING OFFICE": "", "BACK DROP- OFF": "", "BACK PWD RAMP": "", "BILLING/ PHILHEALTH": "",
        "BUDGET & FINANCE": "", "CAR RAMP": "", "DECONTAMINATION AREA": "",
        "ELEVATOR 1 UG": "ELEVATOR_1_UG", "ELEVATOR 2 UG": "ELEVATOR_2_UG", "ELEVATOR 3 UG": "ELEVATOR_3_UG",
        "ELEVATOR LOBBY UG": "ELEVATOR_LOBBY_UG", "EMERGENCY ROOM": "", "EMERGENCY ROOM ENTRY": "",
        "EMERGENCY ROOM EQUIPMENT & SUPPLY STORAGE AREA": "", "EMERGENCY ROOM FEMALE BATHROOM": "",
        "EMERGENCY ROOM LOUNGE": "", "EMERGENCY ROOM LOUNGE BATHROOM": "", "EMERGENCY ROOM MALE BATHROOM": "",
        "EMERGENCY ROOM NURSE STATION": "", "EMERGENCY ROOM WAITING AREA": "", "ENTRY": "",
        "EXAMINATION & TREATMENT AREA": "", "EXIT": "", "FEMALE BATHROOM UG": "", "INFORMATION UG": "",
        "JANITOR'S CLOSET UG": "", "MAIN DROP-OFF": "", "MAIN DROP-OFF PWD RAMP": "", "MAIN LOBBY": "",
        "MAIN ROAD": "", "MALE BATHROOM UG": "", "MINOR O.R.": "", "OBSERVATION AREA": "",
        "OUT-PATIENT DEPARTMENT DROP-OFF": "", "OUT-PATIENT DEPARTMENT PWD RAMP": "",
        "OUT-PATIENT WAITING AREA UG": "", "PHARMACY": "", "PWD BATHROOM UG": "", "SCRUB-UP": "",
        "SERVICE ELEVATOR UG": "SERVICE_ELEVATOR_UG", "SOCIAL SERVICE OFFICE": "", "STAFF DOCTORS": "",
        "STAFF DOCTORS BATHROOM": "", "STAIRS BACK UG": "STAIR_BACK_UG", "STAIRS FRONT UG": "STAIR_FRONT_UG",
        "STAIRS MIDDLE UG": "STAIR_MIDDLE_UG",

        # ---------------- 2ND FLOOR (2F) ----------------
        "ADMITTING & RECORDS AREA": "", "BLOOD STATION": "", "BREASTFEEDING AREA": "",
        "CAESARIAN DELIVERY ROOM": "", "CLEAN- UP BACK": "", "CLEAN- UP FRONT": "",
        "CLINIC 1": "", "CLINIC 2": "", "CONSULTATION": "", "COUNSELING ROOM": "", "CSSR": "",
        "DELIVERY ROOM": "", "DENTAL": "", "DOCTOR'S LOUNGE": "", "DOCTOR'S LOUNGE BATHROOM": "",
        "DRESSING AREA": "", "ELEVATOR 1 2F": "ELEVATOR_1_2F", "ELEVATOR 2 2F": "ELEVATOR_2_2F",
        "ELEVATOR 3 2F": "ELEVATOR_3_2F", "ELEVATOR LOBBY 2F": "ELEVATOR_LOBBY_2F", "EQUIPMENT & SUPPLY ROOM": "",
        "EXAMINATION & TREATMENT": "", "FAMILY ROOM": "", "FAMILY ROOM BATHROOM": "",
        "FEMALE BATHROOM 2F": "", "FEMALE DRESSING ROOM": "", "FEMALE DRESSING ROOM BATHROOM": "",
        "FRONT BALCONY 2F": "", "ICU": "", "ICU NURSE  STATION BATHROOM": "", "ICU NURSE STATION": "",
        "INFECTIOUS CHAMBER": "", "INFORMATION/ REGISTRATION": "", "LABOR ROOM": "",
        "LABOR ROOM BATHROOM": "", "LABORATORY": "", "LABORATORY BATHROOM": "", "MALE BATHROOM 2F": "",
        "MALE DRESSING ROOM": "", "MALE DRESSING ROOM BATHROOM": "", "MICROBIOLOGY ROOM": "",
        "MIDDLE BALCONY 2F": "", "NEWBORN CARE AREA": "", "NICU": "", "NICU NURSE STATION": "",
        "OFFICE ANETHESIA": "", "OFFICE DEPARTMENT HEAD (SURGERY)": "", "OPERATING AREA": "",
        "OPERATING AREA JANITOR'S CLOSET": "", "OPERATING AREA NURSE STATION BATHROOM": "",
        "OPERATING AREA NURSE STATION/ TREATMENT AREA": "", "OPERATION  ROOM 1": "", "OPERATION  ROOM 2": "",
        "OUT-PATIENT DEPARTMENT": "", "OUT-PATIENT DEPARTMENT FEMALE  BATHROOM": "",
        "OUT-PATIENT DEPARTMENT MALE  BATHROOM": "", "OUT-PATIENT DEPARTMENT NURSE STATION/ TREATMENT AREA": "",
        "OUT-PATIENT DEPARTMENT PANTRY": "", "OUT-PATIENT DEPARTMENT PANTRY BATHROOM": "",
        "PATHOLOGIST": "", "PATHOLOGIST BATHROOM": "", "PRAYER ROOM": "", "PRE- MATURE": "",
        "PWD BATHROOM 2F": "", "RECOVERY ROOM": "", "RESPIRATORY": "", "SCRUB-UP 2F": "",
        "SERVICE ELEVATOR 2F": "SERVICE_ELEVATOR_2F", "STAIRS BACK 2F": "STAIR_BACK_2F",
        "STAIRS FRONT 2F": "STAIR_FRONT_2F", "STAIRS MIDDLE 2F": "STAIR_MIDDLE_2F",
        "SUB- STERILIZING": "", "TREATMENT AREA": "", "WAITING AREA": "",

        # ---------------- 3RD FLOOR (3F) ----------------
        "ANTE ROOM 3F": "", "CLEAN LINEN/ CLEAN UTILITIES 1 3F": "", "CLEAN LINEN/ CLEAN UTILITIES 2 3F": "",
        "ELEVATOR 1 3F": "ELEVATOR_1_3F", "ELEVATOR 2 3F": "ELEVATOR_2_3F", "ELEVATOR 3 3F": "ELEVATOR_3_3F",
        "ELEVATOR LOBBY 3F": "ELEVATOR_LOBBY_3F", "FEMALE BATHROOM 3F": "", "FRONT BALCONY 3F": "",
        "ISOLATION ROOM 3F": "", "ISOLATION ROOM BATHROOM 3F": "", "JANITOR'S CLOSET 3F": "",
        "LOUNGE 1 3F": "", "LOUNGE 1 BATHROOM 3F": "", "LOUNGE 2 3F": "", "LOUNGE 2 BATHROOM 3F": "",
        "MALE BATHROOM 3F": "", "MIDDLE BALCONY 3F": "", "NURSE STATION/ TREATMENT AREA 1 3F": "",
        "NURSE STATION/ TREATMENT AREA 2 3F": "", "OFFICE INTERNAL MEDICINE 3F": "",
        "OFFICE OBSTETRICS & GYNECOLOGY 3F": "", "OFFICE PEDIATRICS 3F": "", "PANTRY 3F": "",
        "PANTRY BATHROOM 3F": "", "SERVICE ELEVATOR 3F": "SERVICE_ELEVATOR_3F",
        "SOILED LINEN/ SOILED UTILITIES 1 3F": "", "SOILED LINEN/ SOILED UTILITIES 2 3F": "",
        "STAIRS BACK 3F": "STAIR_BACK_3F", "STAIRS FRONT 3F": "STAIR_FRONT_3F", "STAIRS MIDDLE 3F": "STAIR_MIDDLE_3F",
        "WARD 1 3F": "", "WARD 1 BATHROOM 3F": "", "WARD 2 3F": "", "WARD 2 BATHROOM 3F": "",
        "WARD 3 3F": "", "WARD 3 BATHROOM 3F": "", "WARD 4 3F": "", "WARD 4 BATHROOM 3F": "",
        "WARD 5 3F": "", "WARD 5 BATHROOM 3F": "", "WARD 6 3F": "", "WARD 6 BATHROOM 3F": "",
        "WARD 7 3F": "", "WARD 7 BATHROOM 3F": "", "WARD 8 3F": "", "WARD 8 BATHROOM 3F": "",
        "WARD 9 3F": "", "WARD 9 BATHROOM 3F": "", "WARD 10 3F": "", "WARD 10 BATHROOM 3F": "",
        "WARD 11 3F": "", "WARD 11 BATHROOM 3F": "", "WARD 12 3F": "", "WARD 12 BATHROOM 3F": "",
        "WARD 13 3F": "", "WARD 13 BATHROOM 3F": "", "WARD 14 3F": "", "WARD 14 BATHROOM 3F": "",
        "WARD 15 3F": "", "WARD 15 BATHROOM 3F": "", "WARD 16 3F": "", "WARD 16 BATHROOM 3F": "",
        "WARD 17 3F": "", "WARD 17 BATHROOM 3F": "",

        # ---------------- 4TH FLOOR (4F) ----------------
        "ANTE ROOM 4F": "", "CLEAN LINEN/ CLEAN UTILITIES 1 4F": "", "CLEAN LINEN/ CLEAN UTILITIES 2 4F": "",
        "ELEVATOR 1 4F": "ELEVATOR_1_4F", "ELEVATOR 2 4F": "ELEVATOR_2_4F", "ELEVATOR 3 4F": "ELEVATOR_3_4F",
        "ELEVATOR LOBBY 4F": "ELEVATOR_LOBBY_4F", "FEMALE BATHROOM 4F": "", "FRONT BALCONY 4F": "",
        "ISOLATION ROOM 4F": "", "ISOLATION ROOM BATHROOM 4F": "", "JANITOR'S CLOSET 4F": "",
        "LOUNGE 1 4F": "", "LOUNGE 1 BATHROOM 4F": "", "LOUNGE 2 4F": "", "LOUNGE 2 BATHROOM 4F": "",
        "MALE BATHROOM 4F": "", "MIDDLE BALCONY 4F": "", "NURSE STATION/ TREATMENT AREA 1 4F": "",
        "NURSE STATION/ TREATMENT AREA 2 4F": "", "OFFICE INTERNAL MEDICINE 4F": "",
        "OFFICE OBSTETRICS & GYNECOLOGY 4F": "", "OFFICE PEDIATRICS 4F": "", "PANTRY 4F": "",
        "PANTRY BATHROOM 4F": "", "SERVICE ELEVATOR 4F": "SERVICE_ELEVATOR_4F",
        "SOILED LINEN/ SOILED UTILITIES 1 4F": "", "SOILED LINEN/ SOILED UTILITIES 2 4F": "",
        "STAIRS BACK 4F": "STAIR_BACK_4F", "STAIRS FRONT 4F": "STAIR_FRONT_4F", "STAIRS MIDDLE 4F": "STAIR_MIDDLE_4F",
        "WARD 1 4F": "", "WARD 1 BATHROOM 4F": "", "WARD 2 4F": "", "WARD 2 BATHROOM 4F": "",
        "WARD 3 4F": "", "WARD 3 BATHROOM 4F": "", "WARD 4 4F": "", "WARD 4 BATHROOM 4F": "",
        "WARD 5 4F": "", "WARD 5 BATHROOM 4F": "", "WARD 6 4F": "", "WARD 6 BATHROOM 4F": "",
        "WARD 7 4F": "", "WARD 7 BATHROOM 4F": "", "WARD 8 4F": "", "WARD 8 BATHROOM 4F": "",
        "WARD 9 4F": "", "WARD 9 BATHROOM 4F": "", "WARD 10 4F": "", "WARD 10 BATHROOM 4F": "",
        "WARD 11 4F": "", "WARD 11 BATHROOM 4F": "", "WARD 12 4F": "", "WARD 12 BATHROOM 4F": "",
        "WARD 13 4F": "", "WARD 13 BATHROOM 4F": "", "WARD 14 4F": "", "WARD 14 BATHROOM 4F": "",
        "WARD 15 4F": "", "WARD 15 BATHROOM 4F": "", "WARD 16 4F": "", "WARD 16 BATHROOM 4F": "",
        "WARD 17 4F": "", "WARD 17 BATHROOM 4F": "",

        # ---------------- 5TH FLOOR (5F) ----------------
        "ADMIN OFFICE": "", "ADMIN OFFICE BATHROOM": "", "CHIEF OF CLINICS": "", "CHIEF OF CLINICS BATHROOM": "",
        "CHIEF OF NURSE": "", "CLEAN LINEN/OFFICE": "", "COLD STORAGE": "", "CONFERENCE ROOM": "",
        "CONFERENCE ROOM BATHROOM": "", "COOKING AREA": "", "DECONTAMINATON": "", "DIET KITCHEN": "",
        "DIET KITCHEN STORAGE": "", "DIETARY": "", "DIETARY BATHROOM": "", "DIETICIAN": "",
        "DIETICIAN BATHROOM": "", "DIRECTOR'S OFFICE": "", "DIRECTOR'S OFFICE AND SECRETARY'S BATHROOM": "",
        "DIRECTOR'S OFFICE AND SECRETARY'S PANTRY": "", "DISHWASHING AREA": "", "DRY STORAGE": "",
        "ELEVATOR 1 5F": "ELEVATOR_1_5F", "ELEVATOR 2 5F": "ELEVATOR_2_5F", "ELEVATOR 3 5F": "ELEVATOR_3_5F",
        "ELEVATOR LOBBY 5F": "ELEVATOR_LOBBY_5F", "FEMALE BATHROOM 5F": "", "FOOD ASSEMBLY": "", "FOOD PREPARATION AREA": "",
        "GARBAGE DISPOSAL AREA": "", "H.R.M.O.": "", "HOUSEKEEPING": "", "MAINTENANCE OFFICE": "",
        "MALE BATHROOM 5F": "", "MEDICAL RECORDS": "", "MIDDLE BALCONY 5F": "", "PANTRY": "",
        "PANTRY BATHROOM": "", "PRESSING & IRONING AREA": "", "RECEIVING AREA": "", "ROOF DECK": "", 
        "SECRETARY": "", "SERVICE ELEVATOR 5F": "SERVICE_ELEVATOR_5F", "SORTING AREA": "", "SPECIAL DIET": "",
        "STAFF": "", "STAFF BATHROOM": "", "STAFF DINING/ CANTEEN": "", "STAFF DINING/ CANTEEN BATHROOM": "",
        "STAIRS BACK 5F": "STAIR_BACK_5F", "STAIRS FRONT 5F": "STAIR_FRONT_5F", "STAIRS MIDDLE 5F": "STAIR_MIDDLE_5F",
        "STORAGE": "", "STORAGE AREA": "",

        # ---------------- 6TH FLOOR (6F) ----------------
        "ELEVATOR MACHINE ROOM": "", "STAIRS BACK 6F": "STAIR_BACK_6F",
        "STAIRS FRONT 6F": "STAIR_FRONT_6F", "STAIRS MIDDLE 6F": "STAIR_MIDDLE_6F",
        "WATER TANK AREA 1": "", "WATER TANK AREA 2": "",
    }

    # ==========================================
    # 1. GROUP LINES BY DXF LAYER
    # ==========================================
    lines_by_layer = {}
    for entity in msp.query('LWPOLYLINE LINE'):
        # THIS is where layer_name is officially defined!
        layer_name = entity.dxf.layer.upper() 
        
        if layer_name not in lines_by_layer:
            lines_by_layer[layer_name] = []
            
        if entity.dxftype() == 'LINE':
            s, e = (round(entity.dxf.start.x, 1), round(entity.dxf.start.y, 1)), (round(entity.dxf.end.x, 1), round(entity.dxf.end.y, 1))
            if s != e: lines_by_layer[layer_name].append(LineString([s, e]))
        elif entity.dxftype() == 'LWPOLYLINE':
            pts = [(round(p[0], 1), round(p[1], 1)) for p in entity.get_points('xy')]
            for i in range(len(pts)-1):
                if pts[i] != pts[i+1]: lines_by_layer[layer_name].append(LineString([pts[i], pts[i+1]]))

    # ==========================================
    # 2. MERGE & BUILD GRAPH BY LAYER
    # ==========================================
    for layer_name, raw_lines in lines_by_layer.items(): 
        merged = unary_union(raw_lines)
        clean_lines = list(merged.geoms) if merged.geom_type == 'MultiLineString' else [merged]

        for line in clean_lines:
            coords = list(line.coords)
            for i in range(len(coords)-1):
                dist_m = calculate_distance(coords[i], coords[i+1]) / 1000.0
                
                G.add_node(coords[i], layer=layer_name)
                G.add_node(coords[i+1], layer=layer_name)
                G.add_edge(coords[i], coords[i+1], weight=dist_m / SPEED_FLAT)
                
                all_endpoints.update([coords[i], coords[i+1]])

    # ---------------------------------------------------------
    # 🚨 NEW: THE NODE FUSION ALGORITHM (CAD SLOP FIX)
    # ---------------------------------------------------------
    # Set this to your CAD tolerance. If your CAD is in millimeters, 
    # 100.0 means it will snap gaps up to 10cm apart.
    TOLERANCE = 150.0 
    
    mapping = {}
    current_nodes = list(G.nodes())
    
    for n in current_nodes:
        if n in mapping: 
            continue
        mapping[n] = n
        
        for other in current_nodes:
            if other in mapping: 
                continue
            if calculate_distance(n, other) <= TOLERANCE:
                mapping[other] = n # Magnetically map 'other' to 'n'
                
    # Fuse the graph together
    G = nx.relabel_nodes(G, mapping, copy=True)
    G.remove_edges_from(nx.selfloop_edges(G)) # Destroy overlapping stubs
    
    # Update the endpoints so the text parser snaps to the fixed grid
    all_endpoints = set(G.nodes())
    # ---------------------------------------------------------


    # ==========================================
    # 3. PARSE TEXT LABELS (Leave this part exactly as you have it)
    # ==========================================
    for entity in msp.query('TEXT MTEXT'):
        # ... (rest of your text code) ...
        txt = entity.plain_text().strip().upper() if entity.dxftype() == 'MTEXT' else entity.dxf.text.strip().upper()
        
        # Eradicate invisible CAD typos
        txt = re.sub(r'\s+', ' ', txt)
        
        # If it is blank in the dictionary, KEEP THE ORIGINAL NAME.
        if txt in translations and translations[txt] != "": 
            txt = translations[txt]
            
        if hasattr(entity.dxf, 'insert') and txt:
            pos = (round(entity.dxf.insert.x, 1), round(entity.dxf.insert.y, 1))
            if all_endpoints:
                closest = min(all_endpoints, key=lambda pt: calculate_distance(pos, pt))
                
                destinations[txt] = closest
                
                # 3. FIX: Only protect actual shafts (using the underscore!)
                existing_label = G.nodes[closest].get('label', '')
                is_existing_transit = "ELEV_" in existing_label or "STAIR_" in existing_label
                is_new_transit = "ELEV_" in txt or "STAIR_" in txt
                
                if not is_existing_transit or is_new_transit:
                    G.nodes[closest]['label'] = txt
            
        if hasattr(entity.dxf, 'insert') and txt:
            pos = (round(entity.dxf.insert.x, 1), round(entity.dxf.insert.y, 1))
            if all_endpoints:
                closest = min(all_endpoints, key=lambda pt: calculate_distance(pos, pt))
                
                # Always add the room to destinations so it can be searched
                destinations[txt] = closest
                
                # 3. Protect Transit Nodes from being overwritten by nearby rooms
                existing_label = G.nodes[closest].get('label', '')
                is_existing_transit = "ELEV" in existing_label or "STAIR" in existing_label
                is_new_transit = "ELEV" in txt or "STAIR" in txt
                
                # Only update the graph node's label if it doesn't destroy a transit tag
                if not is_existing_transit or is_new_transit:
                    G.nodes[closest]['label'] = txt

    # ==========================================
    # 3. THE "LOBBY HUB" PORTAL BUILDER
    # ==========================================
    portals = {}
    for name, pt in destinations.items():
        # Only build vertical shafts for Lobbies, Stairs, and Service Elevators
        if "ELEVATOR_LOBBY_" in name or "STAIR_" in name or "SERVICE_ELEVATOR_" in name:
            
            # THE FIX: Updated RegEx to capture your new _4F format!
            m = re.search(r'(.*)_(LG|UG|\d+F)$', name) 
            
            if m:
                base, floor = m.group(1), m.group(2)
                # THE FIX: Updated order mapping to use 2F, 3F, etc.
                order = {"LG":-1, "UG":0, "2F":2, "3F":3, "4F":4, "5F":5, "6F":6} 
                if base not in portals: portals[base] = []
                portals[base].append((order.get(floor, 99), name, pt))

    for base, floors in portals.items():
        floors.sort(key=lambda x: x[0])
        for i in range(len(floors)-1):
            f1_n, n1, p1 = floors[i]; f2_n, n2, p2 = floors[i+1]
            diff = abs(f2_n - f1_n)
            
            if "STAIR" in base:
                cost = (diff * 3.5) / SPEED_STAIR_UP 
            else:
                cost = ELEV_WAIT_TIME + ELEV_DOOR_CYCLE + (diff * ELEV_TIME_PER_FLOOR)
                
            G.add_edge(p1, p2, weight=cost)

    return apply_congestion(G), destinations

def get_restrictions(role):
    """
    Returns a list of text keywords that the selected role is FORBIDDEN from entering.
    Currently set to allow EVERYTHING for all roles (Development Mode).
    """
    # By returning an empty list for everyone, no nodes are ever removed from the graph.
    # Every role (Patient, PWD, Staff, etc.) has full access to Stairs, Elevators, and all rooms.
    return []

# --- THE FULLY ASSEMBLED SMART ITINERARY GENERATOR ---
def find_optimized_paths(graph, destinations, start, end, role):
    if start not in destinations or end not in destinations:
        return "Start or Destination not found in database.", []

    s_node, e_node = destinations[start], destinations[end]
    restricted = [n for n, d in graph.nodes(data=True) if any(k in d.get('label','') for k in get_restrictions(role))]
    
    safe_G = graph.copy()
    safe_G.remove_nodes_from(restricted)
    
    if s_node not in safe_G or e_node not in safe_G:
        return f"Access Denied: This route crosses through restricted areas for a {role}.", []

    # 1. POISON THE GRAPH (Using Underscores!)
    routing_G = safe_G.copy()
    for u, v, d in routing_G.edges(data=True):
        u_label = routing_G.nodes[u].get('label', '').upper()
        v_label = routing_G.nodes[v].get('label', '').upper()
        
        u_is_transit = "ELEVATOR_" in u_label or "STAIR_" in u_label
        v_is_transit = "ELEVATOR_" in v_label or "STAIR_" in v_label
        
        if u_is_transit != v_is_transit:
            d['weight'] += 50000 

    try:
        raw_paths = list(itertools.islice(nx.shortest_simple_paths(routing_G, s_node, e_node, weight='weight'), 50))
        
        scored_paths = []
        
        for p in raw_paths:
            # ---------------------------------------------------------
            # FILTER 1: UNIDIRECTIONAL & ANTI-BOUNCE
            # ---------------------------------------------------------
            visited_floors = []
            for node in p:
                floor = get_floor_from_y(node[1])
                if not visited_floors or visited_floors[-1] != floor:
                    visited_floors.append(floor)
            
            is_valid = True
            
            if len(visited_floors) != len(set(visited_floors)):
                is_valid = False
                
            if is_valid and len(visited_floors) > 2:
                elevations = [FLOOR_ELEVATION.get(f, -1) for f in visited_floors]
                direction = None
                
                for k in range(len(elevations) - 1):
                    diff = elevations[k+1] - elevations[k]
                    if diff == 0: continue
                    current_dir = "UP" if diff > 0 else "DOWN"
                    
                    if direction is None:
                        direction = current_dir
                    elif direction != current_dir:
                        is_valid = False 
                        break
            
            if not is_valid:
                pass # DEBUG: We disabled the Anti-Bounce kill switch! 
                    
            # ---------------------------------------------------------
            # FILTER 2: THE STRICT TRANSFER BAN
            # ---------------------------------------------------------
            transit_hops = 0
            was_on_transit = False
            uses_elev = False
            uses_stair = False
            
            for node in p:
                label = safe_G.nodes[node].get('label', '').upper()
                
                # FIX: Look for the underscore!
                is_elev = "ELEVATOR_" in label
                is_stair = "STAIR_" in label
                is_transit = is_elev or is_stair
                
                if is_elev: uses_elev = True
                if is_stair: uses_stair = True
                
                if is_transit and not was_on_transit:
                    transit_hops += 1
                was_on_transit = is_transit
            
            if transit_hops > 1:
                pass # DEBUG: We disabled the Transit Transfer kill switch!
            
            is_mixed = 1 if (uses_elev and uses_stair) else 0
            real_weight = sum(safe_G[p[i]][p[i+1]]['weight'] for i in range(len(p)-1))
            
            scored_paths.append({
                'path': p,
                'transit_hops': transit_hops,
                'is_mixed': is_mixed,
                'weight': real_weight
            })
            
        if not scored_paths:
            return "No logical alternatives found. Graph connection error.", []
            
        # 2. THE GOLDEN SORT
        scored_paths.sort(key=lambda x: (x['is_mixed'], x['transit_hops'], x['weight']))
        
        # 3. ANTI-CLONE FILTER
        logical_paths = []
        for sp in scored_paths:
            p = sp['path']
            is_clone = False
            p_set = set(p)
            for approved in logical_paths:
                approved_set = set(approved)
                overlap = len(p_set.intersection(approved_set)) / min(len(p_set), len(approved_set))
                if overlap > 0.80:
                    is_clone = True
                    break
                    
            if not is_clone:
                logical_paths.append(p)
                
            if len(logical_paths) == 3:
                break
                
        final_paths = logical_paths

        # 4. ITINERARY BUILDER
        output = f"[ 🗺️ WAYFINDING ITINERARY FOR {role} ]\n\n"
        
        for i, path in enumerate(final_paths, 1):
            step_sequence = []
            current_floor = get_floor_from_y(path[0][1])
            step_sequence.append(f"Start at {start}")
            
            uses_stairs = False
            uses_elev = False
            
            for j, node in enumerate(path):
                node_floor = get_floor_from_y(node[1])
                node_label = safe_G.nodes[node].get('label', '').upper()
                
                if node_floor != current_floor:
                    transit_method = "Stairs/Elevator" 
                    # FIX: Look for the underscore for UI generation too
                    if "ELEVATOR_" in node_label:
                        transit_method = "Elevator"
                        uses_elev = True
                    elif "STAIR_" in node_label:
                        transit_method = "Stairs"
                        uses_stairs = True
                    elif j > 0:
                        prev_label = safe_G.nodes[path[j-1]].get('label', '').upper()
                        if "ELEVATOR_" in prev_label:
                            transit_method = "Elevator"
                            uses_elev = True
                        elif "STAIR_" in prev_label:
                            transit_method = "Stairs"
                            uses_stairs = True
                            
                    step_sequence.append(f"Take {transit_method} to {node_floor}")
                    current_floor = node_floor
                
                if node_label and node_label not in [start, end]:
                    if "STAIR_" not in node_label and "ELEVATOR_" not in node_label:
                        step_sequence.append(f"Pass by {node_label}")
                            
            step_sequence.append(f"Arrive at {end}")
            
            if uses_stairs and uses_elev:
                route_tag = "[Mixed: Stairs & Elevator]"
            elif uses_stairs:
                route_tag = "[Stairs Route]"
            elif uses_elev:
                route_tag = "[Elevator Route]"
            else:
                route_tag = "[Same Floor - Direct Walk]"
            
            output += f"OPTION {i} {route_tag}:\n"
            output += " ➔ ".join(step_sequence) + "\n\n"
            
        return output, final_paths
        
    except nx.NetworkXNoPath:
        return f"[{role} ERROR] No valid path found.", []

# We removed the terminal while loop at the bottom because Streamlit handles the interface now!
