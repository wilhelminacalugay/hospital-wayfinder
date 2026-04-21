import ezdxf
import networkx as nx
import math
import re
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
        "ELEVATOR 1 LG": "ELEV_1_LG", "ELEVATOR 2 LG": "ELEV_2_LG", "ELEVATOR 3 LG": "ELEV_3_LG",
        "ELEVATOR LOBBY LG": "", "FILM FILE & STORAGE AREA": "", "GENSET": "", "MORGUE": "",
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
        "PUMP ROOM": "", "RADIOLOGIST": "", "SERVICE ELEVATOR LG": "SERVICE_ELEV_LG",
        "STAIRS BACK LG": "STAIR_BACK_LG", "STAIRS FRONT LG": "STAIR_FRONT_LG", "STAIRS MIDDLE LG": "STAIR_MIDDLE_LG",
        "WET GARBAGE STORAGE": "", "X-RAY": "",

        # ---------------- UPPER GROUND (UG) ----------------
        "ADMITTING OFFICE": "", "BACK DROP- OFF": "", "BACK PWD RAMP": "", "BILLING/ PHILHEALTH": "",
        "BUDGET & FINANCE": "", "CAR RAMP": "", "DECONTAMINATION AREA": "",
        "ELEVATOR 1 UG": "ELEV_1_UG", "ELEVATOR 2 UG": "ELEV_2_UG", "ELEVATOR 3 UG": "ELEV_3_UG",
        "ELEVATOR LOBBY UG": "", "EMERGENCY ROOM": "", "EMERGENCY ROOM ENTRY": "",
        "EMERGENCY ROOM EQUIPMENT & SUPPLY STORAGE AREA": "", "EMERGENCY ROOM FEMALE BATHROOM": "",
        "EMERGENCY ROOM LOUNGE": "", "EMERGENCY ROOM LOUNGE BATHROOM": "", "EMERGENCY ROOM MALE BATHROOM": "",
        "EMERGENCY ROOM NURSE STATION": "", "EMERGENCY ROOM WAITING AREA": "", "ENTRY": "",
        "EXAMINATION & TREATMENT AREA": "", "EXIT": "", "FEMALE BATHROOM UG": "", "INFORMATION UG": "",
        "JANITOR'S CLOSET UG": "", "MAIN DROP-OFF": "", "MAIN DROP-OFF PWD RAMP": "", "MAIN LOBBY": "",
        "MAIN ROAD": "", "MALE BATHROOM UG": "", "MINOR O.R.": "", "OBSERVATION AREA": "",
        "OUT-PATIENT DEPARTMENT DROP-OFF": "", "OUT-PATIENT DEPARTMENT PWD RAMP": "",
        "OUT-PATIENT WAITING AREA UG": "", "PHARMACY": "", "PWD BATHROOM UG": "", "SCRUB-UP": "",
        "SERVICE ELEVATOR UG": "SERVICE_ELEV_UG", "SOCIAL SERVICE OFFICE": "", "STAFF DOCTORS": "",
        "STAFF DOCTORS BATHROOM": "", "STAIRS BACK UG": "STAIR_BACK_UG", "STAIRS FRONT UG": "STAIR_FRONT_UG",
        "STAIRS MIDDLE UG": "STAIR_MIDDLE_UG",

        # ---------------- 2ND FLOOR (2F) ----------------
        "ADMITTING & RECORDS AREA": "", "BLOOD STATION": "", "BREASTFEEDING AREA": "",
        "CAESARIAN DELIVERY ROOM": "", "CLEAN- UP BACK": "", "CLEAN- UP FRONT": "",
        "CLINIC 1": "", "CLINIC 2": "", "CONSULTATION": "", "COUNSELING ROOM": "", "CSSR": "",
        "DELIVERY ROOM": "", "DENTAL": "", "DOCTOR'S LOUNGE": "", "DOCTOR'S LOUNGE BATHROOM": "",
        "DRESSING AREA": "", "ELEVATOR 1 2F": "ELEV_1_F2", "ELEVATOR 2 2F": "ELEV_2_F2",
        "ELEVATOR 3 2F": "ELEV_3_F2", "ELEVATOR LOBBY 2F": "", "EQUIPMENT & SUPPLY ROOM": "",
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
        "SERVICE ELEVATOR 2F": "SERVICE_ELEV_F2", "STAIRS BACK 2F": "STAIR_BACK_F2",
        "STAIRS FRONT 2F": "STAIR_FRONT_F2", "STAIRS MIDDLE 2F": "STAIR_MIDDLE_F2",
        "SUB- STERILIZING": "", "TREATMENT AREA": "", "WAITING AREA": "",

        # ---------------- 3RD FLOOR (3F) ----------------
        "ANTE ROOM 3F": "", "CLEAN LINEN/ CLEAN UTILITIES 1 3F": "", "CLEAN LINEN/ CLEAN UTILITIES 2 3F": "",
        "ELEVATOR 1 3F": "ELEV_1_F3", "ELEVATOR 2 3F": "ELEV_2_F3", "ELEVATOR 3 3F": "ELEV_3_F3",
        "ELEVATOR LOBBY 3F": "", "FEMALE BATHROOM 3F": "", "FRONT BALCONY 3F": "",
        "ISOLATION ROOM 3F": "", "ISOLATION ROOM BATHROOM 3F": "", "JANITOR'S CLOSET 3F": "",
        "LOUNGE 1 3F": "", "LOUNGE 1 BATHROOM 3F": "", "LOUNGE 2 3F": "", "LOUNGE 2 BATHROOM 3F": "",
        "MALE BATHROOM 3F": "", "MIDDLE BALCONY 3F": "", "NURSE STATION/ TREATMENT AREA 1 3F": "",
        "NURSE STATION/ TREATMENT AREA 2 3F": "", "OFFICE INTERNAL MEDICINE 3F": "",
        "OFFICE OBSTETRICS & GYNECOLOGY 3F": "", "OFFICE PEDIATRICS 3F": "", "PANTRY 3F": "",
        "PANTRY BATHROOM 3F": "", "SERVICE ELEVATOR 3F": "SERVICE_ELEV_F3",
        "SOILED LINEN/ SOILED UTILITIES 1 3F": "", "SOILED LINEN/ SOILED UTILITIES 2 3F": "",
        "STAIRS BACK 3F": "STAIR_BACK_F3", "STAIRS FRONT 3F": "STAIR_FRONT_F3", "STAIRS MIDDLE 3F": "STAIR_MIDDLE_F3",
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
        "ELEVATOR 1 4F": "ELEV_1_F4", "ELEVATOR 2 4F": "ELEV_2_F4", "ELEVATOR 3 4F": "ELEV_3_F4",
        "ELEVATOR LOBBY 4F": "", "FEMALE BATHROOM 4F": "", "FRONT BALCONY 4F": "",
        "ISOLATION ROOM 4F": "", "ISOLATION ROOM BATHROOM 4F": "", "JANITOR'S CLOSET 4F": "",
        "LOUNGE 1 4F": "", "LOUNGE 1 BATHROOM 4F": "", "LOUNGE 2 4F": "", "LOUNGE 2 BATHROOM 4F": "",
        "MALE BATHROOM 4F": "", "MIDDLE BALCONY 4F": "", "NURSE STATION/ TREATMENT AREA 1 4F": "",
        "NURSE STATION/ TREATMENT AREA 2 4F": "", "OFFICE INTERNAL MEDICINE 4F": "",
        "OFFICE OBSTETRICS & GYNECOLOGY 4F": "", "OFFICE PEDIATRICS 4F": "", "PANTRY 4F": "",
        "PANTRY BATHROOM 4F": "", "SERVICE ELEVATOR 4F": "SERVICE_ELEV_F4",
        "SOILED LINEN/ SOILED UTILITIES 1 4F": "", "SOILED LINEN/ SOILED UTILITIES 2 4F": "",
        "STAIRS BACK 4F": "STAIR_BACK_F4", "STAIRS FRONT 4F": "STAIR_FRONT_F4", "STAIRS MIDDLE 4F": "STAIR_MIDDLE_F4",
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
        "ELEVATOR 1 5F": "ELEV_1_F5", "ELEVATOR 2 5F": "ELEV_2_F5", "ELEVATOR 3 5F": "ELEV_3_F5",
        "ELEVATOR LOBBY 5F": "", "FEMALE BATHROOM 5F": "", "FOOD ASSEMBLY": "", "FOOD PREPARATION AREA": "",
        "GARBAGE DISPOSAL AREA": "", "H.R.M.O.": "", "HOUSEKEEPING": "", "MAINTENANCE OFFICE": "",
        "MALE BATHROOM 5F": "", "MEDICAL RECORDS": "", "MIDDLE BALCONY 5F": "", "PANTRY": "",
        "PANTRY BATHROOM": "", "PRESSING & IRONING AREA": "", "RECEIVING AREA": "", "ROOF DECK": "", 
        "SECRETARY": "", "SERVICE ELEVATOR 5F": "SERVICE_ELEV_F5", "SORTING AREA": "", "SPECIAL DIET": "",
        "STAFF": "", "STAFF BATHROOM": "", "STAFF DINING/ CANTEEN": "", "STAFF DINING/ CANTEEN BATHROOM": "",
        "STAIRS BACK 5F": "STAIR_BACK_F5", "STAIRS FRONT 5F": "STAIR_FRONT_F5", "STAIRS MIDDLE 5F": "STAIR_MIDDLE_F5",
        "STORAGE": "", "STORAGE AREA": "",

        # ---------------- 6TH FLOOR (6F) ----------------
        "ELEVATOR MACHINE ROOM": "", "STAIRS BACK 6F": "STAIR_BACK_F6",
        "STAIRS FRONT 6F": "STAIR_FRONT_F6", "STAIRS MIDDLE 6F": "STAIR_MIDDLE_F6",
        "WATER TANK AREA 1": "", "WATER TANK AREA 2": "",
    }

    raw_lines = []
    for entity in msp.query('LWPOLYLINE LINE'):
        if entity.dxftype() == 'LINE':
            s, e = (round(entity.dxf.start.x, 1), round(entity.dxf.start.y, 1)), (round(entity.dxf.end.x, 1), round(entity.dxf.end.y, 1))
            if s != e: raw_lines.append(LineString([s, e]))
        elif entity.dxftype() == 'LWPOLYLINE':
            pts = [(round(p[0], 1), round(p[1], 1)) for p in entity.get_points('xy')]
            for i in range(len(pts)-1):
                if pts[i] != pts[i+1]: raw_lines.append(LineString([pts[i], pts[i+1]]))

    merged = unary_union(raw_lines)
    clean_lines = list(merged.geoms) if merged.geom_type == 'MultiLineString' else [merged]

    for line in clean_lines:
        coords = list(line.coords)
        for i in range(len(coords)-1):
            dist_m = calculate_distance(coords[i], coords[i+1]) / 1000.0
            G.add_edge(coords[i], coords[i+1], weight=dist_m / SPEED_FLAT)
            all_endpoints.update([coords[i], coords[i+1]])

    for entity in msp.query('TEXT MTEXT'):
        txt = entity.plain_text().strip().upper() if entity.dxftype() == 'MTEXT' else entity.dxf.text.strip().upper()
        txt = txt.replace('\n', ' ').replace('\r', '')
        
        if txt in translations and translations[txt] != "": txt = translations[txt]
        if hasattr(entity.dxf, 'insert') and txt:
            pos = (round(entity.dxf.insert.x, 1), round(entity.dxf.insert.y, 1))
            if all_endpoints:
                closest = min(all_endpoints, key=lambda pt: calculate_distance(pos, pt))
                destinations[txt] = closest
                G.nodes[closest]['label'] = txt

    portals = {}
    for name, pt in destinations.items():
        if "STAIR" in name or "ELEV" in name:
            m = re.search(r'(.*)_(LG|UG|F\d+)$', name)
            if m:
                base, floor = m.group(1), m.group(2)
                order = {"LG":-1, "UG":0, "F1":1, "F2":2, "F3":3, "F4":4, "F5":5, "F6":6}
                if base not in portals: portals[base] = []
                portals[base].append((order.get(floor, 99), name, pt))

    for base, floors in portals.items():
        floors.sort(key=lambda x: x[0])
        for i in range(len(floors)-1):
            f1_n, n1, p1 = floors[i]; f2_n, n2, p2 = floors[i+1]
            diff = abs(f2_n - f1_n)
            cost = (diff*3.5)/SPEED_STAIR_UP if "STAIR" in base else ELEV_WAIT_TIME+ELEV_DOOR_CYCLE+(diff*ELEV_TIME_PER_FLOOR)
            G.add_edge(p1, p2, weight=cost)

    return apply_congestion(G), destinations

def get_restrictions(role):
    # Base areas no regular person should enter
    common = ["STAFF", "SERVICE", "CSSR", "CLEAN LINEN", "SOILED", "DIET KITCHEN", "MORGUE", "OPERATING AREA"]
    roles = {
        "DOCTOR": [], # Doctors go anywhere
        "STAFF": ["DOCTOR'S LOUNGE"],
        "PATIENT": common,
        "VISITOR": common + ["ICU", "NICU", "ISOLATION"],
        "PWD": common + ["ICU", "NICU", "ISOLATION", "STAIR"] # PWD avoids stairs
    }
    return roles.get(role, common)

# --- THE FIX: This function now officially accepts 5 arguments! ---
def find_optimized_paths(graph, destinations, start, end, role):
    if start not in destinations or end not in destinations:
        return "Start or Destination not found in database."

    s_node, e_node = destinations[start], destinations[end]
    restricted = [n for n, d in graph.nodes(data=True) if any(k in d.get('label','') for k in get_restrictions(role))]
    
    safe_G = graph.copy()
    safe_G.remove_nodes_from(restricted)
    
    if s_node not in safe_G or e_node not in safe_G:
        return f"Path restricted for your role ({role})."

    try:
        paths = list(islice(nx.shortest_simple_paths(safe_G, s_node, e_node, weight='weight'), 3))
        
        output = f"[ SEQUENCE LIST FOR {role} ]\n\n"
        path_data = []
        for i, path in enumerate(paths, 1):
            labels = [safe_G.nodes[p]['label'] for p in path if 'label' in safe_G.nodes[p]]
            output += f"Option {i}: {' -> '.join(labels)}\n"
            
            seconds = sum(safe_G[u][v]['weight'] for u, v in zip(path[:-1], path[1:]))
            turns = count_turns(path)
            path_data.append([i, format_time(seconds), turns])

        output += f"\n{'='*45}\n"
        output += f"{'OPT':<5} | {'TIME':<15} | {'TURNS':<10}\n"
        output += f"{'-'*45}\n"
        for d in path_data:
            output += f"{d[0]:<5} | {d[1]:<15} | {d[2]:<10}\n"
        output += f"{'='*45}\n"
        return output
        
    except nx.NetworkXNoPath:
        return f"[{role} ROUTE ERROR] No valid path found given your security clearance."

# We removed the terminal while loop at the bottom because Streamlit handles the interface now!