import streamlit as st
import networkx as nx
import plotly.graph_objects as go
import os
from PIL import Image
import base64

from hospital_router import build_hospital_graph, get_restrictions, find_optimized_paths

# ==========================================
# SETUP & CONFIG
# ==========================================
st.set_page_config(page_title="Smart Hospital Wayfinder", layout="wide")
st.title("🏥 Smart Hospital Wayfinding System")

# ---------------------------------------------------------
# 1. DISPLAY BOUNDS (STRICT 12,019 HEIGHT FOR PLOTLY IMAGES)
# ---------------------------------------------------------
FLOOR_BOUNDS = {
    "LG": [417942.2448, 532554.4766, -170844.5250, -158825.4973],
    "UG": [417942.2448, 532554.4766, -157112.6036, -145093.5759],
    "2F": [417942.2448, 532554.4766, -141687.9535, -129668.9258],
    "3F": [417942.2448, 532554.4766, -123925.8665, -111906.8388],
    "4F": [417942.2448, 532554.4766, -110017.8566,  -97998.8289],
    "5F": [417942.2448, 532554.4766,  -98097.2445,  -86078.2168],
    "6F": [417942.2448, 532554.4766,  -80271.6670,  -68252.6393],
}

# ---------------------------------------------------------
# 2. DETECTION BOUNDS (RAW CAD LIMITS FOR THE SLICER)
# ---------------------------------------------------------
DETECTION_Y_BOUNDS = {
    "LG": [-170844.5250, -159463.4517],
    "UG": [-157112.6036, -145093.5759],
    "2F": [-141687.9535, -128588.0201],
    "3F": [-123925.8665, -112552.7519],
    "4F": [-110017.8566, -98644.7420],
    "5F": [-98097.2445, -84121.1446],
    "6F": [-80271.6670, -76308.3462],
}

def get_floor_from_coords(x, y):
    """Mathematically detects the floor using a massive vertical buffer."""
    # We apply a massive 3000-unit safety buffer to your raw coordinates 
    # to guarantee absolutely no routing nodes ever get left behind.
    for floor, (ymin, ymax) in DETECTION_Y_BOUNDS.items():
        if (ymin - 3000) <= y <= (ymax + 3000):
            return floor
            
    # Absolute failsafe: If a coordinate is completely lost in the void, 
    # default to UG instead of crashing the application.
    return "UG"

@st.cache_resource
def load_network():
    graph, destinations = build_hospital_graph("new block.dxf") 
    return graph, destinations

graph, destinations = load_network()

if graph is None:
    st.error("Failed to load the hospital network. Check your DXF file path.")
    st.stop()

# ==========================================
# STATE MANAGEMENT
# ==========================================
if 'route_active' not in st.session_state:
    st.session_state.route_active = False
if 'route_segments' not in st.session_state:
    st.session_state.route_segments = []

# ==========================================
# USER INTERFACE (SIDEBAR)
# ==========================================
st.sidebar.header("Navigation Setup")

roles = ["PATIENT", "VISITOR", "DOCTOR", "STAFF", "PWD"]
selected_role = st.sidebar.selectbox("Select User Role", roles)

room_names = sorted(list(destinations.keys()))
start_room = st.sidebar.selectbox("Starting Point", room_names, index=0)
end_room = st.sidebar.selectbox("Destination", room_names, index=1)

# ==========================================
# ROUTING CALCULATIONS
# ==========================================
if st.sidebar.button("Calculate Route"):
    if start_room == end_room:
        st.warning("Start and Destination are the same!")
        st.session_state.route_active = False
    else:
        s_node = destinations[start_room]
        e_node = destinations[end_room]
        
        restricted_keywords = get_restrictions(selected_role)
        restricted_nodes = [
            n for n, d in graph.nodes(data=True) 
            if any(k in d.get('label', '') for k in restricted_keywords)
        ]
        
        safe_G = graph.copy()
        safe_G.remove_nodes_from(restricted_nodes)
        
        if s_node not in safe_G or e_node not in safe_G:
            st.error(f"Access Denied: This route is restricted for your role ({selected_role}).")
            st.session_state.route_active = False
        else:
            try:
                path = nx.shortest_path(safe_G, s_node, e_node, weight='weight')
                
                # ---------------------------------------------------------
                # NEW: THE LINEAR SEGMENT SLICER
                # Breaks the route at vertical transit nodes (Elevators/Stairs)
                # ---------------------------------------------------------
                segments = []
                current_floor = safe_G.nodes[path[0]].get('layer', 'UG').upper()
                current_x = []
                current_y = []
                
                for p in path:
                    node_layer = safe_G.nodes[p].get('layer', 'UG').upper()
                    
                    if node_layer == current_floor:
                        current_x.append(p[0])
                        current_y.append(p[1])
                    else:
                        # Floor change detected! Cap off the previous floor's route.
                        segments.append({
                            'floor': current_floor,
                            'x': current_x,
                            'y': current_y
                        })
                        # Start the new floor's route EXACTLY at the new transit node
                        current_floor = node_layer
                        current_x = [p[0]]
                        current_y = [p[1]]
                
                # Catch the final segment after the loop finishes
                if len(current_x) > 0:
                    segments.append({
                        'floor': current_floor,
                        'x': current_x,
                        'y': current_y
                    })
                
                st.session_state.route_segments = segments
                st.session_state.route_active = True
                st.session_state.itinerary_text = find_optimized_paths(
                    graph, destinations, start_room, end_room, selected_role
                )
                
            except nx.NetworkXNoPath:
                st.error(f"No valid path found for {selected_role} between these locations.")
                st.session_state.route_active = False

# ==========================================
# VISUALIZATION & MULTI-FLOOR UI
# ==========================================
if st.session_state.route_active:
    st.success("Route generated successfully!")
    
    segments = st.session_state.route_segments
    
    # Create sequential UI buttons (e.g., "Step 1: UG", "Step 2: F1")
    segment_names = [f"Step {i+1}: {seg['floor']} Floor" for i, seg in enumerate(segments)]
    
    st.markdown("### 🗺️ Route Map")
    if len(segments) > 1:
        st.info("This route spans multiple floors. Follow the steps below sequentially.")
    
    # The Sequence Flipbook
    selected_segment_name = st.radio("Navigation Sequence:", segment_names, horizontal=True)
    
    # Get the active segment data based on user selection
    active_idx = segment_names.index(selected_segment_name)
    active_segment = segments[active_idx]
    active_floor = active_segment['floor']
    
    # --- PLOTLY MAP VISUALIZATION ---
    # --- PLOTLY MAP VISUALIZATION ---
    # We dynamically grab the specific bounding box for the active floor!
    # Safely fetch the bounds. If the memory is corrupted or unknown, default to UG.
    bounds = FLOOR_BOUNDS.get(active_floor, FLOOR_BOUNDS["UG"])
    dx_min, dx_max, dy_min, dy_max = bounds
    fig = go.Figure()
    
   # ---------------------------------------------------------
    # IMAGE DEBUGGER & LOADER (Base64 Web-Safe Version)
    # ---------------------------------------------------------
    img_path = f"new block-{active_floor}_EXPORT.png" 
    
    if os.path.exists(img_path):
        # 1. Open with PIL just to get the width/height math
        img = Image.open(img_path)
        img_w, img_h = img.size  
        img_ratio = img_w / img_h
        
        # 2. Encode the image to Base64 so Plotly guarantees rendering in the browser
        with open(img_path, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode()
        img_uri = f"data:image/png;base64,{encoded_string}"
        
        # 3. "Anti-Pancake" Bounding Box Math
        cad_w = dx_max - dx_min
        cad_h = dy_max - dy_min
        true_image_height = cad_w / img_ratio
        
        y_center = dy_min + (cad_h / 2.0)
        y_adjusted_max = y_center + (true_image_height / 2.0)
        
        # 4. Inject the Base64 Image into Plotly with Explicit Anchors
        fig.add_layout_image(
            dict(
                source=img_uri,      # Using the Base64 URI instead of the raw PIL object
                xref="x", yref="y",
                x=dx_min, y=y_adjusted_max,
                xanchor="left",      # Explicitly lock the X anchor
                yanchor="top",       # Explicitly lock the Y anchor
                sizex=cad_w,
                sizey=true_image_height,
                sizing="stretch", 
                opacity=0.9,
                layer="below"
            )
        )
    else:
        st.error(f"⚠️ Image Missing: The app is looking for an image named exactly '{img_path}' in your folder but cannot find it. Please rename your PNG file to match this string.")
        
    # Draw ONLY the path segment for this specific step in the journey
    path_x = active_segment['x']
    path_y = active_segment['y']
    
    if len(path_x) > 0:
        fig.add_trace(go.Scatter(
            x=path_x, y=path_y,
            mode='lines',
            line=dict(color='red', width=4),
            name=f'{active_floor} Route'
        ))
        
        # Mark Local Start/End Points for this specific step
        # If this is Step 2, the "Start" marker visually drops exactly on the elevator node.
        fig.add_trace(go.Scatter(
            x=[path_x[0], path_x[-1]], 
            y=[path_y[0], path_y[-1]],
            mode='markers+text',
            marker=dict(color=['green', 'blue'], size=[12, 12]),
            text=['Start Here', 'End Here'],
            textposition="top center",
            name='Anchor Points'
        ))
        
    fig.update_layout(
        xaxis=dict(range=[dx_min, dx_max], showgrid=False, zeroline=False, visible=False),
        yaxis=dict(range=[dy_min, dy_max], showgrid=False, zeroline=False, visible=False, scaleanchor="x", scaleratio=1),
        margin=dict(l=0, r=0, t=0, b=0),
        plot_bgcolor="rgba(0,0,0,0)"
    )
    
    st.plotly_chart(fig, use_container_width=True)
    
    # ==========================================
    # TEXT ITINERARY
    # ==========================================
    st.markdown("### 📋 Step-by-Step Itinerary")
    st.text(st.session_state.itinerary_text)

    path = nx.shortest_path(safe_G, s_node, e_node, weight='weight')
