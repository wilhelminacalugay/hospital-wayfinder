import streamlit as st
import networkx as nx
import plotly.graph_objects as go
import textwrap
from PIL import Image

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

    /* Changes the text color of the currently SELECTED option in the main page dropdown to GOLD */
    div[data-baseweb="select"] > div {
        color: #fcba06 !important; 
    }
    
    /* Ensures the specific text span inside the box also turns gold */
    div[data-baseweb="select"] > div span {
        color: #fcba06 !important; 
    }
    
    /* Keeps the list of options in the POP-OUT menu dark green */
    ul[role="listbox"] li {
        color: #03542b !important; 
    }
    
    /* Changes the background color of the option you hover over */
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
    best_floor = "UG"
    min_dist = float('inf')
    
    for floor, (ymin, ymax) in DETECTION_Y_BOUNDS.items():
        if ymin <= y <= ymax:
            return floor
            
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

# MANUAL CAD NUDGES
# X controls Left/Right (+ is Right, - is Left)
# Y controls Up/Down (+ is Up, - is Down)

# 1. Fix the Overlap: Push Conference Room UP so it stops mashing with Secretary
if "CONFERENCE ROOM" in destinations:
    current_x, current_y = destinations["CONFERENCE ROOM"]
    destinations["CONFERENCE ROOM"] = (current_x + 800, current_y - 800)

# 2. Fix the Misplaced Node: Slide Chief of Clinics to the correct intersection
if "CHIEF OF CLINICS" in destinations:
    current_x, current_y = destinations["CHIEF OF CLINICS"]
    # Adjust these numbers to slide the dot exactly where it belongs
    destinations["CHIEF OF CLINICS"] = (current_x -500, current_y)

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
# USER INTERFACE (MOBILE/DESKTOP MAIN PAGE)
# ==========================================
st.markdown("### Navigation Setup")

# 1. Ask for the Role FIRST
roles = ["PATIENT", "VISITOR", "NURSE", "DOCTOR", "STAFF", "PWD"]
selected_role = st.selectbox("Select User Role", roles)

# 2. Fetch restrictions from the backend for this specific role
raw_restrictions = get_restrictions(selected_role)

# Safely extract the restricted nodes, whether the backend returns 1 item or a tuple
restricted_nodes = raw_restrictions[0] if isinstance(raw_restrictions, tuple) else raw_restrictions

# 3. Dynamically filter the room list
allowed_room_names = []
for name, coords in destinations.items():
    # Check against both the name AND the coordinates to be absolutely safe
    if name not in restricted_nodes and coords not in restricted_nodes:
        allowed_room_names.append(name)

# Sort them alphabetically for the user
allowed_room_names = sorted(allowed_room_names)

# 4. Display the pre-filtered dropdowns
col1, col2 = st.columns(2)
with col1:
    start_room = st.selectbox("Starting Point", allowed_room_names, index=0)
with col2:
    # Safely set the default destination index so it doesn't break if the list is small
    default_end = 1 if len(allowed_room_names) > 1 else 0
    end_room = st.selectbox("Destination", allowed_room_names, index=default_end)

# ==========================================
# ROUTING CALCULATIONS
# ==========================================
if st.button("Calculate Route", use_container_width=True):
    if start_room == end_room:
        st.warning("Start and Destination are the same!")
        st.session_state.route_active = False
    else:
        route_data, all_paths = find_optimized_paths(
            graph, destinations, start_room, end_room, selected_role
        )
        
        if not all_paths: 
            st.error(route_data) 
            st.session_state.route_active = False
        else:
            st.session_state.all_paths = all_paths
            st.session_state.route_data = route_data 
            st.session_state.route_active = True
        
# ==========================================
# VISUALIZATION & MULTI-FLOOR UI
# ==========================================
if st.session_state.route_active:
    st.success("Routes generated successfully!")
    
    # --- 1. ROUTE CARDS ---
    st.markdown("### Route Options")
    
    for r in st.session_state.route_data:
        with st.container(border=True):
            st.markdown(f"#### {r['name']}")
            st.markdown(f"**Est. Time:** {r['time']} &nbsp; | &nbsp; **Turns:** {r['turns']}")
            st.caption(r['steps'])

    st.markdown("---")
    
    # --- 2. DYNAMIC DROPDOWN ---
    path_options = [r['name'] for r in st.session_state.route_data]
    
    col1, col2 = st.columns([1, 2])
    with col1:
        selected_path_name = st.selectbox("Select Route to Display on Map:", path_options)
    
    path_idx = path_options.index(selected_path_name)
    active_path = st.session_state.all_paths[path_idx]
    
    # --- 3. DYNAMIC SLICER ---
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
    
    # --- 4. FLOOR NAVIGATION UI ---
    if len(valid_segments) > 1:
        st.info("This route spans multiple floors. Follow the steps below sequentially.")
    
    selected_segment_name = st.radio("Floor Navigation Sequence:", segment_names, horizontal=True)
    active_idx = segment_names.index(selected_segment_name)
    active_segment = valid_segments[active_idx]
    active_floor = active_segment['floor']
    
    # --- 5. PLOTLY MAP VISUALIZATION ---
    fig = go.Figure()
    
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
        hoverinfo='none', 
        name='Wayfinding Nodes'
    ))

    dest_x = []
    dest_y = []
    dest_names = []
    for name, pt in destinations.items():
        if get_floor_from_coords(pt[0], pt[1]) == active_floor:
            dest_x.append(pt[0])
            dest_y.append(pt[1])
            
            # FIX: Widened from 15 to 30 characters so the text breathes horizontally
            wrapped_lines = textwrap.wrap(name, width=30)[:2] 
            wrapped_text = "<br>".join(wrapped_lines) 
            
            dest_names.append(wrapped_text)

    # UPDATED: Node names to dark blue
    fig.add_trace(go.Scatter(
        x=dest_x, y=dest_y,
        mode='markers+text',
        text=dest_names,
        textposition="middle right", # <--- Pushes text to the side to stop vertical mashing
        textfont=dict(size=9, color="darkblue"),
        marker=dict(size=6, color='darkblue', opacity=0.8),
        hoverinfo='none',
        name='Destinations'
    ))
        
    path_x = active_segment['x']
    path_y = active_segment['y']
    
    if len(path_x) > 0:
        # UPDATED: Route line to black
        fig.add_trace(go.Scatter(
            x=path_x, y=path_y,
            mode='lines',
            line=dict(color='black', width=5),
            name=f'{active_floor} Route',
            hoverinfo='none'
        ))
        
        # UPDATED: Yellow Start, Dark Green End, Black Text positioned below the dots
        fig.add_trace(go.Scatter(
            x=[path_x[0], path_x[-1]], 
            y=[path_y[0], path_y[-1]],
            mode='markers+text',
            marker=dict(color=['yellow', 'darkgreen'], size=[14, 14], line=dict(color='black', width=2)),
            text=['Start Here', 'End Here'],
            textposition="bottom center", # <--- Changed this to push text down
            textfont=dict(size=14, color="black"),
            name='Anchor Points',
            hoverinfo='none'
        ))
        
    fig.update_layout(
        xaxis=dict(showgrid=False, zeroline=False, visible=False, fixedrange=False), 
        yaxis=dict(showgrid=False, zeroline=False, visible=False, scaleanchor="x", scaleratio=1, fixedrange=False), 
        margin=dict(l=0, r=0, t=0, b=0),
        plot_bgcolor="#eef7f2",
        paper_bgcolor="#eef7f2",
        showlegend=False,
        dragmode="zoom", 
        hovermode=False 
    )
    
    st.plotly_chart(fig, use_container_width=True, height=600, config={'displayModeBar': True, 'displaylogo': False})
    
    # ADDED: Double-tap reminder for the Main Route Map
    st.info("**Tip:** Double-tap the map to reset the zoom view.")

    # --- 6. REAL AS-BUILT REFERENCE ---
    st.markdown("---")
    with st.expander(f"View Original As-Built Plan for {active_floor} Floor"):
        image_filename = f"{active_floor}_plan.jpg" 
        try:
            img = Image.open(image_filename)
            img_w, img_h = img.size
            
            fig_blueprint = go.Figure()
            fig_blueprint.add_layout_image(
                dict(
                    source=img,
                    xref="x", yref="y",
                    x=0, y=img_h,      
                    sizex=img_w,
                    sizey=img_h,
                    sizing="stretch",
                    layer="below"
                )
            )
            
            fig_blueprint.update_layout(
                xaxis=dict(range=[0, img_w], showgrid=False, zeroline=False, visible=False, fixedrange=False),
                yaxis=dict(range=[0, img_h], showgrid=False, zeroline=False, visible=False, scaleanchor="x", scaleratio=1, fixedrange=False),
                margin=dict(l=0, r=0, t=0, b=0),
                plot_bgcolor="#eef7f2",
                paper_bgcolor="#eef7f2",
                showlegend=False,
                dragmode="zoom",
                height=500,
                hovermode=False
            )
            
            st.plotly_chart(fig_blueprint, use_container_width=True, config={'displayModeBar': True, 'displaylogo': False})
            
            # ADDED: Double-tap reminder for the Blueprint Map
            st.info("**Tip:** Double-tap the map to reset the zoom view.")
            
        except FileNotFoundError:
            st.warning(f"Please upload '{image_filename}' to the project folder to view it here.")
