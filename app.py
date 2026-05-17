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

# Define the bounding boxes and image paths for all floors
# [WEST (Min X), EAST (Max X), SOUTH (Min Y), NORTH (Max Y)]
# NOTE: Update the X coordinates below with your true side-by-side CAD data
FLOOR_CONFIG = {
    "LG": {"bounds": [300000.0, 417000.0, -157112.6, -145093.6], "img": "new block-LG_EXPORT.png"},
    "UG": {"bounds": [417942.2, 532554.5, -157112.6, -145093.6], "img": "new block-UG_EXPORT.png"},
    "2F": {"bounds": [540000.0, 650000.0, -157112.6, -145093.6], "img": "new block-2F_EXPORT.png"},
    "3F": {"bounds": [660000.0, 770000.0, -157112.6, -145093.6], "img": "new block-3F_EXPORT.png"},
    "4F": {"bounds": [780000.0, 890000.0, -157112.6, -145093.6], "img": "new block-4F_EXPORT.png"},
    "5F": {"bounds": [900000.0, 1010000.0, -157112.6, -145093.6], "img": "new block-5F_EXPORT.png"},
    "6F": {"bounds": [1020000.0, 1130000.0, -157112.6, -145093.6], "img": "new block-6F_EXPORT.png"},
}

# ==========================================
# LOAD NETWORK ENGINE
# ==========================================
@st.cache_resource
def load_network():
    # Keep using your original top-to-bottom DXF file for this presentation
    graph, destinations = build_hospital_graph("new block.dxf") 
    return graph, destinations

graph, destinations = load_network()

if graph is None:
    st.error("Failed to load the hospital network. Check your DXF file path.")
    st.stop()

# ==========================================
# USER INTERFACE (SIDEBAR)
# ==========================================
st.sidebar.header("Navigation Setup")

roles = ["PATIENT", "VISITOR", "DOCTOR", "STAFF", "PWD"]
selected_role = st.sidebar.selectbox("Select User Role", roles)

# Sort destinations alphabetically for a clean UI
room_names = sorted(list(destinations.keys()))
start_room = st.sidebar.selectbox("Starting Point", room_names, index=0)
end_room = st.sidebar.selectbox("Destination", room_names, index=1)

# ==========================================
# ROUTING & VISUALIZATION LOGIC
# ==========================================
def get_floors_in_path(path_nodes):
    """Determines which floors a given path traverses based on X coordinates."""
    active_floors = []
    for node in path_nodes:
        x_coord = node[0]
        for floor, data in FLOOR_CONFIG.items():
            dx_min, dx_max, _, _ = data["bounds"]
            if dx_min <= x_coord <= dx_max and floor not in active_floors:
                active_floors.append(floor)
    return active_floors

if st.sidebar.button("Calculate Route"):
    if start_room == end_room:
        st.warning("Start and Destination are the same!")
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
        else:
            try:
                # 3. Calculate mathematical path
                path = nx.shortest_path(safe_G, s_node, e_node, weight='weight')
                
                # --- MULTI-FLOOR PLOTLY VISUALIZATION ---
                
                # Determine which floors this specific route uses
                route_floors = get_floors_in_path(path)
                
                if not route_floors:
                    st.error("Route coordinates do not match any known floor bounds.")
                    st.stop()

                # Initialize Session State for interactive floor navigation
                if 'current_floor_idx' not in st.session_state:
                    st.session_state.current_floor_idx = 0
                
                # Keep index within bounds if a new route is calculated
                if st.session_state.current_floor_idx >= len(route_floors):
                    st.session_state.current_floor_idx = 0

                active_floor_name = route_floors[st.session_state.current_floor_idx]
                floor_data = FLOOR_CONFIG[active_floor_name]
                dx_min, dx_max, dy_min, dy_max = floor_data["bounds"]
                
                # UI: Floor Navigation Controls
                st.markdown(f"### Current View: {active_floor_name} Floor")
                col1, col2, col3 = st.columns([1, 2, 1])
                
                with col1:
                    if st.session_state.current_floor_idx > 0:
                        if st.button("⬅️ Previous Floor"):
                            st.session_state.current_floor_idx -= 1
                            st.rerun()
                with col3:
                    if st.session_state.current_floor_idx < len(route_floors) - 1:
                        if st.button("Next Floor ➡️"):
                            st.session_state.current_floor_idx += 1
                            st.rerun()

                # Build the Plotly Figure
                fig = go.Figure()
                img_path = floor_data["img"]
                
                try:
                    img = Image.open(img_path)
                    img_w, img_h = img.size  
                    img_ratio = img_w / img_h
                    
                    cad_w = dx_max - dx_min
                    cad_h = dy_max - dy_min
                    true_image_height = cad_w / img_ratio
                    
                    y_center = dy_min + (cad_h / 2.0)
                    y_adjusted_max = y_center + (true_image_height / 2.0)
                    
                    fig.add_layout_image(
                        dict(
                            source=img, xref="x", yref="y",
                            x=dx_min, y=y_adjusted_max,
                            sizex=cad_w, sizey=true_image_height,
                            sizing="stretch", opacity=0.9, layer="below"
                        )
                    )
                except FileNotFoundError:
                    st.warning(f"Map image {img_path} not found. Drawing route on blank grid.")
                
                # The Spatial Slicer: Filter coordinates to strictly this floor
                path_x, path_y = [], []
                for p in path:
                    # If the node is within the current floor's horizontal bounds, draw it
                    if dx_min - 500 <= p[0] <= dx_max + 500:
                        path_x.append(p[0])
                        path_y.append(p[1])
                    else:
                        # If we hit a node outside the floor (e.g., up an elevator),
                        # insert a break (None) so Plotly doesn't draw a spaghetti line
                        if path_x and path_x[-1] is not None:
                            path_x.append(None)
                            path_y.append(None)
                        
                # Draw the Red Route Line
                if any(x is not None for x in path_x):
                    fig.add_trace(go.Scatter(
                        x=path_x, y=path_y,
                        mode='lines',
                        line=dict(color='red', width=4),
                        name='Optimal Route',
                        connectgaps=False # Ensure the spatial slicer gaps are respected
                    ))
                
                # Clean up Axes
                fig.update_layout(
                    xaxis=dict(range=[dx_min, dx_max], showgrid=False, zeroline=False, visible=False),
                    yaxis=dict(range=[dy_min, dy_max], showgrid=False, zeroline=False, visible=False, scaleanchor="x", scaleratio=1),
                    margin=dict(l=0, r=0, t=0, b=0),
                    plot_bgcolor="rgba(0,0,0,0)"
                )
                
                st.plotly_chart(fig, use_container_width=True)
                
                # Display Success
                st.success("Route generated successfully!")
                
                # ==========================================
                # ADD THE TEXT ITINERARY & OPTIONS HERE!
                # ==========================================
                st.markdown("### 📋 Step-by-Step Itinerary & Options")
                
                # Call your backend Operations Research function to get the text table
                itinerary_text = find_optimized_paths(graph, destinations, start_room, end_room, selected_role)
                
                # Print it using st.text() so it keeps your perfect column spacing!
                st.text(itinerary_text)
                
            except nx.NetworkXNoPath:
                st.error(f"No valid path found for {selected_role} between these locations.")
