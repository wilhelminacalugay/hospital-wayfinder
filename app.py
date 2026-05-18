import streamlit as st
import networkx as nx
import plotly.graph_objects as go
import textwrap

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
st.markdown(
    """
    <style>
    /* Target all text inside the sidebar and make it Gold */
    [data-testid="stSidebar"] {
        color: #fcba06;
    }
    [data-testid="stSidebar"] * {
        color: #fcba06 !important;
    }

    /* 1. Changes the text color of the currently SELECTED option in the main page dropdown to GOLD */
    div[data-baseweb="select"] > div {
        color: #fcba06 !important; 
    }
    
    /* Ensures the specific text span inside the box also turns gold */
    div[data-baseweb="select"] > div span {
        color: #fcba06 !important; 
    }
    
    /* 2. Keeps the list of options in the POP-OUT menu dark green so they are readable against a white background */
    ul[role="listbox"] li {
        color: #03542b !important; 
    }
    
    /* Optional: Changes the background color of the option you hover over */
    ul[role="listbox"] li:hover {
        background-color: #eef7f2 !important;
        color: #03542b !important;
    }
    </style>
    """,
    unsafe_allow_html=True
)
st.title("Ospital ng Parañaque - District II Wayfinding System")

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
    """Magnetically snaps coordinates to the closest floor to prevent fake bounces."""
    best_floor = "UG"
    min_dist = float('inf')
    
    for floor, (ymin, ymax) in DETECTION_Y_BOUNDS.items():
        # If it is perfectly inside the bounds, return immediately
        if ymin <= y <= ymax:
            return floor
            
        # If it is slightly outside, calculate the distance to the nearest edge
        dist = min(abs(y - ymin), abs(y - ymax))
        if dist < min_dist:
            min_dist = dist
            best_floor = floor
            
    return best_floor

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

roles = ["PATIENT", "VISITOR", "NURSE", "DOCTOR", "STAFF", "PWD"]
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
        # Catch BOTH the data dictionary and the raw paths
        route_data, all_paths = find_optimized_paths(
            graph, destinations, start_room, end_room, selected_role
        )
        
        if not all_paths: 
            st.error(route_data) # If it fails, route_data holds the error message
            st.session_state.route_active = False
        else:
            st.session_state.all_paths = all_paths
            st.session_state.route_data = route_data # Save the new data!
            st.session_state.route_active = True

# ==========================================
# TEMPORARY DEBUG TOOLS
# ==========================================
# st.sidebar.markdown("---")
# if st.sidebar.button("Run Island Finder"):
    # import networkx as nx
    
    # Convert to an undirected graph for checking connections
    # check_G = graph.to_undirected()
    # islands = list(nx.connected_components(check_G))
    
    # if len(islands) > 1:
        # st.sidebar.error(f"WARNING: Graph broken into {len(islands)} pieces!")
        
        # Sort islands by size (the biggest one is the main hospital)
        # islands.sort(key=len, reverse=True)
        
        # Print the disconnected rooms directly to the sidebar
        # for i, island in enumerate(islands[1:], 1):
            # floating_labels = [check_G.nodes[n].get('label', str(n)) for n in island]
            # st.sidebar.warning(f"**Disconnected Piece #{i}:**\n" + ", ".join(floating_labels))
    # else:
        # st.sidebar.success("The hospital grid is perfectly connected!")
        
# ==========================================
# VISUALIZATION & MULTI-FLOOR UI
# ==========================================
if st.session_state.route_active:
    st.success("Routes generated successfully!")
    
    import pandas as pd
    
    # --- 1. THE NEW ROUTE COMPARISON TABLE ---
    st.markdown("### Route Options")
    
    # Build a clean dataframe for the user to read
    table_data = []
    for r in st.session_state.route_data:
        table_data.append({
            "Route Type": r['name'],
            "Est. Time": r['time'],
            "Turns": r['turns'],
            "Directions": r['steps']
        })
        
    df = pd.DataFrame(table_data)
    
    # Display it cleanly without the index numbers
    st.table(df.set_index("Route Type")) 

    st.markdown("---")
    
    # --- 2. THE NEW DYNAMIC DROPDOWN ---
    # Extract the names we created in the backend (e.g., "Best Route")
    path_options = [r['name'] for r in st.session_state.route_data]
    
    col1, col2 = st.columns([1, 2])
    with col1:
        selected_path_name = st.selectbox("Select Route to Display on Map:", path_options)
    
    path_idx = path_options.index(selected_path_name)
    active_path = st.session_state.all_paths[path_idx]
    
    # --- 2. DYNAMIC SLICER (Runs on the selected option) ---
    segments = []
    first_x, first_y = active_path[0][0], active_path[0][1]
    current_floor = get_floor_from_coords(first_x, first_y)
    current_x, current_y = [], []
    
    for p in active_path:
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
        
    valid_segments = [seg for seg in segments if seg['floor'] != "UNKNOWN"]
    segment_names = [f"Step {i+1}: {seg['floor']} Floor" for i, seg in enumerate(valid_segments)]
    
    st.markdown("---")
    
    # --- 3. FLOOR NAVIGATION UI ---
    if len(valid_segments) > 1:
        st.info("This route spans multiple floors. Follow the steps below sequentially.")
    
    selected_segment_name = st.radio("Floor Navigation Sequence:", segment_names, horizontal=True)
    active_idx = segment_names.index(selected_segment_name)
    active_segment = valid_segments[active_idx]
    active_floor = active_segment['floor']
    
    # --- 4. PLOTLY MAP VISUALIZATION ---
    fig = go.Figure()
    
    # DRAW THE BLUEPRINT (BACKGROUND SKELETON)
    edge_x = []
    edge_y = []
    for u, v in graph.edges():
        if get_floor_from_coords(u[0], u[1]) == active_floor and get_floor_from_coords(v[0], v[1]) == active_floor:
            edge_x.extend([u[0], v[0], None])
            edge_y.extend([u[1], v[1], None])
            
    fig.add_trace(go.Scatter(
        x=edge_x, y=edge_y,
        mode='lines',
        line=dict(color='lightgray', width=2),
        hoverinfo='none',
        name='Hospital Layout'
    ))

    # ---------------------------------------------------------
    # NEW: DRAW THE WAYFINDING NODES (BLUE DOTS)
    # ---------------------------------------------------------
    node_x = []
    node_y = []
    for n in graph.nodes():
        if get_floor_from_coords(n[0], n[1]) == active_floor:
            node_x.append(n[0])
            node_y.append(n[1])

    fig.add_trace(go.Scatter(
        x=node_x, y=node_y,
        mode='markers',
        marker=dict(size=4, color='blue', opacity=0.4),
        hoverinfo='x+y', # Shows coordinates on mouse hover
        name='Wayfinding Nodes'
    ))

    # ---------------------------------------------------------
    # NEW: DRAW THE NAMED DESTINATIONS (ORANGE DOTS WITH TEXT)
    # ---------------------------------------------------------
    import textwrap # Make sure this is at the top of your file!

    dest_x = []
    dest_y = []
    dest_names = []
    for name, pt in destinations.items():
        if get_floor_from_coords(pt[0], pt[1]) == active_floor:
            dest_x.append(pt[0])
            dest_y.append(pt[1])
            
            # This slices the text every 15 characters, and limits it to 3 rows max
            wrapped_lines = textwrap.wrap(name, width=15)[:3] 
            wrapped_text = "<br>".join(wrapped_lines) 
            
            dest_names.append(wrapped_text)

    fig.add_trace(go.Scatter(
        x=dest_x, y=dest_y,
        mode='markers+text',
        text=dest_names,
        textposition="top center",
        textfont=dict(size=9, color="orange"),
        marker=dict(size=6, color='orange', opacity=0.8),
        hoverinfo='text',
        name='Destinations'
    ))
    # ---------------------------------------------------------
        
    # DRAW THE OPTIMAL ROUTE
    path_x = active_segment['x']
    path_y = active_segment['y']
    
    if len(path_x) > 0:
        fig.add_trace(go.Scatter(
            x=path_x, y=path_y,
            mode='lines',
            line=dict(color='red', width=5),
            name=f'{active_floor} Route'
        ))
        
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
        
    fig.update_layout(
        xaxis=dict(showgrid=False, zeroline=False, visible=False),
        yaxis=dict(showgrid=False, zeroline=False, visible=False, scaleanchor="x", scaleratio=1),
        margin=dict(l=10, r=10, t=10, b=10),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        showlegend=False
    )
    
    st.plotly_chart(fig, use_container_width=True, height=600)

    # --- 6. REAL AS-BUILT REFERENCE ---
    st.markdown("---")
    with st.expander(f"View Original As-Built Plan for {active_floor} Floor"):
        # Dynamically load the correct image based on the floor they are looking at!
        image_filename = f"{active_floor}_plan.jpg" 
        try:
            st.image(image_filename, caption=f"Original CAD Blueprint - {active_floor} Floor", use_container_width=True)
        except FileNotFoundError:
            st.warning(f"Please upload '{image_filename}' to the project folder to view it here.")
    # --- 7. DEVELOPER X-RAY VISION ---
    st.markdown("---")
    with st.expander("🛠️ Developer Mode: View Raw Routing Math"):
        st.write(st.session_state.route_data)
