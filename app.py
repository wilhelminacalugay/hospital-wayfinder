import streamlit as st
import networkx as nx
import plotly.graph_objects as go

# ---------------------------------------------------------
# THE GITHUB IMPORT FIX
# ---------------------------------------------------------
import importlib
import hospital_router
importlib.reload(hospital_router)
from hospital_router import build_hospital_graph, get_restrictions, find_optimized_paths

# ==========================================
# SETUP & CONFIG
# ==========================================
st.set_page_config(page_title="Smart Hospital Wayfinder", layout="wide")
st.title("🏥 Smart Hospital Wayfinding System")

# ---------------------------------------------------------
# DETECTION BOUNDS (RAW CAD LIMITS FOR THE SLICER)
# We ONLY need these now to slice the multi-floor route!
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
    for floor, (ymin, ymax) in DETECTION_Y_BOUNDS.items():
        if (ymin - 3000) <= y <= (ymax + 3000):
            return floor
    return "UG" # Failsafe

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
                
                # Slicer Logic
                segments = []
                first_x, first_y = path[0][0], path[0][1]
                current_floor = get_floor_from_coords(first_x, first_y)
                current_x, current_y = [], []
                
                for p in path:
                    node_x, node_y = p[0], p[1]
                    node_floor = get_floor_from_coords(node_x, node_y)
                    
                    if node_floor == current_floor:
                        current_x.append(node_x)
                        current_y.append(node_y)
                    else:
                        segments.append({'floor': current_floor, 'x': current_x, 'y': current_y})
                        current_floor = node_floor
                        current_x, current_y = [node_x], [node_y]
                
                if len(current_x) > 0:
                    segments.append({'floor': current_floor, 'x': current_x, 'y': current_y})
                
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
    valid_segments = [seg for seg in segments if seg['floor'] != "UNKNOWN"]
    segment_names = [f"Step {i+1}: {seg['floor']} Floor" for i, seg in enumerate(valid_segments)]
    
    st.markdown("### 🗺️ Route Map")
    if len(valid_segments) > 1:
        st.info("This route spans multiple floors. Follow the steps below sequentially.")
    
    selected_segment_name = st.radio("Navigation Sequence:", segment_names, horizontal=True)
    active_idx = segment_names.index(selected_segment_name)
    active_segment = valid_segments[active_idx]
    active_floor = active_segment['floor']
    
    # --- PLOTLY MAP VISUALIZATION ---
    fig = go.Figure()
    
    # 1. DRAW THE BLUEPRINT (BACKGROUND SKELETON)
    # We iterate through the graph and draw all edges that belong to the active floor
    edge_x = []
    edge_y = []
    
    for u, v in graph.edges():
        if get_floor_from_coords(u[0], u[1]) == active_floor and get_floor_from_coords(v[0], v[1]) == active_floor:
            # We add None between line segments so Plotly doesn't connect them into a giant spiderweb
            edge_x.extend([u[0], v[0], None])
            edge_y.extend([u[1], v[1], None])
            
    fig.add_trace(go.Scatter(
        x=edge_x, y=edge_y,
        mode='lines',
        line=dict(color='lightgray', width=2),
        hoverinfo='none',
        name='Hospital Layout'
    ))
        
    # 2. DRAW THE OPTIMAL ROUTE
    path_x = active_segment['x']
    path_y = active_segment['y']
    
    if len(path_x) > 0:
        fig.add_trace(go.Scatter(
            x=path_x, y=path_y,
            mode='lines',
            line=dict(color='red', width=5),
            name=f'{active_floor} Route'
        ))
        
        # Mark Local Start/End Points
        fig.add_trace(go.Scatter(
            x=[path_x[0], path_x[-1]], 
            y=[path_y[0], path_y[-1]],
            mode='markers+text',
            marker=dict(color=['green', 'blue'], size=[14, 14], line=dict(color='white', width=2)),
            text=['Start Here', 'End Here'],
            textposition="top center",
            textfont=dict(size=14, color="white"),
            name='Anchor Points'
        ))
        
    # 3. CONFIGURE PLOTLY (AUTO-SCALING)
    # We lock the scaleanchor so the map doesn't warp, but let Plotly auto-zoom to the data
    fig.update_layout(
        xaxis=dict(showgrid=False, zeroline=False, visible=False),
        yaxis=dict(showgrid=False, zeroline=False, visible=False, scaleanchor="x", scaleratio=1),
        margin=dict(l=10, r=10, t=10, b=10),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        showlegend=False
    )
    
    # We set a fixed height so the map looks good on screen
    st.plotly_chart(fig, use_container_width=True, height=600)
    
    st.markdown("### 📋 Step-by-Step Itinerary")
    st.text(st.session_state.itinerary_text)
