import streamlit as st
import plotly.graph_objects as go
from PIL import Image
import networkx as nx
from hospital_router import build_hospital_graph, find_optimized_paths 

# ==========================================
# PAGE CONFIGURATION
# ==========================================
st.set_page_config(page_title="Hospital Wayfinder", layout="wide")

st.title("🏥 Smart Hospital Wayfinding System")
st.markdown("### Interactive Decision-Support Dashboard")

# ==========================================
# CACHE THE ALGORITHM
# ==========================================
@st.cache_resource
def load_hospital_data():
    return build_hospital_graph("new block.dxf")

with st.spinner("Loading structural network geometry..."):
    net, db = load_hospital_data()

# ==========================================
# MULTI-FLOOR IMAGE DICTIONARY
# ==========================================
# This links the user's selected view to your exact uploaded PNGs
floor_maps = {
    "Lower Ground (LG)": "lg_floor.png",
    "Upper Ground (UG)": "ug_floor.png",
    "2nd Floor (2F)": "2f_floor.png",
    "3rd Floor (3F)": "3f_floor.png",
    "4th Floor (4F)": "4f_floor.png",
    "5th Floor (5F)": "5f_floor.png",
    "6th Floor (6F)": "6f_floor.png"
}

# ==========================================
# THE INTERACTIVE USER INTERFACE
# ==========================================
if net and db:
    all_rooms = sorted(list(db.keys()))
    
    with st.sidebar:
        st.header("Navigation Parameters")
        
        role_options = ["DOCTOR", "STAFF", "PATIENT", "VISITOR", "PWD"]
        user_role = st.selectbox("👤 Security Clearance:", options=role_options, index=3)
        st.divider()
        start_point = st.selectbox("📍 Current Location:", options=all_rooms, index=0)
        destination = st.selectbox("🏁 Destination:", options=all_rooms, index=1)
        st.divider()
        calculate_btn = st.button("Calculate Optimal Route", type="primary", use_container_width=True)

    if calculate_btn:
        if start_point == destination:
            st.warning("You are already at your destination!")
        else:
            with st.spinner("Calculating multi-objective trade-offs..."):
                result = find_optimized_paths(net, db, start_point, destination, user_role)
                
                text_col, map_col = st.columns([1, 1.5])
                
                with text_col:
                    st.markdown("### Recommended Itineraries")
                    st.success("Routing Complete.")
                    st.code(result, language="markdown")
                
                with map_col:
                    st.markdown("### Structural Spatial Map")
                    
                    # Floor Selector for the Map View
                    view_floor = st.selectbox("👁️ View Floor Map:", options=list(floor_maps.keys()), index=1)
                    
                    fig = go.Figure()
                    
                    # 1. Load the background image based on dropdown
                    try:
                        img_path = floor_maps[view_floor]
                        img = Image.open(img_path)
                        
                        # --- THE CALIBRATION BOUNDS ---
                        # We will need to calibrate these numbers for each floor!
                        # For now, using placeholder coordinates
                        dx_min, dx_max = 0, 100 
                        dy_min, dy_max = 0, 100 
                        
                        fig.add_layout_image(
                            dict(
                                source=img,
                                xref="x", yref="y",
                                x=dx_min, y=dy_max,
                                sizex=(dx_max - dx_min),
                                sizey=(dy_max - dy_min),
                                sizing="stretch",
                                opacity=0.9,
                                layer="below"
                            )
                        )
                    except FileNotFoundError:
                        st.warning(f"Image '{img_path}' not found on server.")

                    # 2. Draw the Route (Note: The math will be off until we calibrate!)
                    # We extract coordinates directly from the backend calculation
                    if "SEQUENCE LIST" in result:
                        # This is a simplified plotter just to get the lines on screen
                        s_node = db[start_point]
                        e_node = db[destination]
                        try:
                            # Recalculate just the single shortest path to plot
                            path = nx.shortest_path(net, s_node, e_node, weight='weight')
                            x_coords = [p[0] for p in path]
                            y_coords = [p[1] for p in path]
                            
                            fig.add_trace(go.Scatter(x=x_coords, y=y_coords, mode='lines+markers', line=dict(color='red', width=4), name="Route"))
                        except nx.NetworkXNoPath:
                            pass

                    fig.update_xaxes(range=[dx_min, dx_max], showgrid=False, zeroline=False, visible=False)
                    fig.update_yaxes(range=[dy_min, dy_max], showgrid=False, zeroline=False, visible=False, scaleanchor="x", scaleratio=1)
                    fig.update_layout(template="plotly_dark", margin=dict(l=0, r=0, t=0, b=0), height=500, showlegend=False)
                    
                    st.plotly_chart(fig, use_container_width=True)
else:
    st.error("System Offline: Could not load the hospital map data.")
