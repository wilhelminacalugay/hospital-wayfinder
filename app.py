import streamlit as st
import networkx as nx
import plotly.graph_objects as go
from PIL import Image

# Import the logic we built in your backend
from hospital_router import build_hospital_graph, get_restrictions, find_optimized_paths

# ==========================================
# SETUP & CONFIG
# ==========================================
st.set_page_config(page_title="Smart Hospital Wayfinder", layout="wide")
st.title("🏥 Smart Hospital Wayfinding System")

# Define the Master Bounds (Universal for all vertically stacked floors)
# [WEST (Min X), EAST (Max X), SOUTH (Min Y), NORTH (Max Y)]
MASTER_BOUNDS = [417942.2, 532554.5, -157112.6, -145093.6]

# ==========================================
# LOAD NETWORK ENGINE
# ==========================================
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
# Initialize session state variables to hold route data between UI clicks
if 'route_active' not in st.session_state:
    st.session_state.route_active = False
if 'path_nodes' not in st.session_state:
    st.session_state.path_nodes = []
if 'floor_segments' not in st.session_state:
    st.session_state.floor_segments = {}

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
        
        # 1. Apply Role-Based Access Control (RBAC)
        restricted_keywords = get_restrictions(selected_role)
        restricted_nodes = [
            n for n, d in graph.nodes(data=True) 
            if any(k in d.get('label', '') for k in restricted_keywords)
        ]
        
        safe_G = graph.copy()
        safe_G.remove_nodes_from(restricted_nodes)
        
        # 2. Check if route is possible
        if s_node not in safe_G or e_node not in safe_G:
            st.error(f"Access Denied: This route is restricted for your role ({selected_role}).")
            st.session_state.route_active = False
        else:
            try:
                # 3. Calculate mathematical path
                path = nx.shortest_path(safe_G, s_node, e_node, weight='weight')
                
                # 4. The Z-Axis Spatial Slicer
                floor_segments = {}
                for p in path:
                    # Extract node data. Change 'layer' to whatever attribute 
                    # hospital_router.py uses to store the floor name (e.g., 'floor', 'elevation')
                    node_data = safe_G.nodes[p]
                    floor_id = node_data.get('layer', 'UG') # Default to UG if missing
                    
                    if floor_id not in floor_segments:
                        floor_segments[floor_id] = {'x': [], 'y': []}
                        
                    # Assuming nodes are represented as (X, Y) or (X, Y, Z) tuples
                    floor_segments[floor_id]['x'].append(p[0])
                    floor_segments[floor_id]['y'].append(p[1])
                
                # Save to state so the UI can page through it
                st.session_state.path_nodes = path
                st.session_state.floor_segments = floor_segments
                st.session_state.route_active = True
                
                # Also generate and store the text itinerary
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
    
    # Extract the sliced data from session state
    floor_segments = st.session_state.floor_segments
    involved_floors = list(floor_segments.keys())
    
    # Multi-Floor UI Selector
    st.markdown("### 🗺️ Route Map")
    if len(involved_floors) > 1:
        st.info("This route spans multiple floors. Select a floor below to view that segment.")
    
    # This radio button lets the user "flip" through the floors.
    # Because we used st.session_state, clicking this won't erase the calculated route.
    selected_floor = st.radio("View Route on Floor:", involved_floors, horizontal=True)
    
    # --- PLOTLY MAP VISUALIZATION ---
    dx_min, dx_max, dy_min, dy_max = MASTER_BOUNDS
    fig = go.Figure()
    
    # Dynamically load the correct Background Image based on the selected floor
    # Adjust this string formatting to match your exact PNG naming convention
    img_path = f"new block-{selected_floor}_EXPORT.png" 
    
    try:
        img = Image.open(img_path)
        
        # The "Anti-Pancake" Aspect Ratio Math
        img_w, img_h = img.size  
        img_ratio = img_w / img_h
        
        cad_w = dx_max - dx_min
        cad_h = dy_max - dy_min
        true_image_height = cad_w / img_ratio
        
        y_center = dy_min + (cad_h / 2.0)
        y_adjusted_max = y_center + (true_image_height / 2.0)
        
        fig.add_layout_image(
            dict(
                source=img,
                xref="x", yref="y",
                x=dx_min, y=y_adjusted_max,
                sizex=cad_w,
                sizey=true_image_height,
                sizing="stretch", 
                opacity=0.9,
                layer="below"
            )
        )
    except FileNotFoundError:
        st.warning(f"Could not find {img_path}. Displaying route without background.")
        
    # Draw ONLY the path segment that physically belongs to the currently selected floor
    path_x = floor_segments[selected_floor]['x']
    path_y = floor_segments[selected_floor]['y']
    
    if len(path_x) > 0:
        fig.add_trace(go.Scatter(
            x=path_x, y=path_y,
            mode='lines',
            line=dict(color='red', width=4),
            name=f'{selected_floor} Route'
        ))
        
        # Mark Local Start/End Points for this specific floor segment
        fig.add_trace(go.Scatter(
            x=[path_x[0], path_x[-1]], 
            y=[path_y[0], path_y[-1]],
            mode='markers+text',
            marker=dict(color=['green', 'blue'], size=12),
            text=['Segment Start', 'Segment End'],
            textposition="top center",
            name='Transition Points'
        ))
        
    # Configure Plot axes to match the universal bounding box
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
    st.markdown("### 📋 Step-by-Step Itinerary & Options")
    st.text(st.session_state.itinerary_text)
